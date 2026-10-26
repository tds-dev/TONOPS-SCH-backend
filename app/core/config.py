"""Application settings, read from environment variables or a .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./scheduler_dev.db"
    cors_origins: str = "http://localhost:4200"
    worker_poll_seconds: float = 2.0
    # Used for CreatedBy / UpdatedBy until authentication is added.
    default_user: str = "system"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
