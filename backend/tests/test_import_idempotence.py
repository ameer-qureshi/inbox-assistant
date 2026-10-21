"""Required: the same email imported twice is stored once."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from app.db import engine
from app.models import Email, SyncRun, SyncStatus, Thread
from tests.conftest import WEBHOOK_HEADERS, import_emails, make_email


def test_same_email_imported_twice_is_stored_once(client, db):
    first = import_emails(client, [make_email(1)])
    second = import_emails(client, [make_email(1)])

    assert first == {"received": 1, "inserted": 1, "duplicates": 0}
    assert second == {"received": 1, "inserted": 0, "duplicates": 1}
    assert db.scalar(select(func.count()).select_from(Email)) == 1


def test_duplicate_inside_one_batch(client, db):
    out = import_emails(client, [make_email(1), make_email(1), make_email(2)])
    assert out == {"received": 3, "inserted": 2, "duplicates": 1}


def test_overlapping_batches(client, db):
    import_emails(client, [make_email(i) for i in range(1, 6)])
    out = import_emails(client, [make_email(i) for i in range(4, 9)])
    assert out["inserted"] == 3 and out["duplicates"] == 2
    assert db.scalar(select(func.count()).select_from(Email)) == 8


def test_messages_of_same_thread_share_one_thread(client, db):
    import_emails(client, [make_email(1, thread="t", minutes_ago=30),
                           make_email(2, thread="t", minutes_ago=10)])
    assert db.scalar(select(func.count()).select_from(Thread)) == 1


def test_sync_cursor_uses_last_successful_run(client, db):
    r1 = client.post("/api/webhooks/sync/start", headers=WEBHOOK_HEADERS).json()
    assert r1["after_epoch"] == 0  # first sync ever: fetch everything

    client.post(f"/api/webhooks/sync/{r1['sync_run_id']}/complete",
                json={"status": "success", "fetched_count": 3}, headers=WEBHOOK_HEADERS)
    r2 = client.post("/api/webhooks/sync/start", headers=WEBHOOK_HEADERS).json()
    run1 = db.get(SyncRun, r1["sync_run_id"])
    # cursor = start of last successful run minus the overlap (300 s)
    assert r2["after_epoch"] == int(run1.started_at.timestamp()) - 300

    # A failed run must not move the cursor
    client.post(f"/api/webhooks/sync/{r2['sync_run_id']}/complete",
                json={"status": "failed", "error": "boom"}, headers=WEBHOOK_HEADERS)
    r3 = client.post("/api/webhooks/sync/start", headers=WEBHOOK_HEADERS).json()
    assert r3["after_epoch"] == r2["after_epoch"]


def _post_batch(client, run_id: int, emails: list[dict]) -> None:
    r = client.post("/api/webhooks/emails/batch", headers=WEBHOOK_HEADERS,
                    json={"sync_run_id": run_id, "emails": emails})
    assert r.status_code == 200, r.text


def test_sync_run_counts_add_up_over_batches(client, db):
    run_id = client.post("/api/webhooks/sync/start", headers=WEBHOOK_HEADERS).json()["sync_run_id"]
    _post_batch(client, run_id, [make_email(i) for i in range(1, 11)])
    _post_batch(client, run_id, [make_email(i) for i in range(5, 21)])
    run = db.get(SyncRun, run_id)
    assert (run.inserted_count, run.duplicate_count) == (20, 6)


@pytest.mark.skipif(engine.dialect.name == "sqlite", reason="needs real concurrent connections")
def test_sync_run_counts_survive_parallel_batches(client, db):
    # n8n posts the batches of one run at the same time: no count may be lost
    run_id = client.post("/api/webhooks/sync/start", headers=WEBHOOK_HEADERS).json()["sync_run_id"]
    batches = [[make_email(b * 10 + i) for i in range(10)] for b in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda emails: _post_batch(client, run_id, emails), batches))
    assert db.get(SyncRun, run_id).inserted_count == 80


def test_error_workflow_marks_running_sync_failed(client, db):
    run = client.post("/api/webhooks/sync/start", headers=WEBHOOK_HEADERS).json()
    r = client.post("/api/webhooks/errors", headers=WEBHOOK_HEADERS,
                    json={"workflow": "1 - Gmail sync", "node": "Gmail list", "message": "401"})
    assert r.status_code == 201
    db.expire_all()
    assert db.get(SyncRun, run["sync_run_id"]).status == SyncStatus.failed


def test_outbound_message_closes_older_emails_of_thread(client, db):
    from app.models import EmailStatus
    # newest first, like the Gmail API returns them
    import_emails(client, [make_email(3, thread="t", minutes_ago=10),
                           make_email(2, thread="t", minutes_ago=30, is_outbound=True),
                           make_email(1, thread="t", minutes_ago=60)])
    statuses = {e.gmail_message_id: e.status for e in db.scalars(select(Email))}
    assert statuses["msg-1"] == EmailStatus.replied     # answered from Gmail
    assert statuses["msg-3"] == EmailStatus.to_process  # newer message: still open
