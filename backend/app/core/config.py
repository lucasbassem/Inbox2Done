from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Inbox2Done API"
    api_prefix: str = "/api"
    session_secret_key: str = "development-secret-change-me"
    app_env: str = "development"

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
    google_redirect_uri: str = "http://127.0.0.1:8000/api/auth/google/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = Settings()
