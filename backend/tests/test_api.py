"""Auth, list filters, pagination, threads, drafts and summary."""

from sqlalchemy import select

from app.ai.masking import mask_sensitive
from app.models import Email
from tests.conftest import WEBHOOK_HEADERS, import_emails, make_email


def classify(client, email_id, category, priority):
    import json
    raw = json.dumps({"category": category, "priority": priority,
                      "summary": "A test email summary.", "expected_action": "Reply"})
    client.post(f"/api/webhooks/emails/{email_id}/classification",
                json={"raw_output": raw, "attempt": 1}, headers=WEBHOOK_HEADERS)


# ---- auth ----

def test_no_data_without_login(client):
    for url in ["/api/emails", "/api/threads/1", "/api/summary", "/api/stats", "/api/auth/me"]:
        assert client.get(url).status_code == 401
    assert client.post("/api/emails/1/draft", json={"tone": "short"}).status_code == 401


def test_wrong_password(client):
    r = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "nope"})
    assert r.status_code == 401


def test_password_is_hashed(client, db):
    from app.models import User
    user = db.scalar(select(User))
    assert user.password_hash.startswith("$argon2id$")
    assert "correct-horse-battery" not in user.password_hash


def test_logout(auth_client):
    assert auth_client.get("/api/auth/me").status_code == 200
    auth_client.post("/api/auth/logout")
    assert auth_client.get("/api/auth/me").status_code == 401


# ---- list ----

def test_filters_and_pagination(auth_client, client, db):
    import_emails(client, [make_email(i, minutes_ago=i,
                                      from_address=f"user{i % 3}@x.example",
                                      subject="Invoice 2026" if i % 2 else "Hello")
                           for i in range(1, 26)])
    ids = db.scalars(select(Email.id).order_by(Email.id)).all()
    for i, eid in enumerate(ids):
        classify(client, eid, "invoice" if i % 2 == 0 else "client", 1 + i % 3)

    page1 = auth_client.get("/api/emails", params={"page_size": 10}).json()
    assert page1["total"] == 25 and page1["pages"] == 3 and len(page1["items"]) == 10
    # newest first
    dates = [i["received_at"] for i in page1["items"]]
    assert dates == sorted(dates, reverse=True)

    inv = auth_client.get("/api/emails", params={"category": "invoice"}).json()
    assert inv["total"] == 13

    combined = auth_client.get("/api/emails", params={
        "category": "invoice", "priority": 1, "q": "invoice"}).json()
    for item in combined["items"]:
        assert item["category"] == "invoice" and item["priority"] == 1
        assert "invoice" in item["subject"].lower()

    by_sender = auth_client.get("/api/emails", params={"sender": "user1@"}).json()
    assert all(i["from_address"] == "user1@x.example" for i in by_sender["items"])


def test_search_escapes_wildcards(auth_client, client):
    import_emails(client, [make_email(1, subject="100% discount"), make_email(2, subject="Hello")])
    assert auth_client.get("/api/emails", params={"q": "%"}).json()["total"] == 1


def test_ignore_status(auth_client, client, db):
    import_emails(client, [make_email(1)])
    eid = db.scalar(select(Email.id))
    r = auth_client.patch(f"/api/emails/{eid}", json={"status": "ignored"})
    assert r.json()["status"] == "ignored"
    assert auth_client.get("/api/emails", params={"status": "ignored"}).json()["total"] == 1


# ---- thread ----

def test_thread_in_chronological_order(auth_client, client, db):
    import_emails(client, [make_email(3, thread="t", minutes_ago=5),
                           make_email(1, thread="t", minutes_ago=50),
                           make_email(2, thread="t", minutes_ago=20, is_outbound=True)])
    thread_id = db.scalar(select(Email.thread_id))
    t = auth_client.get(f"/api/threads/{thread_id}").json()
    assert [m["subject"] for m in t["messages"]] == ["Subject 1", "Subject 2", "Subject 3"]
    # outbound messages are in the thread but not in the inbox list
    assert auth_client.get("/api/emails").json()["total"] == 2


# ---- drafts (demo mode, no API key) ----

def test_draft_never_sends(auth_client, client, db):
    import_emails(client, [make_email(1)])
    eid = db.scalar(select(Email.id))
    r = auth_client.post(f"/api/emails/{eid}/draft", json={"tone": "formal"})
    assert r.status_code == 201 and r.json()["tone"] == "formal"
    assert auth_client.get(f"/api/emails/{eid}").json()["status"] == "draft_ready"
    tid = auth_client.get(f"/api/emails/{eid}").json()["thread_id"]
    thread = auth_client.get(f"/api/threads/{tid}").json()
    assert thread["latest_draft"]["id"] == r.json()["id"]
    assert thread["replies"] == []  # nothing sent


def test_invalid_tone_rejected(auth_client, client, db):
    import_emails(client, [make_email(1)])
    eid = db.scalar(select(Email.id))
    assert auth_client.post(f"/api/emails/{eid}/draft", json={"tone": "angry"}).status_code == 422


# ---- summary ----

def test_summary_top5_ordering(auth_client, client, db):
    import_emails(client, [make_email(i, minutes_ago=10 + i) for i in range(1, 8)])
    ids = db.scalars(select(Email.id).order_by(Email.id)).all()
    prios = [3, 1, 2, 1, 3, 2, 1]
    for eid, p in zip(ids, prios, strict=True):
        classify(client, eid, "client", p)

    s = auth_client.get("/api/summary").json()
    assert s["total"] == 7 and len(s["top"]) == 5
    top_prios = [t["email"]["priority"] for t in s["top"]]
    assert top_prios == sorted(top_prios)  # urgent first
    assert all(t["reason"].startswith("Priority") for t in s["top"])
    assert s["summary"]


def test_stats(auth_client, client, db):
    import_emails(client, [make_email(1), make_email(2)])
    ids = db.scalars(select(Email.id)).all()
    classify(client, ids[0], "client", 1)
    client.post(f"/api/webhooks/emails/{ids[1]}/classification",
                json={"raw_output": "oops", "attempt": 1}, headers=WEBHOOK_HEADERS)
    assert auth_client.get("/api/stats").json()["first_try_valid_rate"] == 0.5


# ---- masking ----

def test_masking_keeps_normal_text():
    text = "Meeting on 2026-10-21 at 14:30, invoice total 1250 EUR."
    assert mask_sensitive(text) == text


def test_masking_french_formats():
    out = mask_sensitive("Tél : 06.12.34.56.78 ou 01 23 45 67 89, IBAN FR7630006000011234567890189")
    assert out.count("[PHONE]") == 2 and "[IBAN]" in out
