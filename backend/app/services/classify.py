"""Applies an AI classification result coming from n8n.

Rule from the brief: if the AI output is invalid -> one retry, then
category "other" + "needs review".
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai.classification import build_groq_request, parse_classification
from app.models import Category, ClassificationState, Email
from app.schemas import ClassificationResultOut


def apply_classification(db: Session, email: Email, raw: str, attempt: int) -> ClassificationResultOut:
    if email.classification_state != ClassificationState.pending:
        # Already handled (e.g. n8n retried the HTTP call): no-op, idempotent
        return ClassificationResultOut(email_id=email.id, valid=True, final=True)

    result = parse_classification(raw)
    email.classification_attempts = max(email.classification_attempts, attempt)
    if attempt == 1:
        email.first_try_valid = result is not None

    if result is not None:
        email.category = Category(result.category)
        email.priority = result.priority
        email.ai_summary = result.summary
        email.expected_action = result.expected_action
        email.needs_review = False
        email.classification_state = ClassificationState.done
        db.commit()
        return ClassificationResultOut(email_id=email.id, valid=True, final=True)

    if attempt == 1:
        db.commit()
        return ClassificationResultOut(
            email_id=email.id, valid=False, final=False,
            retry_request=build_groq_request(email, strict=True),
        )

    # Second failure: safe fallback, flagged for a human
    email.category = Category.other
    email.priority = 2
    email.ai_summary = None
    email.expected_action = "Check this email manually"
    email.needs_review = True
    email.classification_state = ClassificationState.fallback
    db.commit()
    return ClassificationResultOut(email_id=email.id, valid=False, final=True)
