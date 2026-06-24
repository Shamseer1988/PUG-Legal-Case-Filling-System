"""Scheduled reports + run history."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

# Run statuses
RUN_STATUS_SUCCESS = "Success"
RUN_STATUS_FAILED = "Failed"

# Schedule last-run statuses
LAST_RUN_NEVER = ""
LAST_RUN_SUCCESS = "Success"
LAST_RUN_FAILED = "Failed"


class ScheduledReport(Base, TimestampMixin):
    __tablename__ = "scheduled_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    report_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)

    cron: Mapped[str] = mapped_column(String(50), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")

    recipients: Mapped[list[str]] = mapped_column(JSON, default=list)
    cc: Mapped[list[str]] = mapped_column(JSON, default=list)
    bcc: Mapped[list[str]] = mapped_column(JSON, default=list)
    formats: Mapped[list[str]] = mapped_column(JSON, default=list)  # xlsx / pdf

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    notes: Mapped[str] = mapped_column(String(500), default="")

    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_status: Mapped[str] = mapped_column(String(20), default=LAST_RUN_NEVER)
    last_run_error: Mapped[str] = mapped_column(Text, default="")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    runs: Mapped[list["ScheduledReportRun"]] = relationship(
        back_populates="schedule",
        cascade="all, delete-orphan",
        order_by="ScheduledReportRun.id.desc()",
        lazy="selectin",
    )


class ScheduledReportRun(Base, TimestampMixin):
    __tablename__ = "scheduled_report_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("scheduled_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    rows_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="")
    email_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("email_log.id", ondelete="SET NULL"), nullable=True
    )

    schedule: Mapped[ScheduledReport] = relationship(back_populates="runs")
