"""Passwords, sessions and webhook authentication."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import AuthSession, User, utcnow

SESSION_COOKIE = "session"
_hasher = PasswordHasher()  # Argon2id with library defaults
# Used to keep login timing similar when the user does not exist
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


# ---------- passwords ----------

def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if user is None:
        verify_password(_DUMMY_HASH, password)  # constant-ish time
        return None
    return user if verify_password(user.password_hash, password) else None


# ---------- sessions ----------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User, settings: Settings) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=_token_hash(token),
            user_id=user.id,
            expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
        )
    )
    db.commit()
    return token


def delete_session(db: Session, token: str) -> None:
    s = db.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    if s:
        db.delete(s)
        db.commit()


def current_user(
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> User:
    """Dependency: every user-facing route requires a valid session."""
    if not session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    s = db.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(session)))
    if s is None or s.expires_at < utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    return s.user


# ---------- webhooks (n8n -> backend) ----------

async def verify_webhook(
    request: Request,
    x_webhook_secret: str | None = Header(default=None),
    x_signature: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Rejects any webhook call without the right shared secret.

    hmac.compare_digest compares in constant time, so an attacker cannot
    guess the secret character by character from response times.
    """
    expected = settings.webhook_secret.get_secret_value()
    if not expected:
        # Misconfiguration must fail closed, never open
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Webhook secret not configured")
    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook secret")

    # Bonus: if an HMAC key is configured, the body signature is also required
    hmac_key = settings.webhook_hmac_secret.get_secret_value()
    if hmac_key and request.method in {"POST", "PUT", "PATCH"}:
        body = await request.body()
        digest = hmac.new(hmac_key.encode(), body, hashlib.sha256).hexdigest()
        provided = (x_signature or "").removeprefix("sha256=")
        if not hmac.compare_digest(provided, digest):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid body signature")
