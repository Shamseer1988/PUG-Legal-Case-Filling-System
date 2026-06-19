"""Backup + restore schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class BackupJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    status: str
    storage_path: str
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
    extras: dict[str, Any] = {}
