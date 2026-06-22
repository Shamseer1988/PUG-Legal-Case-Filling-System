"""Case view audit (Phase 30).

Records who opened which case and when, so an auditor can answer
"who has accessed PUG-LEGAL-2026-0123?". One row per
(user, case, ~5-minute window) so a tab refresh doesn't spam the
log.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CaseView(Base):
    __tablename__ = "case_views"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    ip_address: Mapped[str] = mapped_column(String(45), default="")
