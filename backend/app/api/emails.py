"""User-facing routes. All of them require a session (router dependency)."""


import math
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.ai.client import AIError
from app.ai.drafts import generate_draft
from app.db import get_db
from app.models import (
    Category,
    ClassificationState,
    Draft,
    Email,
    EmailStatus,
    Reply,
    SyncRun,
    Thread,
    utcnow,
)
from app.schemas import (
    DraftIn,
    DraftOut,
    EmailListItem,
    EmailOut,
    EmailPatch,
    Page,
    ReplyIn,
    ReplyOut,
    StatsOut,
    SummaryOut,
    ThreadOut,
)
from app.security import current_user
from app.services import replies as reply_service
from app.services.summary import TZ, build_summary, day_bounds

router = APIRouter(tags=["inbox"], dependencies=[Depends(current_user)])


def _like(value: str) -> str:
    """Escapes LIKE wildcards so user input is matched literally."""
    v = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{v}%"


@router.get("/emails", response_model=Page[EmailListItem])
def list_emails(
    db: Session = Depends(get_db),
    category: list[Category] | None = Query(default=None),
    priority: list[int] | None = Query(default=None),
    status_: list[EmailStatus] | None = Query(default=None, alias="status"),
    sender: str | None = Query(default=None, max_length=200),
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = Query(default=None, max_length=200, description="Search in subject and body"),
    needs_review: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[EmailListItem]:
    """Inbound emails, newest first. Every filter is optional and they combine (AND)."""
    conds = [Email.is_outbound.is_(False)]
    if category:
        conds.append(Email.category.in_(category))
    if priority:
        conds.append(Email.priority.in_(priority))
    if status_:
        conds.append(Email.status.in_(status_))
    if sender:
        conds.append(or_(Email.from_address.ilike(_like(sender), escape="\\"),
                         Email.from_name.ilike(_like(sender), escape="\\")))
    if date_from:
        conds.append(Email.received_at >= day_bounds(date_from)[0])
    if date_to:
        conds.append(Email.received_at < day_bounds(date_to)[1])
    if q:
        conds.append(or_(Email.subject.ilike(_like(q), escape="\\"),
                         Email.body_text.ilike(_like(q), escape="\\")))
    if needs_review is not None:
        conds.append(Email.needs_review.is_(needs_review))

    where = and_(*conds)
    total = db.scalar(select(func.count()).select_from(Email).where(where)) or 0
    items = db.scalars(select(Email).where(where)
                       .order_by(Email.received_at.desc(), Email.id.desc())
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return Page[EmailListItem](
        items=[EmailListItem.model_validate(e) for e in items], total=total, page=page,
        page_size=page_size, pages=max(1, math.ceil(total / page_size)))


def _get_email(db: Session, email_id: int) -> Email:
    email = db.get(Email, email_id)
    if email is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Email not found")
    return email


@router.get("/emails/{email_id}", response_model=EmailOut)
def get_email(email_id: int, db: Session = Depends(get_db)) -> Email:
    return _get_email(db, email_id)


@router.patch("/emails/{email_id}", response_model=EmailOut)
def patch_email(email_id: int, body: EmailPatch, db: Session = Depends(get_db)) -> Email:
    """Mark an email as ignored, or back to "to process"."""
    email = _get_email(db, email_id)
    if email.status == EmailStatus.replied:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already replied")
    email.status = EmailStatus(body.status)
    db.commit()
    return email


@router.get("/threads/{thread_id}", response_model=ThreadOut)
def get_thread(thread_id: int, db: Session = Depends(get_db)) -> ThreadOut:
    """All messages of the conversation in chronological order, plus replies sent from the app."""
    thread = db.get(Thread, thread_id)
    if thread is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found")
    email_ids = [e.id for e in thread.emails]
    imported_gmail_ids = {e.gmail_message_id for e in thread.emails}
    replies = db.scalars(select(Reply).where(Reply.email_id.in_(email_ids))
                         .order_by(Reply.created_at)).all() if email_ids else []
    # A sent reply re-imported by the next sync is already in `messages`
    replies = [r for r in replies if r.gmail_message_id not in imported_gmail_ids]
    draft = db.scalar(select(Draft).where(Draft.email_id.in_(email_ids))
                      .order_by(Draft.created_at.desc()).limit(1)) if email_ids else None
    return ThreadOut(
        id=thread.id, subject=thread.subject,
        messages=[EmailOut.model_validate(e) for e in thread.emails],
        replies=[ReplyOut.model_validate(r) for r in replies],
        latest_draft=DraftOut.model_validate(draft) if draft else None,
    )


@router.get("/summary", response_model=SummaryOut)
def summary(date_: date | None = Query(default=None, alias="date"),
            db: Session = Depends(get_db)) -> SummaryOut:
    """Day summary and the 5 emails to handle first (default: today, Europe/Paris)."""
    return build_summary(db, date_ or utcnow().astimezone(TZ).date())


@router.post("/emails/{email_id}/draft", response_model=DraftOut, status_code=201)
def create_draft(email_id: int, body: DraftIn, db: Session = Depends(get_db)) -> Draft:
    """Asks the AI for an editable draft. Nothing is sent."""
    email = _get_email(db, email_id)
    if email.is_outbound:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot reply to your own message")
    try:
        text, model = generate_draft(email, body.tone)
    except AIError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI draft failed: {e}") from e
    draft = Draft(email_id=email.id, tone=body.tone, body=text, model=model)
    db.add(draft)
    if email.status == EmailStatus.to_process:
        email.status = EmailStatus.draft_ready
    db.commit()
    return draft


@router.post("/emails/{email_id}/reply", response_model=ReplyOut, status_code=202,
             responses={200: {"description": "Duplicate request: existing reply returned"}})
def send_reply(
    email_id: int,
    body: ReplyIn,
    background: BackgroundTasks,
    idempotency_key: str = Header(min_length=8, max_length=128,
                                  description="Unique per user validation, e.g. a UUID"),
    db: Session = Depends(get_db),
):
    """Validated by the user -> queued for sending through n8n. Sent at most once per key."""
    email = _get_email(db, email_id)
    if email.is_outbound:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot reply to your own message")
    try:
        reply, created = reply_service.create_reply(db, email, body.body, idempotency_key,
                                                    body.draft_id)
    except reply_service.ReplyConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    if created:
        background.add_task(reply_service.dispatch, reply.id, reply.attempts)
        return ReplyOut.model_validate(reply)
    return JSONResponse(ReplyOut.model_validate(reply).model_dump(mode="json"), status_code=200)


@router.get("/replies/{reply_id}", response_model=ReplyOut)
def get_reply(reply_id: int, db: Session = Depends(get_db)) -> Reply:
    reply = db.get(Reply, reply_id)
    if reply is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reply not found")
    return reply


@router.post("/replies/{reply_id}/retry", response_model=ReplyOut, status_code=202)
def retry(reply_id: int, background: BackgroundTasks, db: Session = Depends(get_db)) -> Reply:
    """Only a FAILED reply can be retried; a double click starts one attempt only."""
    attempt = reply_service.retry_reply(db, reply_id)
    reply = db.get(Reply, reply_id)
    if reply is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reply not found")
    if attempt is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Reply is {reply.status.value}, not failed")
    db.refresh(reply)
    background.add_task(reply_service.dispatch, reply.id, attempt)
    return reply


@router.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)) -> StatsOut:
    """Measured results for the report: AI validity rate and sync durations."""
    inbound = Email.is_outbound.is_(False)
    total = db.scalar(select(func.count()).select_from(Email).where(inbound)) or 0
    tried = db.scalar(select(func.count()).select_from(Email)
                      .where(inbound, Email.first_try_valid.is_not(None))) or 0
    ok = db.scalar(select(func.count()).select_from(Email)
                   .where(inbound, Email.first_try_valid.is_(True))) or 0
    classified = db.scalar(select(func.count()).select_from(Email).where(
        inbound, Email.classification_state != ClassificationState.pending)) or 0
    fallback = db.scalar(select(func.count()).select_from(Email).where(
        Email.classification_state == ClassificationState.fallback)) or 0
    runs = db.scalars(select(SyncRun).order_by(SyncRun.started_at.desc()).limit(10)).all()
    return StatsOut(
        emails=total, classified=classified, fallback_count=fallback,
        first_try_valid_rate=round(ok / tried, 3) if tried else None,
        last_sync_runs=[{
            "id": r.id, "status": r.status.value, "started_at": r.started_at.isoformat(),
            "duration_seconds": round((r.finished_at - r.started_at).total_seconds(), 2)
            if r.finished_at else None,
            "fetched": r.fetched_count, "inserted": r.inserted_count,
            "duplicates": r.duplicate_count} for r in runs],
    )
