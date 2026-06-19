"""Backup + restore jobs."""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Kinds
BACKUP_KIND_MANUAL = "manual"
BACKUP_KIND_SCHEDULED = "scheduled"
BACKUP_KIND_SAFETY = "safety_snapshot"

# Statuses
JOB_STATUS_QUEUED = "Queued"
JOB_STATUS_RUNNING = "Running"
JOB_STATUS_COMPLETED = "Completed"
JOB_STATUS_FAILED = "Failed"


class BackupJob(Base, TimestampMixin):
    __tablename__ = "backup_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), default=BACKUP_KIND_MANUAL, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=JOB_STATUS_QUEUED, nullable=False, index=True
    )

    storage_path: Mapped[str] = mapped_column(String(500), default="")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), default="")
    is_encrypted: Mapped[bool] = mapped_column(default=False, nullable=False)

    table_row_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    attachment_count: Mapped[int] = mapped_column(default=0, nullable=False)
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")

    notes: Mapped[str] = mapped_column(String(500), default="")
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class RestoreJob(Base, TimestampMixin):
    __tablename__ = "restore_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    backup_id: Mapped[int] = mapped_column(
        ForeignKey("backup_jobs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    safety_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("backup_jobs.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=JOB_STATUS_QUEUED, nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    tables_restored: Mapped[int] = mapped_column(default=0, nullable=False)
    rows_restored: Mapped[int] = mapped_column(default=0, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
