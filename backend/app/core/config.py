from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Inbox2Done API"
    api_prefix: str = "/api"
    session_secret_key: str = "development-secret-change-me"
    app_env: str = "development"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6"
    token_encryption_key: str = ""
    stripe_secret_key: str = ""
    stripe_pro_price_id: str = ""
    stripe_webhook_secret: str = ""

    frontend_origin: str = Field(
        default="http://localhost:5173",
        description="Frontend origin allowed to call the API.",
    )

    database_url: str = Field(
        default="postgresql+psycopg://inbox2done:inbox2done_dev@localhost:5432/inbox2done"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:5173/api/auth/google/callback"

    @model_validator(mode="after")
    def validate_security(self):
        if self.token_encryption_key:
            Fernet(self.token_encryption_key.encode())
        if self.app_env == "production":
            if len(self.session_secret_key) < 32 or self.session_secret_key.startswith("replace-"):
                raise ValueError(
                    "Production requires a random SESSION_SECRET_KEY of at least 32 characters."
                )
            if not self.token_encryption_key:
                raise ValueError("Production requires TOKEN_ENCRYPTION_KEY.")
            if not self.frontend_origin.startswith(
                "https://"
            ) or not self.google_redirect_uri.startswith("https://"):
                raise ValueError("Production requires HTTPS frontend and OAuth URLs.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
