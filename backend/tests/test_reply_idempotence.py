"""Required: the same reply sent twice leaves only once."""

import pytest
from sqlalchemy import func, select

from app.models import Email, EmailStatus, Reply, ReplyStatus
from app.services import replies as reply_service
from tests.conftest import WEBHOOK_HEADERS, import_emails, make_email


@pytest.fixture
def dispatched(monkeypatch):
    """Records every hand-off to the sender instead of sending."""
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(reply_service, "dispatch", lambda rid, att: calls.append((rid, att)))
    return calls


@pytest.fixture
def email_id(client, db):
    import_emails(client, [make_email(1)])
    return db.scalar(select(Email.id))


def reply(client, email_id, key="key-0001-abcdef", body="Thanks, see you Monday."):
    return client.post(f"/api/emails/{email_id}/reply", json={"body": body},
                       headers={"Idempotency-Key": key})


def test_same_reply_sent_twice_is_sent_once(auth_client, db, email_id, dispatched):
    first = reply(auth_client, email_id)
    second = reply(auth_client, email_id)  # double click / network retry

    assert first.status_code == 202
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert db.scalar(select(func.count()).select_from(Reply)) == 1
    assert dispatched == [(first.json()["id"], 1)]  # handed to the sender exactly once


def test_different_keys_are_different_replies(auth_client, email_id, dispatched):
    reply(auth_client, email_id, key="key-aaaa-0001")
    reply(auth_client, email_id, key="key-bbbb-0002")
    assert len(dispatched) == 2


def test_key_reused_for_another_email_is_conflict(auth_client, client, db, dispatched):
    import_emails(client, [make_email(1), make_email(2)])
    ids = db.scalars(select(Email.id).order_by(Email.id)).all()
    assert reply(auth_client, ids[0]).status_code == 202
    assert reply(auth_client, ids[1]).status_code == 409


def test_missing_idempotency_key_is_rejected(auth_client, email_id, dispatched):
    r = auth_client.post(f"/api/emails/{email_id}/reply", json={"body": "hi"})
    assert r.status_code == 422
    assert dispatched == []


def test_claim_only_once(auth_client, client, email_id, dispatched):
    rid = reply(auth_client, email_id).json()["id"]
    c1 = client.post(f"/api/webhooks/replies/{rid}/claim", json={"attempt": 1}, headers=WEBHOOK_HEADERS)
    c2 = client.post(f"/api/webhooks/replies/{rid}/claim", json={"attempt": 1}, headers=WEBHOOK_HEADERS)
    assert c1.json() == {"claimed": True}
    assert c2.json() == {"claimed": False}  # a duplicated n8n execution does not send


def test_retry_only_after_failure_and_only_once(auth_client, client, db, email_id, dispatched):
    rid = reply(auth_client, email_id).json()["id"]

    # Still sending -> retry refused
    assert auth_client.post(f"/api/replies/{rid}/retry").status_code == 409

    client.post(f"/api/webhooks/replies/{rid}/status", headers=WEBHOOK_HEADERS,
                json={"status": "failed", "attempt": 1, "error": "Gmail 500"})
    assert auth_client.get(f"/api/replies/{rid}").json()["status"] == "failed"

    r1 = auth_client.post(f"/api/replies/{rid}/retry")
    r2 = auth_client.post(f"/api/replies/{rid}/retry")  # double click on Retry
    assert r1.status_code == 202 and r1.json()["attempts"] == 2
    assert r2.status_code == 409
    assert dispatched == [(rid, 1), (rid, 2)]


def test_sent_status_marks_email_replied_and_is_idempotent(auth_client, client, db, email_id, dispatched):
    rid = reply(auth_client, email_id).json()["id"]
    for _ in range(2):  # n8n retrying the callback must be harmless
        r = client.post(f"/api/webhooks/replies/{rid}/status", headers=WEBHOOK_HEADERS,
                        json={"status": "sent", "attempt": 1, "gmail_message_id": "g-1"})
        assert r.status_code == 204
    db.expire_all()
    assert db.get(Reply, rid).status == ReplyStatus.sent
    assert db.get(Email, email_id).status == EmailStatus.replied
    # A late "failed" for the same attempt cannot undo "sent"
    client.post(f"/api/webhooks/replies/{rid}/status", headers=WEBHOOK_HEADERS,
                json={"status": "failed", "attempt": 1})
    db.expire_all()
    assert db.get(Reply, rid).status == ReplyStatus.sent


def test_unreachable_n8n_fails_only_if_unclaimed(auth_client, client, db, email_id, dispatched):
    rid = reply(auth_client, email_id).json()["id"]
    client.post(f"/api/webhooks/replies/{rid}/claim", json={"attempt": 1}, headers=WEBHOOK_HEADERS)
    # n8n claimed it (it may be sending), so a timeout must NOT allow a retry
    assert reply_service.fail_unclaimed(db, rid, 1, "timeout") is False
    db.expire_all()
    assert db.get(Reply, rid).status == ReplyStatus.sending


def test_mock_sender_end_to_end(auth_client, db, email_id):
    """Demo mode (no n8n): the background task marks the reply sent."""
    rid = reply(auth_client, email_id).json()["id"]
    assert auth_client.get(f"/api/replies/{rid}").json()["status"] == "sent"
