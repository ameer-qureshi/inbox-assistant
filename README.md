# Inbox Assistant

A Gmail inbox assistant: a web inbox with AI classification, a "Today" priority list and AI reply drafts that are only sent after you confirm them.

```
Website (React)  ->  Backend API (FastAPI + PostgreSQL)  <->  n8n  <->  Gmail / Groq
```

The website only talks to the backend. n8n syncs Gmail, classifies emails with AI and sends replies. The full design is in the report: [RAPPORT.md](RAPPORT.md) (français) or [REPORT.en.md](REPORT.en.md) (English).

## Quick start (demo mode, no Gmail needed)

You need **Docker Desktop**, **Git** and **Python 3** (Python is only used for the n8n setup script).

```bash
git clone <your-repo-url> inbox-assistant
cd inbox-assistant
cp .env.example .env
```

Edit `.env` and replace every `change-me` value. To generate secrets: `openssl rand -hex 32` (or `python -c "import secrets; print(secrets.token_hex(32))"`).

```bash
docker compose up -d --build
docker compose exec backend python -m scripts.seed --classify
```

Open **http://localhost:8080** and sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`.

In demo mode (`GROQ_API_KEY` and `N8N_SEND_WEBHOOK_URL` empty):
- 30 fictional emails are loaded and classified with the expected labels (2 of them simulate invalid AI output, to show the retry and the "To verify" fallback).
- AI drafts use a template, and the day summary is computed without AI.
- Replies are marked "sent" by a mock sender. Set `MOCK_SEND_FAILURE_RATE=0.5` in `.env` (then `docker compose up -d backend`) to see failures and the Retry button.

| URL | What |
|---|---|
| http://localhost:8080 | Website |
| http://localhost:8080/api/docs | API documentation (Swagger) |
| http://localhost:5678 | n8n |

## Going live: Groq + Gmail + n8n

1. **Groq:** create a key at console.groq.com and put it in `GROQ_API_KEY`.
2. **Gmail OAuth:** in Google Cloud (logged in with the *test* Gmail account):
   - Enable the **Gmail API**.
   - OAuth consent screen: **External**, add your test address as a **test user**.
   - Create an **OAuth client ID**, type **Web application**, redirect URI `http://localhost:5678/rest/oauth2-credential/callback`.
   - Put the client ID and secret in `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET`.
3. Restart and load n8n:
   ```bash
   docker compose up -d
   # first visit to http://localhost:5678: create the n8n owner account
   python n8n/setup_n8n.py        # imports the 4 credentials and 4 workflows
   docker compose restart n8n
   ```
4. In n8n: **Credentials > Gmail account > Sign in with Google**. Then open workflows 1, 2 and 3 and switch them to **Active**.
5. In `.env` set `N8N_SEND_WEBHOOK_URL=http://n8n:5678/webhook/send-reply`, then `docker compose up -d backend`.

If the setup script cannot import credentials on your n8n version, create them by hand in n8n (names must match): `Backend webhook secret` and `Send-reply webhook secret` (Header Auth, name `X-Webhook-Secret`), `Groq API key` (Header Auth, name `Authorization`, value `Bearer <key>`), `Gmail account` (Gmail OAuth2). Then import the files from `n8n/workflows/` with **Import from file**.

## Tests

```bash
docker compose exec backend pytest                 # runs on SQLite in memory
docker compose exec backend sh -c 'TEST_DATABASE_URL=$DATABASE_URL pytest'   # on PostgreSQL (wipes the data!)
```

Or locally: `cd backend && pip install -r requirements-dev.txt && pytest`.

The four tests required by the brief:

| Requirement | Test |
|---|---|
| Same email imported twice | `tests/test_import_idempotence.py::test_same_email_imported_twice_is_stored_once` |
| Same reply sent twice | `tests/test_reply_idempotence.py::test_same_reply_sent_twice_is_sent_once` |
| Webhook without / with wrong secret | `tests/test_webhook_security.py` |
| Valid and invalid AI output | `tests/test_classification.py` |

## Measuring results (for the report)

```bash
# AI quality on the 30 demo emails (needs GROQ_API_KEY): validity and accuracy
docker compose exec backend python -m scripts.eval_classification

# Sync duration and first-try validity on real data
# (after a sync of the test inbox, signed in):  http://localhost:8080/api/stats
```

## Project layout

```
backend/            FastAPI app, models, services, tests, scripts (seed, AI eval)
frontend/           React + Vite + Tailwind website (served by nginx in Docker)
n8n/workflows/      Exports of the 4 workflows (no credentials inside)
n8n/setup_n8n.py    Loads credentials from .env and imports the workflows
docker-compose.yml  db + backend + web + n8n
RAPPORT.md          Report in French: architecture, choices, results, limits
REPORT.en.md        The same report in English
```
