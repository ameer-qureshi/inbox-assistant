"""Request and response models (the API contract)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import Category, ClassificationState, EmailStatus, ReplyStatus

Tone = Literal["formal", "neutral", "short"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserOut(ORM):
    id: int
    email: str


# ---------- emails ----------

class EmailListItem(ORM):
    id: int
    thread_id: int
    from_name: str
    from_address: str
    subject: str
    snippet: str
    received_at: datetime
    status: EmailStatus
    category: Category | None
    priority: int | None
    ai_summary: str | None
    needs_review: bool
    classification_state: ClassificationState


class EmailOut(EmailListItem):
    to_addresses: list[str]
    cc_addresses: list[str]
    body_text: str
    expected_action: str | None
    is_outbound: bool


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class ReplyOut(ORM):
    id: int
    email_id: int
    body: str
    status: ReplyStatus
    attempts: int
    error: str | None
    created_at: datetime
    sent_at: datetime | None


class DraftOut(ORM):
    id: int
    email_id: int
    tone: str
    body: str
    model: str
    created_at: datetime


class ThreadOut(BaseModel):
    id: int
    subject: str
    messages: list[EmailOut]
    replies: list[ReplyOut]
    latest_draft: DraftOut | None


class EmailPatch(BaseModel):
    status: Literal["to_process", "ignored"]


class DraftIn(BaseModel):
    tone: Tone = "neutral"


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)
    draft_id: int | None = None


# ---------- summary ----------

class PriorityItem(BaseModel):
    email: EmailListItem
    reason: str


class SummaryOut(BaseModel):
    date: date
    total: int
    to_process: int
    high_priority: int
    by_category: dict[str, int]
    summary: str
    ai_generated: bool
    top: list[PriorityItem]


class StatsOut(BaseModel):
    emails: int
    classified: int
    first_try_valid_rate: float | None
    fallback_count: int
    last_sync_runs: list[dict]


# ---------- webhooks (n8n -> backend) ----------

class IncomingEmail(BaseModel):
    gmail_message_id: str = Field(min_length=1, max_length=128)
    gmail_thread_id: str = Field(min_length=1, max_length=128)
    rfc822_message_id: str | None = None
    references: str | None = None
    from_name: str = ""
    from_address: str = Field(min_length=3, max_length=320)
    to_addresses: list[str] = []
    cc_addresses: list[str] = []
    subject: str = ""
    body_text: str = ""
    received_at: datetime
    is_outbound: bool = False


class EmailBatchIn(BaseModel):
    sync_run_id: int | None = None
    emails: list[IncomingEmail] = Field(max_length=500)


class EmailBatchOut(BaseModel):
    received: int
    inserted: int
    duplicates: int


class SyncStartOut(BaseModel):
    sync_run_id: int
    after_epoch: int  # value for Gmail's "after:" search operator
    cursor: datetime | None


class SyncCompleteIn(BaseModel):
    status: Literal["success", "failed"]
    fetched_count: int = 0
    error: str | None = None


class PendingClassification(BaseModel):
    email_id: int
    gmail_message_id: str
    groq_request: dict


class ClassificationIn(BaseModel):
    raw_output: str = Field(default="", max_length=20_000)
    attempt: int = Field(ge=1, le=2)


class ClassificationResultOut(BaseModel):
    email_id: int
    valid: bool
    final: bool  # True => nothing more to do for this email
    retry_request: dict | None = None  # stricter prompt for attempt 2


class ClaimIn(BaseModel):
    attempt: int = Field(ge=1)


class ClaimOut(BaseModel):
    claimed: bool


class ReplyStatusIn(BaseModel):
    status: Literal["sent", "failed"]
    attempt: int = Field(ge=1)
    gmail_message_id: str | None = None
    error: str | None = Field(default=None, max_length=2000)


class WorkflowErrorIn(BaseModel):
    workflow: str = Field(max_length=255)
    node: str | None = Field(default=None, max_length=255)
    message: str = Field(max_length=5000)
    execution_id: str | None = Field(default=None, max_length=64)
