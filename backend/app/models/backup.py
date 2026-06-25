"""Backup + restore jobs."""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Kinds
BACKUP_KIND_MANUAL = "manual"
BACKUP_KIND_SCHEDULED = "scheduled"
BACKUP_KIND_DAILY = "daily"
BACKUP_KIND_WEEKLY = "weekly"
BACKUP_KIND_SAFETY = "safety_snapshot"
BACKUP_KIND_UPLOAD = "upload"

# Formats - Phase 42 introduced pg_dump-based backups; legacy_enc is
# the old tar+AES-GCM bundle. The restore dispatcher branches on this.
BACKUP_FORMAT_PGDUMP = "pgdump"
BACKUP_FORMAT_LEGACY = "legacy_enc"

# Statuses
JOB_STATUS_QUEUED = "Queued"
JOB_STATUS_RUNNING = "Running"
JOB_STATUS_COMPLETED = "Completed"
JOB_STATUS_FAILED = "Failed"

# Backup activity log activity types
ACT_BACKUP_DAILY = "Daily"
ACT_BACKUP_WEEKLY = "Weekly"
ACT_BACKUP_MANUAL = "Manual"
ACT_BACKUP_UPLOAD = "Upload"
ACT_RESTORE = "Restore"
ACT_DELETE = "Delete"
ACT_CLOUD_PUSH = "CloudPush"


class BackupJob(Base, TimestampMixin):
    __tablename__ = "backup_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), default=BACKUP_KIND_MANUAL, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=JOB_STATUS_QUEUED, nullable=False, index=True
    )
    # Phase 42: format identifies which engine produced this backup
    # so restore can dispatch to pg_restore or the legacy tar path.
    format: Mapped[str] = mapped_column(
        String(20), default=BACKUP_FORMAT_PGDUMP, nullable=False
    )

    storage_path: Mapped[str] = mapped_column(String(500), default="")
    # Optional second file holding the attachments tree (.tar.gz) for
    # pgdump backups; pg_dump can't carry uploads on its own.
    sidecar_path: Mapped[str] = mapped_column(String(500), default="")
    # Object key inside the configured R2/S3 bucket if the dump was
    # pushed off-site (weekly job or "Backup now + cloud" button).
    cloud_path: Mapped[str] = mapped_column(String(500), default="")
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


class BackupActivityLog(Base, TimestampMixin):
    """Phase 42: every backup/restore/delete/cloud-push event so the
    "Backup activity log" panel on the Backup & Restore page can show
    a Finance-style timeline."""

    __tablename__ = "backup_activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True
    )
    activity_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="Success", nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), default="")
    cloud_key: Mapped[str] = mapped_column(String(500), default="")
    message: Mapped[str] = mapped_column(String(1000), default="")
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    backup_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("backup_jobs.id", ondelete="SET NULL"), nullable=True
    )
