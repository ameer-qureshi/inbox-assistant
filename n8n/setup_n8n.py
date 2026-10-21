"""Loads the n8n credentials (from .env) and the 4 workflows into the running n8n container.

Usage, from the repository root, once `docker compose up -d` is running:
    python n8n/setup_n8n.py

- Secrets are read from .env and piped into the container: they are never
  written into the repository or into the workflow exports.
- n8n encrypts the credentials with N8N_ENCRYPTION_KEY when importing them.
- After this, open http://localhost:5678, open the "Gmail account" credential
  and click "Sign in with Google" once (OAuth cannot be scripted).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_env() -> dict[str, str]:
    env_file = ROOT / ".env"
    if not env_file.exists():
        sys.exit("No .env file found. Run: cp .env.example .env  and fill it in.")
    values: dict[str, str] = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def compose(*args: str, stdin: str | None = None) -> None:
    cmd = ["docker", "compose", "exec", "-T", "n8n", *args]
    result = subprocess.run(cmd, cwd=ROOT, input=stdin, text=True, capture_output=True)
    if result.returncode != 0:
        sys.exit(f"Command failed: {' '.join(args)}\n{result.stdout}\n{result.stderr}")
    print(result.stdout.strip())


def main() -> None:
    env = read_env()
    missing = [k for k in ("WEBHOOK_SECRET", "N8N_WEBHOOK_SECRET", "GROQ_API_KEY",
                           "GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET") if not env.get(k)]
    if missing:
        print(f"Warning: empty in .env: {', '.join(missing)}. Those credentials will need "
              "to be completed in the n8n UI.")

    # IDs must match the ones referenced in n8n/workflows/*.json
    credentials = [
        {"id": "BackendWebhook01", "name": "Backend webhook secret", "type": "httpHeaderAuth",
         "data": {"name": "X-Webhook-Secret", "value": env.get("WEBHOOK_SECRET", "")}},
        {"id": "N8nSendSecret001", "name": "Send-reply webhook secret", "type": "httpHeaderAuth",
         "data": {"name": "X-Webhook-Secret", "value": env.get("N8N_WEBHOOK_SECRET", "")}},
        {"id": "GroqApiKey000001", "name": "Groq API key", "type": "httpHeaderAuth",
         "data": {"name": "Authorization", "value": f"Bearer {env.get('GROQ_API_KEY', '')}"}},
        {"id": "GmailOAuth200001", "name": "Gmail account", "type": "gmailOAuth2",
         "data": {"clientId": env.get("GMAIL_CLIENT_ID", ""),
                  "clientSecret": env.get("GMAIL_CLIENT_SECRET", "")}},
    ]
    tmp = "/tmp/inbox-credentials.json"
    compose("sh", "-c", f"umask 077 && cat > {tmp}", stdin=json.dumps(credentials))
    try:
        compose("n8n", "import:credentials", f"--input={tmp}")
    finally:
        compose("rm", "-f", tmp)

    compose("n8n", "import:workflow", "--separate", "--input=/workflows")
    print("\nDone. Next steps:\n"
          "  1. docker compose restart n8n\n"
          "  2. http://localhost:5678 > Credentials > 'Gmail account' > Sign in with Google\n"
          "  3. Activate workflows 1, 2 and 3 (toggle at the top right of each workflow)\n"
          "  4. In .env set N8N_SEND_WEBHOOK_URL=http://n8n:5678/webhook/send-reply\n"
          "     then: docker compose up -d backend")


if __name__ == "__main__":
    main()
