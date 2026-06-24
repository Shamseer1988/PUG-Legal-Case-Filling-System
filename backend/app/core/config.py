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

    # SMTP (Phase 5 - admin UI for editing arrives in Phase 10)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_from_email: str = "no-reply@pug.local"
    smtp_from_name: str = "PUG Legal Case Control System"

    # Branding (used by email templates + print views)
    brand_company_name: str = "Paris United Group Holding"
    brand_app_url: str = "http://127.0.0.1:3000"

    # Backup (Phase 9)
    backup_encryption_key: str = ""  # base64-encoded 32 bytes; blank disables encryption

    # Hardening (Phase 12)
    security_headers_enabled: bool = True
    rate_limit_login_per_minute: int = 10
    rate_limit_login_per_hour: int = 100
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def storage_path(self) -> Path:
        return _resolve_data_path(self.storage_local_path)

    @property
    def backup_path(self) -> Path:
        return _resolve_data_path(self.backup_local_path)


_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # core/config.py -> core -> app -> backend


def _resolve_data_path(p: str) -> Path:
    """Anchor relative data paths (storage/, backups/) to the backend
    project root so uploads, attachments and backup bundles end up in
    the same physical directory regardless of the working directory
    uvicorn was launched from. Absolute paths are returned unchanged.
    """
    pp = Path(p)
    if pp.is_absolute():
        return pp.resolve()
    return (_BACKEND_ROOT / pp).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
