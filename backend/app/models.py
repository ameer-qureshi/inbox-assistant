"""Data model.

Tables: users, auth_sessions, threads, emails, drafts, replies, sync_runs,
workflow_errors, daily_summaries.

Idempotence is enforced by the database itself (UNIQUE constraints), not only
by application code, so it holds even under concurrent requests.
"""

from __future__ import annotations

import enum
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Stores UTC datetimes and always returns timezone-aware values.

    PostgreSQL keeps the timezone; SQLite (used in quick tests) does not,
    so we normalise on the way in and out.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):  # type: ignore[override]
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect):  # type: ignore[override]
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Category(enum.StrEnum):
    client = "client"
    invoice = "invoice"
    appointment = "appointment"
    newsletter = "newsletter"
    spam = "spam"  # "probable spam"
    other = "other"


class EmailStatus(enum.StrEnum):
    to_process = "to_process"
    draft_ready = "draft_ready"
    replied = "replied"
    ignored = "ignored"


class ClassificationState(enum.StrEnum):
    pending = "pending"
    done = "done"
    fallback = "fallback"  # AI output invalid twice -> "other" + needs_review


class ReplyStatus(enum.StrEnum):
    sending = "sending"
    sent = "sent"
    failed = "failed"


class SyncStatus(enum.StrEnum):
    running = "running"
    success = "success"
    failed = "failed"


def _enum(e: type[enum.Enum], name: str) -> Enum:
    # native_enum=False -> stored as VARCHAR + CHECK, easy to migrate
    return Enum(e, name=name, native_enum=False, validate_strings=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # We store a SHA-256 of the token, never the token itself
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    user: Mapped[User] = relationship()


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[int] = mapped_column(primary_key=True)
    gmail_thread_id: Mapped[str] = mapped_column(String(128), unique=True)
    subject: Mapped[str] = mapped_column(String(998), default="")
    last_message_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    emails: Mapped[list[Email]] = relationship(
        back_populates="thread", order_by="Email.received_at"
    )


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Idempotence key for imports: a Gmail message can only be stored once
    gmail_message_id: Mapped[str] = mapped_column(String(128), unique=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"))
    rfc822_message_id: Mapped[str | None] = mapped_column(String(998))
    references: Mapped[str | None] = mapped_column(Text)

    from_name: Mapped[str] = mapped_column(String(255), default="")
    from_address: Mapped[str] = mapped_column(String(320))
    to_addresses: Mapped[list[str]] = mapped_column(JSON, default=list)
    cc_addresses: Mapped[list[str]] = mapped_column(JSON, default=list)
    subject: Mapped[str] = mapped_column(String(998), default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(UTCDateTime)
    is_outbound: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[EmailStatus] = mapped_column(
        _enum(EmailStatus, "email_status"), default=EmailStatus.to_process
    )

    # AI classification
    classification_state: Mapped[ClassificationState] = mapped_column(
        _enum(ClassificationState, "classification_state"),
        default=ClassificationState.pending,
    )
    category: Mapped[Category | None] = mapped_column(_enum(Category, "category"))
    priority: Mapped[int | None] = mapped_column(Integer)  # 1 = high, 3 = low
    ai_summary: Mapped[str | None] = mapped_column(Text)
    expected_action: Mapped[str | None] = mapped_column(Text)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    classification_attempts: Mapped[int] = mapped_column(Integer, default=0)
    first_try_valid: Mapped[bool | None] = mapped_column(Boolean)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    thread: Mapped[Thread] = relationship(back_populates="emails")

    @property
    def snippet(self) -> str:
        return " ".join(self.body_text.split())[:160]

    __table_args__ = (
        Index("ix_emails_received_at", "received_at"),
        Index("ix_emails_status", "status"),
        Index("ix_emails_category_priority", "category", "priority"),
        Index("ix_emails_from_address", "from_address"),
    )


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id", ondelete="CASCADE"))
    tone: Mapped[str] = mapped_column(String(16))
    body: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Reply(Base):
    """A reply the user validated. Sent at most once (idempotency_key)."""

    __tablename__ = "replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id", ondelete="CASCADE"))
    draft_id: Mapped[int | None] = mapped_column(ForeignKey("drafts.id", ondelete="SET NULL"))
    # Idempotence key for sending: one key => one reply row => one send
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[ReplyStatus] = mapped_column(
        _enum(ReplyStatus, "reply_status"), default=ReplyStatus.sending
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Highest attempt number already picked up by n8n (prevents duplicate sends
    # if the same dispatch reaches n8n twice)
    claimed_attempt: Mapped[int] = mapped_column(Integer, default=0)
    gmail_message_id: Mapped[str | None] = mapped_column(String(128))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[SyncStatus] = mapped_column(
        _enum(SyncStatus, "sync_status"), default=SyncStatus.running
    )
    cursor_from: Mapped[datetime | None] = mapped_column(UTCDateTime)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class WorkflowError(Base):
    __tablename__ = "workflow_errors"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow: Mapped[str] = mapped_column(String(255))
    node: Mapped[str | None] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    execution_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class DailySummary(Base):
    """Cache of the AI-written day summary (regenerated when emails change)."""

    __tablename__ = "daily_summaries"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
