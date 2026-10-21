"""Sending replies exactly once.

State machine:   sending --(n8n reports)--> sent
                    |                       ^
                    +--> failed --(retry)---+   (retry = new attempt)

Guarantees:
- Same Idempotency-Key -> same reply row (UNIQUE constraint) -> one send.
- Retry is an atomic conditional UPDATE (only from `failed`), so two
  concurrent clicks on "Retry" produce one new attempt, not two.
- n8n must *claim* an attempt before sending; a dispatch that reaches n8n
  twice is claimed only once.
"""

from __future__ import annotations

import logging
import random
import time

import httpx
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import Draft, Email, EmailStatus, Reply, ReplyStatus, utcnow
from app.services.ingest import mark_thread_replied

log = logging.getLogger(__name__)


class ReplyConflict(Exception):
    pass


def create_reply(db: Session, email: Email, body: str, key: str,
                 draft_id: int | None) -> tuple[Reply, bool]:
    """Returns (reply, created). created=False means it was a duplicate request."""
    existing = db.scalar(select(Reply).where(Reply.idempotency_key == key))
    if existing:
        if existing.email_id != email.id:
            raise ReplyConflict("Idempotency key already used for another email")
        return existing, False

    if draft_id is not None:
        draft = db.get(Draft, draft_id)
        if draft is None or draft.email_id != email.id:
            draft_id = None

    reply = Reply(email_id=email.id, draft_id=draft_id, idempotency_key=key,
                  body=body, status=ReplyStatus.sending, attempts=1)
    db.add(reply)
    try:
        db.commit()
    except IntegrityError:
        # Two identical requests raced; the other one won. Return its row.
        db.rollback()
        existing = db.scalar(select(Reply).where(Reply.idempotency_key == key))
        if existing is None or existing.email_id != email.id:
            raise ReplyConflict("Idempotency key conflict") from None
        return existing, False
    return reply, True


def retry_reply(db: Session, reply_id: int) -> int | None:
    """Starts a new attempt. Returns the attempt number, or None if not allowed."""
    res = db.execute(
        update(Reply)
        .where(Reply.id == reply_id, Reply.status == ReplyStatus.failed)
        .values(status=ReplyStatus.sending, attempts=Reply.attempts + 1,
                error=None, updated_at=utcnow())
    )
    db.commit()
    if res.rowcount != 1:
        return None
    return db.scalar(select(Reply.attempts).where(Reply.id == reply_id))


def claim_attempt(db: Session, reply_id: int, attempt: int) -> bool:
    res = db.execute(
        update(Reply)
        .where(Reply.id == reply_id, Reply.status == ReplyStatus.sending,
               Reply.attempts == attempt, Reply.claimed_attempt < attempt)
        .values(claimed_attempt=attempt)
    )
    db.commit()
    return res.rowcount == 1


def report_status(db: Session, reply_id: int, attempt: int, status: str,
                  gmail_message_id: str | None = None, error: str | None = None) -> Reply | None:
    reply = db.get(Reply, reply_id)
    if reply is None:
        return None
    # Idempotent: callbacks for an old attempt, or repeated ones, change nothing.
    # Exception: "sent" from Gmail is the truth and wins over a "failed" we
    # may have recorded for the same attempt.
    if reply.attempts != attempt or reply.status == ReplyStatus.sent:
        return reply
    if reply.status == ReplyStatus.failed and status != "sent":
        return reply
    if status == "sent":
        reply.status = ReplyStatus.sent
        reply.sent_at = utcnow()
        reply.gmail_message_id = gmail_message_id
        reply.error = None
        email = db.get(Email, reply.email_id)
        if email:
            email.status = EmailStatus.replied
            mark_thread_replied(db, email.thread_id, email.received_at)
    else:
        reply.status = ReplyStatus.failed
        reply.error = (error or "Unknown error")[:500]
    db.commit()
    return reply


def fail_unclaimed(db: Session, reply_id: int, attempt: int, error: str) -> bool:
    """Marks an attempt failed ONLY if n8n has not claimed it.

    If the HTTP call to n8n timed out but n8n did receive it and claimed the
    attempt, it may be sending right now: we must not offer a retry.
    """
    res = db.execute(
        update(Reply)
        .where(Reply.id == reply_id, Reply.status == ReplyStatus.sending,
               Reply.attempts == attempt, Reply.claimed_attempt < attempt)
        .values(status=ReplyStatus.failed, error=error, updated_at=utcnow())
    )
    db.commit()
    return res.rowcount == 1


def dispatch_payload(email: Email, reply: Reply, attempt: int) -> dict:
    subject = email.subject if email.subject.lower().startswith("re:") else f"Re: {email.subject}"
    refs = " ".join(x for x in [email.references, email.rfc822_message_id] if x)
    return {
        "reply_id": reply.id,
        "attempt": attempt,
        "gmail_thread_id": email.thread.gmail_thread_id,
        "to": email.from_address,
        "subject": subject,
        "in_reply_to": email.rfc822_message_id,
        "references": refs or None,
        "body": reply.body,
    }


def send_to_n8n(payload: dict) -> None:
    """POSTs the reply to the n8n "Send reply" webhook. Raises on failure."""
    s = get_settings()
    r = httpx.post(s.n8n_send_webhook_url, json=payload, timeout=15,
                   headers={"X-Webhook-Secret": s.n8n_webhook_secret.get_secret_value()})
    r.raise_for_status()


def dispatch(reply_id: int, attempt: int) -> None:
    """Background task: hands the reply to n8n (or the mock sender in demo mode)."""
    s = get_settings()
    with SessionLocal() as db:
        reply = db.get(Reply, reply_id)
        if reply is None or reply.status != ReplyStatus.sending or reply.attempts != attempt:
            return
        email = db.get(Email, reply.email_id)
        assert email is not None
        if s.mock_sender:
            # Demo mode: no n8n/Gmail. Simulates the n8n round trip.
            time.sleep(s.mock_send_delay_seconds)
            if claim_attempt(db, reply_id, attempt):
                ok = random.random() >= s.mock_send_failure_rate
                report_status(db, reply_id, attempt, "sent" if ok else "failed",
                              gmail_message_id=f"mock-{reply_id}-{attempt}" if ok else None,
                              error=None if ok else "Simulated failure (demo mode)")
            return
        try:
            send_to_n8n(dispatch_payload(email, reply, attempt))
            log.info("Reply %s attempt %s handed to n8n", reply_id, attempt)
        except Exception as e:  # noqa: BLE001 - any failure = retryable
            log.warning("Reply %s attempt %s could not reach n8n: %s",
                        reply_id, attempt, type(e).__name__)
            fail_unclaimed(db, reply_id, attempt, "Could not reach the automation service")

