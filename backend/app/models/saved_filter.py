"""Saved report filters (Phase 27).

A SavedReportFilter is a named combination of report parameters a
user can re-apply with one click. Users can keep their filters
private (default) or mark them ``is_public`` so teammates see them
on the same report.
"""

from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class SavedReportFilter(Base, TimestampMixin):
    __tablename__ = "saved_report_filters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    report_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    is_public: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )

    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
