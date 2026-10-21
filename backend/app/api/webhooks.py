"""Machine-to-machine routes called by n8n. All require the shared secret."""


import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.classification import build_groq_request
from app.db import get_db
from app.models import ClassificationState, Email, SyncRun, WorkflowError
from app.schemas import (
    ClaimIn,
    ClaimOut,
    ClassificationIn,
    ClassificationResultOut,
    EmailBatchIn,
    EmailBatchOut,
    PendingClassification,
    ReplyStatusIn,
    SyncCompleteIn,
    SyncStartOut,
    WorkflowErrorIn,
)
from app.security import verify_webhook
from app.services import replies as reply_service
from app.services.classify import apply_classification
from app.services.ingest import complete_sync, fail_running_syncs, import_batch, start_sync

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks (n8n)"],
                   dependencies=[Depends(verify_webhook)])


# ---------- 1. sync ----------

@router.post("/sync/start", response_model=SyncStartOut)
def sync_start(db: Session = Depends(get_db)) -> SyncStartOut:
    """Opens a sync run and returns the cursor (Gmail `after:` epoch seconds)."""
    run = start_sync(db)
    after = int(run.cursor_from.timestamp()) if run.cursor_from else 0
    return SyncStartOut(sync_run_id=run.id, after_epoch=after, cursor=run.cursor_from)


@router.post("/emails/batch", response_model=EmailBatchOut)
def emails_batch(body: EmailBatchIn, db: Session = Depends(get_db)) -> EmailBatchOut:
    """Idempotent import: an email already stored (same Gmail id) is skipped."""
    return import_batch(db, body.emails, body.sync_run_id)


@router.post("/sync/{run_id}/complete", status_code=204, response_class=Response)
def sync_complete(run_id: int, body: SyncCompleteIn, db: Session = Depends(get_db)) -> None:
    run = db.get(SyncRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sync run not found")
    complete_sync(db, run, body.status, body.fetched_count, body.error)


# ---------- 2. classification ----------

@router.get("/classification/pending", response_model=list[PendingClassification])
def pending_classification(limit: int = Query(default=10, ge=1, le=50),
                           db: Session = Depends(get_db)) -> list[PendingClassification]:
    """Emails waiting for the AI, with a ready-to-send Groq request (content already masked)."""
    emails = db.scalars(select(Email).where(
        Email.classification_state == ClassificationState.pending, Email.is_outbound.is_(False))
        .order_by(Email.received_at).limit(limit)).all()
    return [PendingClassification(email_id=e.id, gmail_message_id=e.gmail_message_id,
                                  groq_request=build_groq_request(e)) for e in emails]


@router.post("/emails/{email_id}/classification", response_model=ClassificationResultOut)
def classification(email_id: int, body: ClassificationIn,
                   db: Session = Depends(get_db)) -> ClassificationResultOut:
    """n8n posts the raw AI text; the backend validates it.

    valid=false, final=false -> n8n retries once with `retry_request`.
    valid=false, final=true  -> fallback applied (category other, needs review).
    """
    email = db.get(Email, email_id)
    if email is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Email not found")
    return apply_classification(db, email, body.raw_output, body.attempt)


# ---------- 3. send replies ----------

@router.post("/replies/{reply_id}/claim", response_model=ClaimOut)
def claim(reply_id: int, body: ClaimIn, db: Session = Depends(get_db)) -> ClaimOut:
    """n8n must claim an attempt before sending. Only the first claim wins."""
    return ClaimOut(claimed=reply_service.claim_attempt(db, reply_id, body.attempt))


@router.post("/replies/{reply_id}/status", status_code=204, response_class=Response)
def reply_status(reply_id: int, body: ReplyStatusIn, db: Session = Depends(get_db)) -> None:
    reply = reply_service.report_status(db, reply_id, body.attempt, body.status,
                                        body.gmail_message_id, body.error)
    if reply is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reply not found")


# ---------- 4. errors ----------

@router.post("/errors", status_code=201)
def workflow_error(body: WorkflowErrorIn, db: Session = Depends(get_db)) -> dict:
    """Called by the n8n Error Trigger workflow."""
    db.add(WorkflowError(**body.model_dump()))
    db.commit()
    if "sync" in body.workflow.lower():
        # A crashed sync must not leave a "running" run nor move the cursor
        fail_running_syncs(db, f"{body.node or 'workflow'}: {body.message}")
    log.warning("n8n workflow error in %r (node %r)", body.workflow, body.node)
    return {"recorded": True}
