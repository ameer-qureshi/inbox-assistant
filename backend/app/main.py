"""FastAPI application entry point. Swagger docs: /api/docs"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from app.api import auth, emails, webhooks
from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.models import User
from app.security import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# Never log request bodies or headers (secrets, email content)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("app")


def init_db() -> None:
    Base.metadata.create_all(engine)
    s = get_settings()
    with SessionLocal() as db:
        email = s.admin_email.lower().strip()
        if not db.scalar(select(User).where(User.email == email)):
            db.add(User(email=email, password_hash=hash_password(s.admin_password.get_secret_value())))
            db.commit()
            log.info("Created initial user")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    s = get_settings()
    if not s.webhook_secret.get_secret_value():
        log.warning("WEBHOOK_SECRET is empty: all webhook calls will be refused")
    log.info("AI mode: %s | send mode: %s", "groq" if s.ai_enabled else "demo",
             "mock" if s.mock_sender else "n8n")
    yield


app = FastAPI(
    title="Inbox Assistant API",
    version="1.0.0",
    description="Backend between the web app and n8n. User routes need a session cookie; "
                "`/webhooks/*` routes need the `X-Webhook-Secret` header.",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

for r in (auth.router, emails.router, webhooks.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}
