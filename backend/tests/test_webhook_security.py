"""Required: a webhook without the secret, or with a wrong one, is refused."""

import hashlib
import hmac

import pytest

from app.config import get_settings
from tests.conftest import WEBHOOK_HEADERS, make_email

ROUTES = [
    ("post", "/api/webhooks/emails/batch", {"emails": []}),
    ("post", "/api/webhooks/sync/start", None),
    ("get", "/api/webhooks/classification/pending", None),
    ("post", "/api/webhooks/replies/1/status", {"status": "sent", "attempt": 1}),
    ("post", "/api/webhooks/errors", {"workflow": "x", "message": "y"}),
]


@pytest.mark.parametrize(("method", "url", "body"), ROUTES)
def test_missing_secret_is_rejected(client, method, url, body):
    r = getattr(client, method)(url, **({"json": body} if body is not None else {}))
    assert r.status_code == 401


@pytest.mark.parametrize(("method", "url", "body"), ROUTES)
def test_wrong_secret_is_rejected(client, method, url, body):
    kwargs = {"headers": {"X-Webhook-Secret": "wrong-secret"}}
    if body is not None:
        kwargs["json"] = body
    r = getattr(client, method)(url, **kwargs)
    assert r.status_code == 401


def test_rejected_webhook_stores_nothing(client, auth_client):
    client.post("/api/webhooks/emails/batch", json={"emails": [make_email(1)]},
                headers={"X-Webhook-Secret": "nope"})
    assert auth_client.get("/api/emails").json()["total"] == 0


def test_correct_secret_is_accepted(client):
    r = client.post("/api/webhooks/emails/batch", json={"emails": [make_email(1)]},
                    headers=WEBHOOK_HEADERS)
    assert r.status_code == 200


def test_empty_server_secret_fails_closed(client, monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "")
    get_settings.cache_clear()
    r = client.post("/api/webhooks/emails/batch", json={"emails": []},
                    headers={"X-Webhook-Secret": ""})
    assert r.status_code == 503


def test_hmac_signature_when_enabled(client, monkeypatch):
    monkeypatch.setenv("WEBHOOK_HMAC_SECRET", "hmac-key")
    get_settings.cache_clear()
    body = b'{"emails": []}'
    headers = {**WEBHOOK_HEADERS, "Content-Type": "application/json"}

    bad = client.post("/api/webhooks/emails/batch", content=body,
                      headers={**headers, "X-Signature": "sha256=deadbeef"})
    assert bad.status_code == 401

    sig = hmac.new(b"hmac-key", body, hashlib.sha256).hexdigest()
    ok = client.post("/api/webhooks/emails/batch", content=body,
                     headers={**headers, "X-Signature": f"sha256={sig}"})
    assert ok.status_code == 200
