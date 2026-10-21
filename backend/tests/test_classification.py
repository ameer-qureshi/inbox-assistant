"""Required: a valid AI output and an invalid one are both handled."""

import json

import pytest
from sqlalchemy import select

from app.ai.classification import parse_classification
from app.models import Category, ClassificationState, Email
from tests.conftest import WEBHOOK_HEADERS, import_emails, make_email

VALID = json.dumps({"category": "invoice", "priority": 1,
                    "summary": "Invoice 42 is due on Friday.",
                    "expected_action": "Pay the invoice before Friday"})


@pytest.fixture
def email_id(client, db):
    import_emails(client, [make_email(1)])
    return db.scalar(select(Email.id))


def post(client, email_id, raw, attempt):
    r = client.post(f"/api/webhooks/emails/{email_id}/classification",
                    json={"raw_output": raw, "attempt": attempt}, headers=WEBHOOK_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


# ---- unit tests of the validator ----

@pytest.mark.parametrize("raw", [
    VALID,
    f"```json\n{VALID}\n```",                       # tolerated: code fence
    VALID.replace('"invoice"', '"  Invoice "'),     # tolerated: case/space
])
def test_parse_valid(raw):
    out = parse_classification(raw)
    assert out is not None and out.category == "invoice" and out.priority == 1


@pytest.mark.parametrize("raw", [
    "",
    "Sure! Here is the classification: invoice",          # not JSON
    "[1, 2, 3]",                                          # JSON but not an object
    VALID.replace('"invoice"', '"facture"'),              # category outside the closed list
    VALID.replace('"priority": 1', '"priority": 5'),      # priority out of range
    VALID.replace('"priority": 1', '"priority": "1"'),    # string, not integer
    VALID.replace('"priority": 1', '"priority": true'),   # bool, not integer
    json.dumps({"category": "client", "priority": 2}),    # missing fields
    VALID[:-10],                                          # truncated output
])
def test_parse_invalid(raw):
    assert parse_classification(raw) is None


# ---- end-to-end through the webhook ----

def test_valid_output_is_stored(client, db, email_id):
    out = post(client, email_id, VALID, attempt=1)
    assert out["valid"] and out["final"]
    e = db.get(Email, email_id)
    assert e.category == Category.invoice and e.priority == 1
    assert e.classification_state == ClassificationState.done
    assert e.first_try_valid is True and e.needs_review is False


def test_invalid_then_valid(client, db, email_id):
    first = post(client, email_id, "not json", attempt=1)
    assert first["valid"] is False and first["final"] is False
    assert first["retry_request"]["response_format"] == {"type": "json_object"}

    second = post(client, email_id, VALID, attempt=2)
    assert second["valid"] and second["final"]
    db.expire_all()
    e = db.get(Email, email_id)
    assert e.category == Category.invoice and e.first_try_valid is False


def test_invalid_twice_falls_back_to_other_and_review(client, db, email_id):
    post(client, email_id, "not json", attempt=1)
    out = post(client, email_id, '{"category": "urgent!!"}', attempt=2)
    assert out == {"email_id": email_id, "valid": False, "final": True, "retry_request": None}
    db.expire_all()
    e = db.get(Email, email_id)
    assert e.category == Category.other
    assert e.needs_review is True
    assert e.classification_state == ClassificationState.fallback


def test_classification_is_idempotent(client, db, email_id):
    post(client, email_id, VALID, attempt=1)
    other = VALID.replace('"invoice"', '"spam"')
    post(client, email_id, other, attempt=1)  # n8n replays the call
    db.expire_all()
    assert db.get(Email, email_id).category == Category.invoice


def test_pending_endpoint_masks_sensitive_data(client):
    import_emails(client, [make_email(
        1, body_text="Call me at +33 6 12 34 56 78. IBAN FR76 3000 6000 0112 3456 7890 189.")])
    pending = client.get("/api/webhooks/classification/pending", headers=WEBHOOK_HEADERS).json()
    user_msg = pending[0]["groq_request"]["messages"][1]["content"]
    assert "[PHONE]" in user_msg and "[IBAN]" in user_msg
    assert "12 34 56 78" not in user_msg and "3000 6000" not in user_msg
