"""Minimal Groq client (OpenAI-compatible) with retry on 429 and 5xx."""

from __future__ import annotations

import logging
import time

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


class AIError(Exception):
    pass


def model_options(model: str) -> dict:
    """Extra request fields for a model.

    gpt-oss models reason before answering, and that reasoning counts toward
    max_tokens: keep it short so the JSON answer is never cut off.
    """
    return {"reasoning_effort": "low"} if model.startswith("openai/gpt-oss") else {}


def chat_json(model: str, messages: list[dict], max_tokens: int = 800,
              temperature: float = 0.3) -> str:
    """Calls the chat-completions API in JSON mode and returns the raw content.

    Retries with exponential backoff on HTTP 429 (quota) and 5xx, honouring
    the Retry-After header when the provider sends one.
    """
    s = get_settings()
    if not s.ai_enabled:
        raise AIError("AI is not configured (GROQ_API_KEY is empty)")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        **model_options(model),
    }
    headers = {"Authorization": f"Bearer {s.groq_api_key.get_secret_value()}"}
    delay = 2.0
    for attempt in range(1, s.ai_max_retries + 1):
        try:
            r = httpx.post(f"{s.groq_base_url}/chat/completions", json=payload,
                           headers=headers, timeout=s.ai_timeout_seconds)
        except httpx.HTTPError as e:
            log.warning("AI request failed (attempt %s): %s", attempt, type(e).__name__)
        else:
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"] or ""
            if r.status_code != 429 and r.status_code < 500:
                # 4xx other than 429: retrying will not help
                raise AIError(f"AI provider returned HTTP {r.status_code}")
            retry_after = r.headers.get("retry-after")
            if retry_after and retry_after.replace(".", "", 1).isdigit():
                delay = min(float(retry_after), 30.0)
            log.warning("AI HTTP %s (attempt %s), retrying in %.1fs",
                        r.status_code, attempt, delay)
        if attempt < s.ai_max_retries:
            time.sleep(delay)
            delay *= 2
    raise AIError("AI provider unavailable after retries")
