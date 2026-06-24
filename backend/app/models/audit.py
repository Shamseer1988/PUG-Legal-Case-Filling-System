"""Append-only audit log with a SHA-256 hash chain."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    """One row per mutation. ``prev_hash`` + ``row_hash`` form the chain."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_email: Mapped[str] = mapped_column(String(255), default="")
    actor_role: Mapped[str] = mapped_column(String(100), default="")
    ip_address: Mapped[str] = mapped_column(String(45), default="")
    user_agent: Mapped[str] = mapped_column(String(500), default="")

    action: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    summary: Mapped[str] = mapped_column(String(500), default="")

    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    # SQLAlchemy reserves "metadata"; keep the column name for SQL but expose as meta on the model
    meta: Mapped[dict] = mapped_column("meta", JSON, default=dict)

    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
