"""Settings key-value store.

Sensitive values are stored as ``ENC:<base64>`` where the bytes after
the prefix are an AES-256-GCM envelope produced by ``crypto_service``.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

ENCRYPTION_PREFIX = "ENC:"


class SettingsKV(Base, TimestampMixin):
    __tablename__ = "settings_kv"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, default="")
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at_explicit: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
