"""Idempotent email import and sync-cursor management."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    ClassificationState,
    Email,
    EmailStatus,
    SyncRun,
    SyncStatus,
    Thread,
    utcnow,
)
from app.schemas import EmailBatchOut, IncomingEmail

log = logging.getLogger(__name__)


def _get_or_create_thread(db: Session, item: IncomingEmail) -> Thread:
    thread = db.scalar(select(Thread).where(Thread.gmail_thread_id == item.gmail_thread_id))
    if thread is None:
        thread = Thread(gmail_thread_id=item.gmail_thread_id, subject=item.subject,
                        last_message_at=item.received_at)
        db.add(thread)
        db.flush()
    elif item.received_at > thread.last_message_at:
        thread.last_message_at = item.received_at
    return thread


def mark_thread_replied(db: Session, thread_id: int, until: datetime) -> None:
    """An answer in the thread (from Gmail or from the app) closes the older open emails."""
    db.execute(
        update(Email)
        .where(Email.thread_id == thread_id, Email.is_outbound.is_(False),
               Email.received_at <= until,
               Email.status.in_([EmailStatus.to_process, EmailStatus.draft_ready]))
        .values(status=EmailStatus.replied)
        .execution_options(synchronize_session=False)
    )


def import_batch(db: Session, items: list[IncomingEmail], sync_run_id: int | None) -> EmailBatchOut:
    """Stores each email once, keyed by its Gmail message id.

    Two layers of protection:
    1. We skip ids already in the database (and duplicates inside the batch).
    2. The UNIQUE constraint catches a concurrent import of the same id; each
       insert runs in a SAVEPOINT so one duplicate does not cancel the batch.
    """
    ids = {i.gmail_message_id for i in items}
    existing = set(db.scalars(select(Email.gmail_message_id)
                              .where(Email.gmail_message_id.in_(ids))))
    inserted = duplicates = 0
    seen: set[str] = set()

    # Oldest first: Gmail lists newest first, but thread status rules need time order
    for item in sorted(items, key=lambda i: i.received_at):
        if item.gmail_message_id in existing or item.gmail_message_id in seen:
            duplicates += 1
            continue
        seen.add(item.gmail_message_id)
        try:
            with db.begin_nested():  # SAVEPOINT
                thread = _get_or_create_thread(db, item)
                db.add(Email(
                    gmail_message_id=item.gmail_message_id,
                    thread_id=thread.id,
                    rfc822_message_id=item.rfc822_message_id,
                    references=item.references,
                    from_name=item.from_name[:255],
                    from_address=item.from_address.lower(),
                    to_addresses=item.to_addresses,
                    cc_addresses=item.cc_addresses,
                    subject=item.subject,
                    body_text=item.body_text,
                    received_at=item.received_at,
                    is_outbound=item.is_outbound,
                    # Our own sent messages are part of the thread but need no action
                    status=EmailStatus.replied if item.is_outbound else EmailStatus.to_process,
                    classification_state=(ClassificationState.done if item.is_outbound
                                          else ClassificationState.pending),
                ))
            if item.is_outbound:
                mark_thread_replied(db, thread.id, item.received_at)
            inserted += 1
        except IntegrityError:
            duplicates += 1

    if sync_run_id is not None:
        # Atomic increment: n8n posts the batches of one run in parallel, and a
        # read-then-write in Python would let one batch overwrite the other's count
        db.execute(
            update(SyncRun).where(SyncRun.id == sync_run_id)
            .values(inserted_count=SyncRun.inserted_count + inserted,
                    duplicate_count=SyncRun.duplicate_count + duplicates)
            .execution_options(synchronize_session=False)
        )
    db.commit()
    log.info("Imported batch: received=%s inserted=%s duplicates=%s",
             len(items), inserted, duplicates)  # ids/counts only, never content
    return EmailBatchOut(received=len(items), inserted=inserted, duplicates=duplicates)


def start_sync(db: Session) -> SyncRun:
    """Opens a sync run. The cursor is the START time of the last successful run.

    Using the start time (not the end) means emails that arrived *during* the
    last run are fetched again next time; duplicates are absorbed by
    idempotent import. We also subtract an overlap margin for clock skew.
    """
    last_ok = db.scalar(select(SyncRun).where(SyncRun.status == SyncStatus.success)
                        .order_by(SyncRun.started_at.desc()).limit(1))
    cursor = None
    if last_ok:
        cursor = last_ok.started_at - timedelta(seconds=get_settings().sync_overlap_seconds)
    run = SyncRun(cursor_from=cursor)
    db.add(run)
    db.commit()
    return run


def complete_sync(db: Session, run: SyncRun, status: str, fetched: int, error: str | None) -> None:
    run.status = SyncStatus(status)
    run.fetched_count = fetched
    run.error = error
    run.finished_at = utcnow()
    db.commit()


def fail_running_syncs(db: Session, message: str) -> None:
    """Called by the error workflow: a crashed run must never become the cursor."""
    for run in db.scalars(select(SyncRun).where(SyncRun.status == SyncStatus.running)):
        run.status = SyncStatus.failed
        run.error = message[:2000]
        run.finished_at = utcnow()
    db.commit()
