"""Backup + restore endpoints (Phase 42 rewrite).

Surface stayed source-compatible with the existing UI so older clients
keep working while we ship the new screen:
- ``GET /backups`` - list
- ``POST /backups`` - create (now pg_dump by default; ``push_cloud``
  controls the "Backup now + cloud" path)
- ``GET /backups/{id}/download`` - serve the .dump (or legacy .enc)
- ``POST /backups/{id}/restore`` - dispatcher branches by format
- ``DELETE /backups/{id}`` - delete record + on-disk files

New endpoints for the rebuilt screen:
- ``POST /backups/upload-restore`` - admin uploads a .dump from
  their PC and we register + restore in one shot
- ``GET /backups/activity`` - paginated activity log
- ``GET /backups/r2`` - list off-site backups
- ``POST /backups/r2/test`` - HEAD the bucket to confirm credentials
- ``POST /backups/r2/restore`` - download an R2 object then restore
- ``GET /backups/settings`` / ``PUT /backups/settings`` - schedule +
  cloud config
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings as app_settings
from app.core.deps import require_permission
from app.core.permissions import ADMIN_BACKUP
from app.db.session import get_db
from app.models.backup import BackupJob
from app.models.user import User
from app.schemas.backup import (
    BackupActivityRead,
    BackupCreatePayload,
    BackupJobRead,
    BackupSettingsRead,
    BackupSettingsUpdate,
    BackupStatus,
    R2Object,
    R2RestorePayload,
    R2TestResult,
    RestoreConfirmPayload,
    RestoreJobRead,
    VerifyResult,
)
from app.services import (
    audit_service,
    backup_service,
    crypto_service,
    pg_tools,
    r2_service,
    settings_service,
)

router = APIRouter(prefix="/backups", tags=["backups"])

WEEKDAY_LABELS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def _get_or_404(db: Session, backup_id: int) -> BackupJob:
    job = backup_service.get_backup_or_none(db, backup_id)
    if not job:
        raise HTTPException(status_code=404, detail="Backup not found")
    return job


def _free_space_bytes(p: Path) -> int:
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return 0


def _folder_writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".write_test"
        probe.write_text("ok")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


# ============================== status / list ==============================
@router.get("/status", response_model=BackupStatus)
def status_endpoint(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_BACKUP)),
) -> BackupStatus:
    rows = backup_service.list_backups(db)
    folder = app_settings.backup_path
    return BackupStatus(
        encryption_enabled=crypto_service.encryption_available(),
        backup_count=len(rows),
        last_backup_at=rows[0].finished_at if rows else None,
        total_size_bytes=sum(r.size_bytes for r in rows),
        folder=str(folder),
        folder_writable=_folder_writable(folder),
        free_space_bytes=_free_space_bytes(folder),
    )


@router.get("", response_model=list[BackupJobRead])
def list_backups(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_BACKUP)),
) -> list[BackupJobRead]:
    # Reconcile DB records with actual files on disk before listing.
    # This is cheap (one directory scan) and guarantees the sizes /
    # filenames shown in the UI match reality — critical after a
    # pg_restore that replaced the backup_jobs table.
    try:
        backup_service.sync_disk_files(db)
    except Exception as exc:
        # sync is best-effort — never block listing because of it.
        from loguru import logger
        logger.warning("sync_disk_files failed during list: {}", exc)
    return [BackupJobRead.model_validate(r) for r in backup_service.list_backups(db)]


@router.post("/sync", response_model=list[BackupJobRead])
def sync_disk(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_BACKUP)),
) -> list[BackupJobRead]:
    """Explicitly reconcile backup_jobs with files on disk."""
    backup_service.sync_disk_files(db)
    return [BackupJobRead.model_validate(r) for r in backup_service.list_backups(db)]


@router.get("/activity", response_model=list[BackupActivityRead])
def list_activity(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_BACKUP)),
    limit: int = 200,
) -> list[BackupActivityRead]:
    return [
        BackupActivityRead.model_validate(r)
        for r in backup_service.list_activity(db, limit=limit)
    ]


# ============================== create ==============================
@router.post("", response_model=BackupJobRead, status_code=status.HTTP_201_CREATED)
def create_backup(
    payload: BackupCreatePayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ADMIN_BACKUP)),
) -> BackupJobRead:
    try:
        job = backup_service.create_backup(
            db,
            user_id=user.id,
            notes=payload.notes or "",
            push_cloud=payload.push_cloud,
        )
    except RuntimeError as e:
        # pg_dump missing / not Postgres
        raise HTTPException(status_code=400, detail=str(e)) from e
    audit_service.record_event(
        db,
        action=audit_service.ACTION_BACKUP,
        entity_type="BackupJob",
        entity_id=job.id,
        summary=(
            f"Created backup #{job.id} ({job.size_bytes} bytes, format={job.format})"
        ),
        after={
            "size_bytes": job.size_bytes,
            "checksum": job.checksum_sha256,
            "format": job.format,
            "cloud_path": job.cloud_path,
        },
        actor=user,
        commit=True,
    )
    return BackupJobRead.model_validate(job)


# ============================== Backup schedule settings (declared first) ==
# FastAPI matches routes in registration order. The variable-path
# ``/backups/{backup_id}`` would otherwise eat ``/backups/settings`` and
# ``/backups/r2`` and produce 422 errors. Keeping the static-path
# endpoints above ``/{backup_id}`` is the simplest fix.
def _settings_to_dto(db: Session) -> BackupSettingsRead:
    return BackupSettingsRead(
        daily_enabled=settings_service.get_bool(db, "backup.daily_enabled", False),
        daily_time=settings_service.get_str(db, "backup.daily_time", "23:00"),
        weekly_enabled=settings_service.get_bool(db, "backup.weekly_enabled", False),
        weekly_day=settings_service.get_str(db, "backup.weekly_day", "Sunday"),
        weekly_time=settings_service.get_str(db, "backup.weekly_time", "23:30"),
        local_folder=settings_service.get_str(db, "backup.local_folder", ""),
        cloud_provider=settings_service.get_str(db, "backup.cloud_provider", ""),
        cloud_folder=settings_service.get_str(db, "backup.cloud_folder", ""),
    )


@router.get("/settings", response_model=BackupSettingsRead)
def get_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_BACKUP)),
) -> BackupSettingsRead:
    return _settings_to_dto(db)


@router.put("/settings", response_model=BackupSettingsRead)
def put_settings(
    payload: BackupSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ADMIN_BACKUP)),
) -> BackupSettingsRead:
    pairs = payload.model_dump(exclude_unset=True)
    if "daily_time" in pairs and not _valid_hhmm(pairs["daily_time"]):
        raise HTTPException(status_code=400, detail="daily_time must be HH:MM (24h, UTC)")
    if "weekly_time" in pairs and not _valid_hhmm(pairs["weekly_time"]):
        raise HTTPException(status_code=400, detail="weekly_time must be HH:MM (24h, UTC)")
    if "weekly_day" in pairs and pairs["weekly_day"] not in WEEKDAY_LABELS:
        raise HTTPException(
            status_code=400,
            detail=f"weekly_day must be one of {WEEKDAY_LABELS}",
        )
    for k, v in pairs.items():
        settings_service.set_value(
            db,
            f"backup.{k}",
            str(v) if not isinstance(v, str) else v,
            user_id=user.id,
        )
    db.commit()
    # Re-arm scheduler with the new schedule.
    from app.services import scheduler_service

    scheduler_service.refresh_backup_schedule()
    return _settings_to_dto(db)


def _valid_hhmm(s: str) -> bool:
    try:
        h, m = s.split(":")
        return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
    except (ValueError, AttributeError):
        return False


# ============================== R2 / Cloud (declared above {backup_id}) =====
@router.post("/r2/test", response_model=R2TestResult)
def r2_test(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_BACKUP)),
) -> R2TestResult:
    return R2TestResult(**r2_service.test_connection(db))


@router.get("/r2", response_model=list[R2Object])
def r2_list(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_BACKUP)),
) -> list[R2Object]:
    return [R2Object(**o) for o in r2_service.list_objects(db)]


@router.post("/r2/restore", response_model=RestoreJobRead)
def r2_restore(
    payload: R2RestorePayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ADMIN_BACKUP)),
) -> RestoreJobRead:
    user_id = user.id if user else None
    if payload.confirmation != "RESTORE":
        raise HTTPException(
            status_code=400,
            detail='Type "RESTORE" in the confirmation field to proceed',
        )
    # Download to a temp file inside the backups folder so it sorts
    # next to the other local files in the listing.
    dest = backup_service._backups_dir() / f"r2_pulled_{payload.key.rsplit('/', 1)[-1]}"
    try:
        r2_service.download_object(db, payload.key, dest)
    except r2_service.CloudUnavailable as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    content = dest.read_bytes()
    dest.unlink(missing_ok=True)

    try:
        job = backup_service.import_uploaded_dump(
            db, filename=payload.key, content=content, user_id=user_id
        )
        rj = backup_service.restore_backup(
            db, job,
            user_id=user_id,
            take_safety_snapshot=payload.take_safety_snapshot,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Restore from R2 failed: {e}"
        ) from e

    from app.db.session import SessionLocal
    audit_db = SessionLocal()
    try:
        from app.models.user import User as DBUser
        actor_user = audit_db.get(DBUser, user_id) if user_id else None
        audit_service.record_event(
            audit_db,
            action=audit_service.ACTION_RESTORE,
            entity_type="BackupJob",
            entity_id=rj.backup_id,
            summary=f"Restored from R2 object {payload.key}",
            actor=actor_user,
            commit=True,
        )
    finally:
        audit_db.close()

    return RestoreJobRead.model_validate(rj)


# ============================== Upload + Restore (static path) ===============
@router.post("/upload-restore", response_model=RestoreJobRead)
async def upload_and_restore(
    confirmation: str = "",
    take_safety_snapshot: bool = True,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ADMIN_BACKUP)),
) -> RestoreJobRead:
    """Accept a ``.dump`` upload from the operator's PC and run the
    standard restore pipeline against it. The file is validated for
    pg_dump format + Legal-app schema first, so a Finance backup
    can't accidentally wipe the Legal DB.
    """
    user_id = user.id if user else None
    if confirmation != "RESTORE":
        raise HTTPException(
            status_code=400,
            detail='Type "RESTORE" in the confirmation field to proceed',
        )
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        job = backup_service.import_uploaded_dump(
            db, filename=file.filename, content=content, user_id=user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        rj = backup_service.restore_backup(
            db, job, user_id=user_id, take_safety_snapshot=take_safety_snapshot
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Restore failed after upload: {e}"
        ) from e

    from app.db.session import SessionLocal
    audit_db = SessionLocal()
    try:
        from app.models.user import User as DBUser
        actor_user = audit_db.get(DBUser, user_id) if user_id else None
        audit_service.record_event(
            audit_db,
            action=audit_service.ACTION_RESTORE,
            entity_type="BackupJob",
            entity_id=rj.backup_id,
            summary=f"Uploaded & restored backup ({file.filename})",
            actor=actor_user,
            commit=True,
        )
    finally:
        audit_db.close()

    return RestoreJobRead.model_validate(rj)


# ============================== single backup (variable path - last) ========
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
        media_type="application/octet-stream",
    )


@router.delete("/{backup_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backup(
    backup_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ADMIN_BACKUP)),
) -> None:
    job = _get_or_404(db, backup_id)
    try:
        audit_service.record_event(
            db,
            action="backup_deleted",
            entity_type="BackupJob",
            entity_id=job.id,
            summary=f"Deleted backup #{job.id} ({job.storage_path})",
            actor=user,
            commit=True,
        )
        backup_service.delete_backup(db, job, actor_user_id=user.id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Delete failed: {e}",
        ) from e


# ============================== restore ==============================
@router.post("/{backup_id}/restore", response_model=RestoreJobRead)
def restore_backup(
    backup_id: int,
    payload: RestoreConfirmPayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ADMIN_BACKUP)),
) -> RestoreJobRead:
    user_id = user.id if user else None
    if payload.confirmation != "RESTORE":
        raise HTTPException(
            status_code=400,
            detail='Type "RESTORE" in the confirmation field to proceed',
        )
    job = _get_or_404(db, backup_id)
    try:
        rj = backup_service.restore_backup(
            db, job,
            user_id=user_id,
            take_safety_snapshot=payload.take_safety_snapshot,
            allow_legacy=not pg_tools.is_postgres(),
        )
    except backup_service.LegacyRestoreDisabled as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        # Empty storage_path or invalid backup
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {e}") from e

    from app.db.session import SessionLocal
    audit_db = SessionLocal()
    try:
        from app.models.user import User as DBUser
        actor_user = audit_db.get(DBUser, user_id) if user_id else None
        audit_service.record_event(
            audit_db,
            action=audit_service.ACTION_RESTORE,
            entity_type="BackupJob",
            entity_id=rj.backup_id,
            summary=f"Restored backup #{rj.backup_id}",
            actor=actor_user,
            commit=True,
        )
    finally:
        audit_db.close()

    return RestoreJobRead.model_validate(rj)

