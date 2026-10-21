"""The "Today" block: day summary + top 5 emails to handle, with reasons.

The ranking is rule-based on purpose: it is predictable, testable and easy to
explain. The AI only writes the free-text summary (cached per day).
"""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.ai.drafts import generate_day_summary
from app.models import DailySummary, Email, EmailStatus, utcnow
from app.schemas import EmailListItem, PriorityItem, SummaryOut

TZ = ZoneInfo("Europe/Paris")
OPEN_STATUSES = (EmailStatus.to_process, EmailStatus.draft_ready)
PRIORITY_LABEL = {1: "urgent", 2: "this week", 3: "low"}
LOOKBACK_DAYS = 7  # unanswered emails from the last week still compete for the top 5


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=TZ).astimezone(UTC)
    return start, start + timedelta(days=1)


def _age(received: datetime, now: datetime) -> str:
    hours = int((now - received).total_seconds() // 3600)
    if hours < 1:
        return "just arrived"
    if hours < 24:
        return f"waiting {hours} h"
    return f"waiting {hours // 24} day(s)"


def build_reason(e: Email, now: datetime) -> str:
    parts = []
    if e.priority:
        parts.append(f"Priority {e.priority} ({PRIORITY_LABEL[e.priority]})")
    if e.category:
        parts.append(e.category.value)
    if e.needs_review:
        parts.append("AI unsure, check manually")
    elif e.expected_action:
        parts.append(e.expected_action)
    if e.status == EmailStatus.draft_ready:
        parts.append("draft ready to send")
    parts.append(_age(e.received_at, now))
    return " · ".join(parts)


def top_emails(db: Session, day: date, limit: int = 5) -> list[Email]:
    start, end = day_bounds(day)
    stmt = (
        select(Email)
        .where(Email.is_outbound.is_(False), Email.status.in_(OPEN_STATUSES),
               Email.received_at >= start - timedelta(days=LOOKBACK_DAYS),
               Email.received_at < end)
        .order_by(
            case((Email.priority.is_(None), 4), else_=Email.priority),  # 1 first, unknown last
            Email.needs_review.desc(),
            case((Email.category == "spam", 1), (Email.category == "newsletter", 1), else_=0),
            Email.received_at.asc(),  # oldest waiting first
        )
        .limit(limit)
    )
    return list(db.scalars(stmt))


def build_summary(db: Session, day: date) -> SummaryOut:
    start, end = day_bounds(day)
    emails = list(db.scalars(select(Email).where(
        Email.is_outbound.is_(False), Email.received_at >= start, Email.received_at < end)
        .order_by(Email.received_at)))

    cats = Counter(e.category.value if e.category else "unclassified" for e in emails)
    open_count = sum(e.status in OPEN_STATUSES for e in emails)
    high = sum(e.priority == 1 for e in emails)

    fallback = (f"{len(emails)} email(s) received, {open_count} still to handle, "
                f"{high} urgent. " + ", ".join(f"{n} {c}" for c, n in cats.most_common()) + "."
                if emails else "No email received on this day.")

    fingerprint = hashlib.sha256("|".join(
        f"{e.id}:{e.status.value}:{e.category}:{e.priority}" for e in emails).encode()).hexdigest()
    cached = db.get(DailySummary, day)
    if cached and cached.fingerprint == fingerprint:
        text, ai = cached.text, cached.text != fallback
    else:
        lines = [f"- [{e.category.value if e.category else '?'} P{e.priority or '?'} "
                 f"{e.status.value}] {e.from_name or e.from_address}: "
                 f"{e.ai_summary or e.subject}" for e in emails]
        text, ai = generate_day_summary(lines, fallback)
        if cached:
            cached.fingerprint, cached.text, cached.generated_at = fingerprint, text, utcnow()
        else:
            db.add(DailySummary(day=day, fingerprint=fingerprint, text=text))
        db.commit()

    now = utcnow()
    return SummaryOut(
        date=day, total=len(emails), to_process=open_count, high_priority=high,
        by_category=dict(cats), summary=text, ai_generated=ai,
        top=[PriorityItem(email=EmailListItem.model_validate(e), reason=build_reason(e, now))
             for e in top_emails(db, day)],
    )
