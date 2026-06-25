"""Backup + restore schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class BackupJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    status: str
    format: str
    storage_path: str
    sidecar_path: str
    cloud_path: str
    size_bytes: int
    checksum_sha256: str
    is_encrypted: bool
    table_row_counts: dict[str, int]
    attachment_count: int
    started_at: datetime | None
    finished_at: datetime | None
    error: str
    notes: str
    created_by_id: int | None
    created_at: datetime


class RestoreJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    backup_id: int
    safety_snapshot_id: int | None
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    error: str
    tables_restored: int
    rows_restored: int
    created_at: datetime


class BackupCreatePayload(BaseModel):
    notes: str = ""
    # Phase 42: "Backup now + cloud" button sends this true so the new
    # local file is also pushed to R2 in the same job.
    push_cloud: bool = False


class VerifyResult(BaseModel):
    ok: bool
    message: str
    checksum_sha256: str | None = None
    actual_sha256: str | None = None
    expected_sha256: str | None = None
    entries: int | None = None


class RestoreConfirmPayload(BaseModel):
    confirmation: str  # must equal "RESTORE"
    take_safety_snapshot: bool = True


class BackupStatus(BaseModel):
    encryption_enabled: bool
    backup_count: int
    last_backup_at: datetime | None
    total_size_bytes: int
    folder: str = ""
    folder_writable: bool = True
    free_space_bytes: int = 0
    extras: dict[str, Any] = {}


class BackupActivityRead(BaseModel):
    """Phase 42: row in the Backup Activity Log table."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    occurred_at: datetime
    activity_type: str
    status: str
    file_name: str
    cloud_key: str
    message: str
    actor_user_id: int | None
    backup_job_id: int | None


class R2Object(BaseModel):
    """A backup file currently sitting in the configured R2 bucket."""

    key: str
    name: str
    size: int
    last_modified: str | None = None


class R2TestResult(BaseModel):
    ok: bool
    message: str
    bucket: str | None = None
    prefix: str | None = None
    endpoint: str | None = None


class R2RestorePayload(BaseModel):
    """Body for restoring a backup that lives in R2: we download the
    object, register it as a BackupJob, then run the standard restore."""

    key: str
    confirmation: str
    take_safety_snapshot: bool = True


class BackupSettingsRead(BaseModel):
    """Phase 42: shape of the Backup settings card on the UI."""

    daily_enabled: bool
    daily_time: str  # "HH:MM" UTC
    weekly_enabled: bool
    weekly_day: str  # "Sunday".."Saturday"
    weekly_time: str  # "HH:MM" UTC
    local_folder: str
    cloud_provider: str  # "" | "cloudflare_r2"
    cloud_folder: str  # s3://bucket/prefix


class BackupSettingsUpdate(BaseModel):
    daily_enabled: bool | None = None
    daily_time: str | None = None
    weekly_enabled: bool | None = None
    weekly_day: str | None = None
    weekly_time: str | None = None
    local_folder: str | None = None
    cloud_provider: str | None = None
    cloud_folder: str | None = None
