"""Application settings, read from environment variables (never hard-coded)."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg://inbox:inbox@db:5432/inbox"

    # First user, created at startup if it does not exist yet
    admin_email: str = "admin@example.com"
    admin_password: SecretStr = SecretStr("change-me")

    # Session cookie
    session_ttl_hours: int = 24 * 7
    cookie_secure: bool = False  # set to true behind HTTPS

    # n8n -> backend: shared secret sent in the X-Webhook-Secret header
    webhook_secret: SecretStr = SecretStr("")
    # Optional bonus: HMAC-SHA256 of the raw body in X-Signature
    webhook_hmac_secret: SecretStr = SecretStr("")

    # backend -> n8n: send-reply webhook
    n8n_send_webhook_url: str = ""  # empty => mock sender (demo mode)
    n8n_webhook_secret: SecretStr = SecretStr("")
    mock_send_delay_seconds: float = 1.5
    mock_send_failure_rate: float = Field(default=0.0, ge=0, le=1)  # demo the Retry button

    # AI (Groq, OpenAI-compatible API)
    groq_api_key: SecretStr = SecretStr("")  # empty => mock AI (demo mode)
    groq_base_url: str = "https://api.groq.com/openai/v1"
    classify_model: str = "openai/gpt-oss-20b"
    draft_model: str = "openai/gpt-oss-120b"
    ai_timeout_seconds: float = 30.0
    ai_max_retries: int = 3

    # Sync: overlap applied to the cursor so no email is missed at the edges
    sync_overlap_seconds: int = Field(default=300, ge=0)

    @property
    def ai_enabled(self) -> bool:
        return bool(self.groq_api_key.get_secret_value())

    @property
    def mock_sender(self) -> bool:
        return not self.n8n_send_webhook_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
