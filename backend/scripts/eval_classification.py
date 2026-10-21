"""Offline evaluation of the AI classification on the 30 demo emails.

Measures, with the exact prompt used in production:
  - valid-JSON-first-try rate  (required in the report)
  - category accuracy against the expected labels
  - priority accuracy (exact) and "within 1"

Usage (needs GROQ_API_KEY):
    python -m scripts.eval_classification [--model openai/gpt-oss-20b] [--pause 2]
Writes the details to eval_results.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime

from app.ai.classification import build_groq_request, parse_classification
from app.ai.client import AIError, chat_json
from app.config import get_settings
from app.models import Email
from scripts.demo_data import EMAILS


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=get_settings().classify_model)
    p.add_argument("--pause", type=float, default=2.0, help="seconds between calls (rate limit)")
    args = p.parse_args()
    if not get_settings().ai_enabled:
        print("GROQ_API_KEY is not set: nothing to evaluate.")
        return 1

    rows = []
    for e in [x for x in EMAILS if not x.get("out")]:
        email = Email(from_name=e["n"], from_address=e["a"], subject=e["s"], body_text=e["b"],
                      received_at=datetime.now(UTC))
        req = build_groq_request(email)
        t0 = time.perf_counter()
        try:
            raw = chat_json(args.model, req["messages"], max_tokens=req["max_tokens"],
                            temperature=req["temperature"])
        except AIError as err:
            raw = f"<error: {err}>"
        latency = time.perf_counter() - t0
        out = parse_classification(raw)
        rows.append({
            "key": e["k"], "expected_category": e["c"], "expected_priority": e["p"],
            "valid_first_try": out is not None,
            "category": out.category if out else None, "priority": out.priority if out else None,
            "latency_s": round(latency, 2), "raw": raw[:500],
        })
        mark = "ok " if out and out.category == e["c"] else "-- "
        print(f"{mark}{e['k']:<4} expected={e['c']:<11} got={(out.category if out else 'INVALID'):<11} "
              f"P{out.priority if out else '?'} ({latency:.2f}s)")
        time.sleep(args.pause)

    n = len(rows)
    valid = [r for r in rows if r["valid_first_try"]]
    cat_ok = sum(r["category"] == r["expected_category"] for r in valid)
    prio_ok = sum(r["priority"] == r["expected_priority"] for r in valid)
    prio_near = sum(abs(r["priority"] - r["expected_priority"]) <= 1 for r in valid)
    confusion = Counter(f"{r['expected_category']}->{r['category']}" for r in valid
                        if r["category"] != r["expected_category"])

    summary = {
        "model": args.model, "emails": n,
        "valid_first_try_rate": round(len(valid) / n, 3),
        "category_accuracy": round(cat_ok / n, 3),
        "priority_exact": round(prio_ok / n, 3),
        "priority_within_1": round(prio_near / n, 3),
        "mean_latency_s": round(sum(r["latency_s"] for r in rows) / n, 2),
        "errors": dict(confusion),
    }
    print("\n" + json.dumps(summary, indent=2))
    with open("eval_results.json", "w") as f:
        json.dump({"summary": summary, "rows": rows}, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
