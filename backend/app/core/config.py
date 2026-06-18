"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "PUG Legal Case Control System"
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_secret_key: str = Field(default="change-me", min_length=8)

    # Database
    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/pug_legal"

    # Redis
    redis_url: str = "redis://127.0.0.1:6379/0"

    # JWT
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 60
    jwt_refresh_ttl_days: int = 14

    # Storage
    storage_backend: str = "local"
    storage_local_path: str = "../storage"
    backup_local_path: str = "../backups"

    # CORS
    cors_origins: str = "http://127.0.0.1:3000,http://localhost:3000"

    # Logging
    log_level: str = "INFO"
    log_json: bool = False

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_local_path).resolve()

    @property
    def backup_path(self) -> Path:
        return Path(self.backup_local_path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
