"""Test setup.

By default tests run on in-memory SQLite (fast, zero setup). To run them on
PostgreSQL, as in production:  TEST_DATABASE_URL=postgresql+psycopg://... pytest
"""

import os

os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite://")
os.environ["WEBHOOK_SECRET"] = "test-webhook-secret"
os.environ["ADMIN_EMAIL"] = "admin@example.com"
os.environ["ADMIN_PASSWORD"] = "correct-horse-battery"
os.environ["GROQ_API_KEY"] = ""
os.environ["N8N_SEND_WEBHOOK_URL"] = ""
os.environ["MOCK_SEND_DELAY_SECONDS"] = "0"
os.environ["WEBHOOK_HMAC_SECRET"] = ""

from datetime import UTC, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

WEBHOOK_HEADERS = {"X-Webhook-Secret": "test-webhook-secret"}


@pytest.fixture(autouse=True)
def fresh_db():
    get_settings.cache_clear()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:  # runs the lifespan -> creates the admin user
        yield c


@pytest.fixture
def auth_client(client):
    r = client.post("/api/auth/login",
                    json={"email": "admin@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 200
    return client


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


def make_email(n: int = 1, thread: str | None = None, minutes_ago: int = 60, **kw) -> dict:
    received = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    return {
        "gmail_message_id": f"msg-{n}",
        "gmail_thread_id": thread or f"thr-{n}",
        "rfc822_message_id": f"<msg-{n}@mail.example.com>",
        "from_name": "Alice Martin",
        "from_address": "alice@client.example",
        "to_addresses": ["me@example.com"],
        "subject": f"Subject {n}",
        "body_text": f"Hello, this is message number {n}.",
        "received_at": received.isoformat(),
        **kw,
    }


def import_emails(client, emails: list[dict]) -> dict:
    r = client.post("/api/webhooks/emails/batch", json={"emails": emails}, headers=WEBHOOK_HEADERS)
    assert r.status_code == 200, r.text
    return r.json()
