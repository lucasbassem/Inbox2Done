from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Inbox2Done API"
    app_environment: str = "development"
    api_prefix: str = "/api"

    frontend_origin: str = Field(
        default="http://localhost:5173",
        description="Frontend origin allowed to call the API.",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
