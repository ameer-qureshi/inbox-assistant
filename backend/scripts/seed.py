"""Injects the 30 demo emails through the real webhook (same path as n8n).

Usage (inside the backend container):
    python -m scripts.seed               # import the 30 emails
    python -m scripts.seed --classify    # + simulate n8n's AI step with the expected labels

Run it twice: the second run reports 30 duplicates and inserts nothing
(this demonstrates import idempotence).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta

import httpx

from scripts.demo_data import EMAILS, ME

# Simulated AI answers that are invalid, to show the retry + fallback path:
#   "o3": invalid on attempt 1, valid on attempt 2
#   "o6": invalid twice -> category "other" + "needs review"
INVALID_FIRST = {"o3", "o6"}
INVALID_TWICE = {"o6"}


def build_payload(now: datetime) -> list[dict]:
    out = []
    for e in EMAILS:
        received = now - timedelta(hours=e["h"])
        out.append({
            "gmail_message_id": f"demo-{e['k']}",
            "gmail_thread_id": f"demo-{e['t']}",
            "rfc822_message_id": f"<demo-{e['k']}@demo-inbox.example>",
            "from_name": e["n"],
            "from_address": e["a"],
            "to_addresses": [e["a"]] if e.get("out") else [ME],
            "subject": e["s"],
            "body_text": e["b"],
            "received_at": received.isoformat(),
            "is_outbound": bool(e.get("out")),
        })
    return out


class Backend:
    def __init__(self, base: str, secret: str, hmac_key: str) -> None:
        self.http = httpx.Client(base_url=base, timeout=30)
        self.secret, self.hmac_key = secret, hmac_key

    def call(self, method: str, url: str, body: dict | None = None) -> httpx.Response:
        headers = {"X-Webhook-Secret": self.secret}
        content = None
        if body is not None:
            content = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
            if self.hmac_key:
                sig = hmac.new(self.hmac_key.encode(), content, hashlib.sha256).hexdigest()
                headers["X-Signature"] = f"sha256={sig}"
        r = self.http.request(method, url, content=content, headers=headers)
        r.raise_for_status()
        return r


def simulated_ai_output(key: str, attempt: int) -> str:
    e = next(x for x in EMAILS if x["k"] == key)
    if key in INVALID_TWICE or (key in INVALID_FIRST and attempt == 1):
        return "Sure! This email looks like category: other, priority low."
    return json.dumps({
        "category": e["c"], "priority": e["p"],
        "summary": f"{e['n']} writes about: {e['s'][:80]}.",
        "expected_action": "No action" if e["p"] == 3 else "Reply to the sender",
    })


def classify(api: Backend) -> None:
    done = 0
    while batch := api.call("GET", "/api/webhooks/classification/pending?limit=50").json():
        for item in batch:
            key = item["gmail_message_id"].removeprefix("demo-")
            for attempt in (1, 2):
                res = api.call("POST", f"/api/webhooks/emails/{item['email_id']}/classification",
                               {"raw_output": simulated_ai_output(key, attempt),
                                "attempt": attempt}).json()
                if res["final"]:
                    break
            done += 1
    print(f"Classified {done} email(s) with simulated AI output")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--classify", action="store_true",
                        help="simulate the AI classification with the expected labels")
    parser.add_argument("--batch-size", type=int, default=10)
    args = parser.parse_args()

    api = Backend(os.environ.get("BACKEND_URL", "http://localhost:8000"),
                  os.environ.get("WEBHOOK_SECRET", ""), os.environ.get("WEBHOOK_HMAC_SECRET", ""))
    emails = build_payload(datetime.now(UTC))

    t0 = time.perf_counter()
    inserted = duplicates = 0
    for i in range(0, len(emails), args.batch_size):
        out = api.call("POST", "/api/webhooks/emails/batch",
                       {"emails": emails[i:i + args.batch_size]}).json()
        inserted += out["inserted"]
        duplicates += out["duplicates"]
    elapsed = time.perf_counter() - t0
    print(f"Imported {len(emails)} demo emails in {elapsed:.2f}s: "
          f"{inserted} inserted, {duplicates} duplicate(s) skipped")

    if args.classify:
        classify(api)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except httpx.HTTPStatusError as e:
        print(f"Backend refused the request: HTTP {e.response.status_code} {e.response.text}")
        sys.exit(1)
    except httpx.HTTPError as e:
        print(f"Cannot reach the backend: {e}")
        sys.exit(1)
