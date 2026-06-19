"""Backup + restore endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import require_permission
from app.core.permissions import ADMIN_BACKUP
from app.db.session import get_db
from app.models.backup import BackupJob
from app.models.user import User
from app.schemas.backup import (
    BackupCreatePayload,
    BackupJobRead,
    BackupStatus,
    RestoreConfirmPayload,
    RestoreJobRead,
    VerifyResult,
)
from app.services import audit_service, backup_service, crypto_service

router = APIRouter(prefix="/backups", tags=["backups"])


def _get_or_404(db: Session, backup_id: int) -> BackupJob:
    job = backup_service.get_backup_or_none(db, backup_id)
    if not job:
        raise HTTPException(status_code=404, detail="Backup not found")
    return job


@router.get("/status", response_model=BackupStatus)
def status_endpoint(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_BACKUP)),
) -> BackupStatus:
    rows = backup_service.list_backups(db)
    return BackupStatus(
        encryption_enabled=crypto_service.encryption_available(),
        backup_count=len(rows),
        last_backup_at=rows[0].finished_at if rows else None,
        total_size_bytes=sum(r.size_bytes for r in rows),
    )


@router.get("", response_model=list[BackupJobRead])
def list_backups(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_BACKUP)),
) -> list[BackupJobRead]:
    return [BackupJobRead.model_validate(r) for r in backup_service.list_backups(db)]


@router.post("", response_model=BackupJobRead, status_code=status.HTTP_201_CREATED)
def create_backup(
    payload: BackupCreatePayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ADMIN_BACKUP)),
) -> BackupJobRead:
    job = backup_service.create_backup(
        db, user_id=user.id, notes=payload.notes or ""
    )
    audit_service.record_event(
        db,
        action=audit_service.ACTION_BACKUP,
        entity_type="BackupJob",
        entity_id=job.id,
        summary=(
            f"Created backup #{job.id} ({job.size_bytes} bytes, "
            f"encrypted={job.is_encrypted})"
        ),
        after={
            "size_bytes": job.size_bytes,
            "checksum": job.checksum_sha256,
            "encrypted": job.is_encrypted,
            "row_counts": job.table_row_counts,
        },
        actor=user,
        commit=True,
    )
    return BackupJobRead.model_validate(job)


@router.get("/{backup_id}", response_model=BackupJobRead)
def get_backup(
    backup_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_BACKUP)),
) -> BackupJobRead:
    return BackupJobRead.model_validate(_get_or_404(db, backup_id))


@router.get("/{backup_id}/verify", response_model=VerifyResult)
def verify_backup(
    backup_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_BACKUP)),
) -> VerifyResult:
    job = _get_or_404(db, backup_id)
    return VerifyResult(**backup_service.verify_backup(job))


@router.get("/{backup_id}/download")
def download_backup(
    backup_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ADMIN_BACKUP)),
):
    job = _get_or_404(db, backup_id)
    path = backup_service._backups_dir() / job.storage_path
    if not path.exists():
        raise HTTPException(status_code=410, detail="Backup file missing on disk")
    audit_service.record_event(
        db,
        action="backup_downloaded",
        entity_type="BackupJob",
        entity_id=job.id,
        summary=f"Downloaded backup #{job.id}",
        actor=user,
        commit=True,
    )
    return FileResponse(
        path,
        filename=job.storage_path,
        media_type=("application/octet-stream" if job.is_encrypted else "application/gzip"),
    )


@router.delete("/{backup_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backup(
    backup_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ADMIN_BACKUP)),
) -> None:
    job = _get_or_404(db, backup_id)
    audit_service.record_event(
        db,
        action="backup_deleted",
        entity_type="BackupJob",
        entity_id=job.id,
        summary=f"Deleted backup #{job.id} ({job.storage_path})",
        actor=user,
        commit=True,
    )
    backup_service.delete_backup(db, job)


@router.post("/{backup_id}/restore", response_model=RestoreJobRead)
def restore_backup(
    backup_id: int,
    payload: RestoreConfirmPayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ADMIN_BACKUP)),
) -> RestoreJobRead:
    if payload.confirmation != "RESTORE":
        raise HTTPException(
            status_code=400,
            detail='Type "RESTORE" in the confirmation field to proceed',
        )
    job = _get_or_404(db, backup_id)
    rj = backup_service.restore_backup(
        db, job, user_id=user.id, take_safety_snapshot=payload.take_safety_snapshot
    )
    # After restore, the audit chain has been overwritten by the snapshot's
    # contents. Append a fresh entry to continue the chain.
    audit_service.record_event(
        db,
        action=audit_service.ACTION_RESTORE,
        entity_type="BackupJob",
        entity_id=job.id,
        summary=(
            f"Restored from backup #{job.id} "
            f"({rj.tables_restored} tables, {rj.rows_restored} rows)"
        ),
        meta={
            "restore_job_id": rj.id,
            "safety_snapshot_id": rj.safety_snapshot_id,
        },
        actor=user,
        commit=True,
    )
    return RestoreJobRead.model_validate(rj)
