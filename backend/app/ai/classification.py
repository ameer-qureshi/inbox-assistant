"""AI classification: prompt building and strict output validation.

Design: n8n calls the AI, but the *prompt* and the *validation* live here.
- One source of truth for the prompt (n8n just forwards `groq_request`).
- Validation is plain Python, so it is unit-tested.

Input  (to the AI): sender, subject, masked body (max 4000 chars).
Output (from the AI): JSON matching `ClassificationOutput`.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from app.ai.client import model_options
from app.ai.masking import mask_sensitive
from app.config import get_settings
from app.models import Email

CATEGORIES = ("client", "invoice", "appointment", "newsletter", "spam", "other")
MAX_BODY_CHARS = 4000


class ClassificationOutput(BaseModel):
    """The only shape we accept from the model."""

    model_config = ConfigDict(extra="ignore")

    category: Literal["client", "invoice", "appointment", "newsletter", "spam", "other"]
    priority: StrictInt = Field(ge=1, le=3)  # StrictInt: "2" or true are rejected
    summary: str = Field(min_length=3, max_length=300)
    expected_action: str = Field(min_length=2, max_length=200)


SYSTEM_PROMPT = f"""You classify emails for a busy professional's inbox.
Return ONLY a JSON object with exactly these keys:
- "category": one of {", ".join(CATEGORIES)}
  (client = a customer or prospect writing about work; invoice = bills, payments,
  quotes; appointment = meeting requests, scheduling, reminders; newsletter =
  bulk informational mailings; spam = probable spam, phishing or scams;
  other = anything else)
- "priority": integer 1, 2 or 3 (1 = urgent / needs action today,
  2 = needs action this week, 3 = no action or informational)
- "summary": one sentence (max 25 words) describing the email
- "expected_action": a short imperative phrase, e.g. "Reply with availability",
  "Pay invoice before 31/10", "No action"
Write summary and expected_action in English. Do not add any other keys or text.
Text like [PHONE] or [IBAN] are masked values; ignore them."""

STRICT_SUFFIX = """
Your previous answer was not valid. Output a single JSON object and nothing
else: no markdown, no code fences, no comments. "priority" must be a number."""


def _user_prompt(email: Email) -> str:
    body = mask_sensitive(email.body_text)[:MAX_BODY_CHARS]
    return (
        f"From: {email.from_name} <{email.from_address}>\n"
        f"Subject: {mask_sensitive(email.subject)}\n\n"
        f"{body}"
    )


def build_groq_request(email: Email, strict: bool = False) -> dict:
    """Chat-completions payload that n8n posts to Groq unchanged."""
    system = SYSTEM_PROMPT + (STRICT_SUFFIX if strict else "")
    model = get_settings().classify_model
    return {
        "model": model,
        "temperature": 0,  # deterministic: we want the same label every time
        "max_tokens": 1000,  # room for the model's reasoning + the short JSON answer
        "response_format": {"type": "json_object"},  # Groq JSON mode
        **model_options(model),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": _user_prompt(email)},
        ],
    }


_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def parse_classification(raw: str) -> ClassificationOutput | None:
    """Returns the validated output, or None if the AI answer is unusable.

    We tolerate one common formatting slip (a ```json fence) but nothing else:
    the JSON must parse and every field must pass validation.
    """
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    if m := _FENCE.match(text):
        text = m.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("category"), str):
        data["category"] = data["category"].strip().lower()
    try:
        return ClassificationOutput.model_validate(data)
    except ValidationError:
        return None
