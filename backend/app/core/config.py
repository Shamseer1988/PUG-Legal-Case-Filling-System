"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Refuse to boot in production when APP_SECRET_KEY is unset, the dev
# default, or trivially short. A weak key lets anyone forge JWTs.
_WEAK_SECRETS = frozenset({"", "change-me", "changeme", "secret", "password"})
_MIN_PROD_SECRET_LEN = 32


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

    @model_validator(mode="after")
    def _enforce_strong_prod_secret(self) -> "Settings":
        if (self.app_env or "").lower() == "production":
            sec = (self.app_secret_key or "").strip()
            if sec.lower() in _WEAK_SECRETS or len(sec) < _MIN_PROD_SECRET_LEN:
                raise ValueError(
                    "APP_SECRET_KEY must be set to a strong random value "
                    f"(>= {_MIN_PROD_SECRET_LEN} chars) when APP_ENV=production. "
                    "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
                )
        return self

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
