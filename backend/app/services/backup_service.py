"""Backup + restore engine.

Phase 42 swapped the default format from the custom ``.bkp.enc`` tarball
to Postgres ``pg_dump`` custom-format (``.dump``) so files are portable
between PUG apps and Postgres tooling. Attachments are written to a
sidecar ``.files.tar.gz`` next to the dump - pg_dump can't carry the
uploads tree on its own.

The legacy path (JSON serialiser + tar + optional AES-GCM) stays put
for backups that were already on disk before Phase 42 shipped so admins
can still restore them. The restore dispatcher picks the engine by
``BackupJob.format``.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import shutil
import tarfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import Base
from app.models import (  # noqa: F401  - register tables
    AuditLog,
    BackupJob,
    Case,
    CaseAttachment,
    CaseNoSequence,
    CaseStatusUpdate,
    CashRequest,
    CaseType,
    Cheque,
    CourtFiling,
    Customer,
    Division,
    EmailLog,
    Hearing,
    Lawyer,
    Notification,
    Role,
    Salesman,
    ScheduledReport,
    ScheduledReportRun,
    User,
    UserDivisionMap,
    Bank,
    RestoreJob,
)
from app.models.backup import (
    ACT_BACKUP_DAILY,
    ACT_BACKUP_MANUAL,
    ACT_BACKUP_UPLOAD,
    ACT_BACKUP_WEEKLY,
    ACT_CLOUD_PUSH,
    ACT_DELETE,
    ACT_RESTORE,
    BACKUP_FORMAT_LEGACY,
    BACKUP_FORMAT_PGDUMP,
    BACKUP_KIND_DAILY,
    BACKUP_KIND_MANUAL,
    BACKUP_KIND_SAFETY,
    BACKUP_KIND_UPLOAD,
    BACKUP_KIND_WEEKLY,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
    BackupActivityLog,
)
from app.services import crypto_service, pg_tools, r2_service

MANIFEST_VERSION = 1
ENC_SUFFIX = ".bkp.enc"
PLAIN_SUFFIX = ".bkp.tar.gz"
PGDUMP_SUFFIX = ".dump"
SIDECAR_SUFFIX = ".files.tar.gz"
APP_FILENAME_PREFIX = "legal"  # mirrors finance_*.dump from PUG Finance

# Tables this Legal app's pg_dump should contain. Used to reject
# uploads from a different PUG app (e.g. Finance) before they replay.
_LEGAL_SIGNATURE_TABLES = {
    "cases",
    "cheques",
    "court_filings",
    "physical_documents",
    "document_custody_log",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _backups_dir() -> Path:
    p = settings.backup_path
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------- activity log helper ----------------
def log_activity(
    db: Session,
    *,
    activity_type: str,
    status: str = "Success",
    file_name: str = "",
    cloud_key: str = "",
    message: str = "",
    actor_user_id: int | None = None,
    backup_job_id: int | None = None,
) -> BackupActivityLog:
    row = BackupActivityLog(
        activity_type=activity_type,
        status=status,
        file_name=file_name,
        cloud_key=cloud_key,
        message=message,
        actor_user_id=actor_user_id,
        backup_job_id=backup_job_id,
    )
    db.add(row)
    db.commit()
    return row


def list_activity(db: Session, *, limit: int = 200) -> list[BackupActivityLog]:
    return (
        db.query(BackupActivityLog)
        .order_by(BackupActivityLog.occurred_at.desc())
        .limit(limit)
        .all()
    )


# ---------------- attachments sidecar ----------------
def _archive_storage_to(path: Path) -> int:
    """Write the local storage directory to ``path`` as a gzipped tar.
    Returns the number of files archived. Skipped silently when storage
    is empty - admins running test installs may not have uploaded
    anything yet."""
    root = settings.storage_path
    count = 0
    with tarfile.open(path, "w:gz", compresslevel=6) as tar:
        if not root.exists():
            return 0
        for dirpath, _, filenames in os.walk(root):
            for fn in filenames:
                full = Path(dirpath) / fn
                try:
                    arcname = str(full.relative_to(root)).replace(os.sep, "/")
                    tar.add(full, arcname=arcname)
                    count += 1
                except Exception as e:  # pragma: no cover
                    logger.warning("Skipping {}: {}", full, e)
    return count


def _restore_storage_from(path: Path) -> int:
    """Extract a sidecar .tar.gz over the local storage directory.
    Existing files are wiped first so the restore matches the snapshot
    exactly (no left-overs from a later case)."""
    root = settings.storage_path
    if root.exists():
        for child in root.iterdir():
            try:
                if child.is_file() or child.is_symlink():
                    child.unlink()
                else:
                    shutil.rmtree(child, ignore_errors=True)
            except Exception as e:  # pragma: no cover
                logger.warning("Could not clear {}: {}", child, e)
    root.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return 0
    count = 0
    with tarfile.open(path, "r:gz") as tar:
        for member in tar.getmembers():
            # tar traversal guard
            target = (root / member.name).resolve()
            if not str(target).startswith(str(root.resolve())):
                continue
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            f = tar.extractfile(member)
            if not f:
                continue
            with open(target, "wb") as out:
                out.write(f.read())
            count += 1
    return count


# ---------------- pg_dump backup ----------------
def _filename_for(kind: str) -> str:
    """Match Pug Finance naming so the Backup files table is visually
    consistent across the two apps:
    ``legal_<kind>_backup_YYYYMMDD_HHMMSS.dump``.
    """
    stamp = _utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{APP_FILENAME_PREFIX}_{kind}_backup_{stamp}{PGDUMP_SUFFIX}"


def create_pgdump_backup(
    db: Session,
    *,
    kind: str = BACKUP_KIND_MANUAL,
    user_id: int | None = None,
    notes: str = "",
    push_cloud: bool = False,
) -> BackupJob:
    """Run pg_dump to a local file + write an attachments sidecar +
    optionally push to R2. The whole thing is recorded as one BackupJob.
    """
    if not pg_tools.is_postgres():
        raise RuntimeError(
            "Backups require a PostgreSQL database. DATABASE_URL is not a "
            "postgres:// URL on this host."
        )
    pg_tools.assert_binaries_present()

    job = BackupJob(
        kind=kind,
        status=JOB_STATUS_RUNNING,
        format=BACKUP_FORMAT_PGDUMP,
        started_at=_utcnow(),
        is_encrypted=False,
        created_by_id=user_id,
        notes=notes,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        filename = _filename_for(kind)
        dump_path = _backups_dir() / filename
        pg_tools.pg_dump_to_file(dump_path)

        # Per Phase 42 follow-up: attachments sidecar only on weekly
        # (and manual when explicitly requested). Daily runs stay lean
        # so off-site shipping is cheap. Manual is left opt-in via
        # notes for now - the operator who clicks "Backup now" can
        # request a sidecar through the API by sending push_cloud=True
        # OR we treat manual as 'safe default = no sidecar' to match
        # the Finance App behaviour.
        write_sidecar = kind == BACKUP_KIND_WEEKLY
        sidecar_name = ""
        attachment_count = 0
        if write_sidecar:
            sidecar_name = filename.replace(PGDUMP_SUFFIX, SIDECAR_SUFFIX)
            sidecar_path = _backups_dir() / sidecar_name
            attachment_count = _archive_storage_to(sidecar_path)
            sidecar_size = sidecar_path.stat().st_size if sidecar_path.exists() else 0
            if attachment_count == 0 and sidecar_path.exists():
                # Empty tarballs just clutter the listing; drop them.
                sidecar_path.unlink(missing_ok=True)
                sidecar_name = ""
                sidecar_size = 0
        else:
            sidecar_size = 0

        size_total = dump_path.stat().st_size + sidecar_size
        checksum = hashlib.sha256(dump_path.read_bytes()).hexdigest()

        job.storage_path = filename
        job.sidecar_path = sidecar_name
        job.size_bytes = size_total
        job.checksum_sha256 = checksum
        job.attachment_count = attachment_count
        job.manifest = {
            "version": MANIFEST_VERSION,
            "format": BACKUP_FORMAT_PGDUMP,
            "created_at": _utcnow().isoformat(),
            "kind": kind,
            "company": settings.brand_company_name,
            "app": "PUG Legal Case Control System",
            "attachment_count": attachment_count,
        }
        job.status = JOB_STATUS_COMPLETED
        job.finished_at = _utcnow()
        db.commit()
        db.refresh(job)

        act_type = {
            BACKUP_KIND_DAILY: ACT_BACKUP_DAILY,
            BACKUP_KIND_WEEKLY: ACT_BACKUP_WEEKLY,
        }.get(kind, ACT_BACKUP_MANUAL)
        log_activity(
            db,
            activity_type=act_type,
            file_name=filename,
            message=f"Backup completed ({size_total} bytes).",
            actor_user_id=user_id,
            backup_job_id=job.id,
        )

        if push_cloud:
            try:
                key = r2_service.upload_file(db, dump_path)
                job.cloud_path = key
                db.commit()
                log_activity(
                    db,
                    activity_type=ACT_CLOUD_PUSH,
                    file_name=filename,
                    cloud_key=key,
                    message="Pushed to cloud.",
                    actor_user_id=user_id,
                    backup_job_id=job.id,
                )
            except r2_service.CloudUnavailable as e:
                log_activity(
                    db,
                    activity_type=ACT_CLOUD_PUSH,
                    status="Failed",
                    file_name=filename,
                    message=str(e),
                    actor_user_id=user_id,
                    backup_job_id=job.id,
                )

        logger.info("Backup {} written ({} bytes)", job.id, size_total)
        return job
    except Exception as e:
        job.status = JOB_STATUS_FAILED
        job.error = f"{type(e).__name__}: {e}"
        job.finished_at = _utcnow()
        db.commit()
        logger.exception("Backup {} failed", job.id)
        log_activity(
            db,
            activity_type=ACT_BACKUP_MANUAL,
            status="Failed",
            message=str(e),
            actor_user_id=user_id,
            backup_job_id=job.id,
        )
        raise


# ---------------- public create dispatcher ----------------
def create_backup(
    db: Session,
    *,
    kind: str = BACKUP_KIND_MANUAL,
    user_id: int | None = None,
    notes: str = "",
    push_cloud: bool = False,
) -> BackupJob:
    """Default = pg_dump. The legacy code path is retained for
    safety_snapshot rotation on SQLite test runs (which can't shell
    out to pg_dump)."""
    if pg_tools.is_postgres():
        return create_pgdump_backup(
            db,
            kind=kind,
            user_id=user_id,
            notes=notes,
            push_cloud=push_cloud,
        )
    return _create_legacy_backup(db, kind=kind, user_id=user_id, notes=notes)


# ---------------- list / verify / delete ----------------
def list_backups(db: Session) -> list[BackupJob]:
    return db.query(BackupJob).order_by(BackupJob.id.desc()).all()


def get_backup_or_none(db: Session, backup_id: int) -> BackupJob | None:
    return db.get(BackupJob, backup_id)


def read_backup_file(job: BackupJob) -> bytes:
    """Return the raw bytes of the primary file - works for both
    pg_dump and legacy formats. Used by the Download endpoint."""
    path = _backups_dir() / job.storage_path
    if not path.exists():
        raise FileNotFoundError("Backup file missing from disk")
    return path.read_bytes()


def verify_backup(job: BackupJob) -> dict[str, Any]:
    path = _backups_dir() / job.storage_path
    if not path.exists():
        return {"ok": False, "message": "Backup file missing from disk"}
    if job.format == BACKUP_FORMAT_PGDUMP:
        if not pg_tools.looks_like_pgdump_custom(path):
            return {"ok": False, "message": "File is not a pg_dump custom-format archive"}
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if job.checksum_sha256 and sha != job.checksum_sha256:
            return {
                "ok": False,
                "message": "Checksum mismatch (file modified after creation)",
                "expected_sha256": job.checksum_sha256,
                "actual_sha256": sha,
            }
        return {
            "ok": True,
            "message": "Backup intact (pg_dump custom format).",
            "checksum_sha256": sha,
            "entries": 1,
        }
    return _verify_legacy(job)


def delete_backup(db: Session, job: BackupJob, *, actor_user_id: int | None = None) -> None:
    """Remove a backup job + its on-disk files. Cloud copies stay - the
    operator can clear those from the bucket directly."""
    for fn in (job.storage_path, job.sidecar_path):
        if not fn:
            continue
        p = _backups_dir() / fn
        if p.exists():
            try:
                p.unlink()
            except OSError as e:
                logger.warning("Could not delete {}: {}", p, e)
    file_name = job.storage_path
    db.delete(job)
    db.commit()
    log_activity(
        db,
        activity_type=ACT_DELETE,
        file_name=file_name,
        message="Backup file deleted by admin.",
        actor_user_id=actor_user_id,
    )


# ---------------- pg_restore restore ----------------
def _restore_pgdump_backup(
    db: Session,
    job: BackupJob,
    *,
    user_id: int | None,
    take_safety_snapshot: bool,
) -> RestoreJob:
    """Replay a pg_dump custom-format backup with pg_restore +
    extract its attachments sidecar.

    The safety snapshot is created *before* we touch the DB so even a
    catastrophic pg_restore leaves us a rollback point. ``RestoreJob``
    is recorded by re-querying after pg_restore - the old row inside
    the SQLAlchemy session is moot once pg_restore replays the DB.
    """
    pg_tools.assert_binaries_present()

    safety: BackupJob | None = None
    if take_safety_snapshot:
        safety = create_pgdump_backup(
            db,
            kind=BACKUP_KIND_SAFETY,
            user_id=user_id,
            notes=f"Pre-restore of #{job.id}",
        )
    safety_id = safety.id if safety else None
    backup_id = job.id
    file_name = job.storage_path

    dump_path = _backups_dir() / job.storage_path
    sidecar = (
        _backups_dir() / job.sidecar_path if job.sidecar_path else None
    )

    started_at = _utcnow()
    try:
        # The DB connection currently held by ``db`` will be dropped
        # by pg_restore --clean. Close it first so we don't end up
        # holding a stale session past the wipe.
        db.commit()
        db.close()
        pg_tools.pg_restore_from_file(dump_path)

        # New session against the freshly-restored DB.
        from app.db.session import SessionLocal

        db2 = SessionLocal()
        try:
            if sidecar is not None and sidecar.exists():
                _restore_storage_from(sidecar)

            # The BackupJob row for the snapshot we just restored may
            # exist under a different id after restore (the dump's row
            # set replaced ours). Re-record the restore against the
            # current backup_jobs table so the audit trail continues.
            rj = RestoreJob(
                backup_id=backup_id,
                safety_snapshot_id=safety_id,
                status=JOB_STATUS_COMPLETED,
                started_at=started_at,
                finished_at=_utcnow(),
                tables_restored=len(_LEGAL_SIGNATURE_TABLES),
                rows_restored=0,
                created_by_id=user_id,
            )
            db2.add(rj)
            db2.commit()
            db2.refresh(rj)
            log_activity(
                db2,
                activity_type=ACT_RESTORE,
                file_name=file_name,
                message="Restore completed.",
                actor_user_id=user_id,
                backup_job_id=backup_id,
            )
            return rj
        finally:
            db2.close()
    except Exception as e:
        from app.db.session import SessionLocal

        db2 = SessionLocal()
        try:
            rj = RestoreJob(
                backup_id=backup_id,
                safety_snapshot_id=safety_id,
                status=JOB_STATUS_FAILED,
                started_at=started_at,
                finished_at=_utcnow(),
                error=f"{type(e).__name__}: {e}",
                created_by_id=user_id,
            )
            db2.add(rj)
            db2.commit()
            log_activity(
                db2,
                activity_type=ACT_RESTORE,
                status="Failed",
                file_name=file_name,
                message=str(e),
                actor_user_id=user_id,
                backup_job_id=backup_id,
            )
        finally:
            db2.close()
        logger.exception("Restore from backup {} failed", backup_id)
        raise


class LegacyRestoreDisabled(RuntimeError):
    """Phase 42 retires the legacy ``.bkp.enc`` restore button. The
    file format is kept downloadable for archival reasons but in-app
    restore is gated off - operators who really need it can convert
    offline and re-upload as a ``.dump``."""


def restore_backup(
    db: Session,
    job: BackupJob,
    *,
    user_id: int | None = None,
    take_safety_snapshot: bool = True,
    allow_legacy: bool = False,
) -> RestoreJob:
    """Dispatch by format - new pg_dump path or legacy tar path.

    Legacy restore is gated off by default since the live LXC restore
    was failing on it. Use the legacy code path directly (with
    ``allow_legacy=True``) only from a one-off CLI/admin tool when
    you really need to recover an old ``.bkp.enc`` snapshot.
    """
    if job.format == BACKUP_FORMAT_PGDUMP:
        return _restore_pgdump_backup(
            db, job, user_id=user_id, take_safety_snapshot=take_safety_snapshot
        )
    if not allow_legacy:
        raise LegacyRestoreDisabled(
            "Legacy .bkp.enc backups are kept downloadable for archival "
            "purposes but in-app restore is disabled. Download the file, "
            "convert offline if needed, and use Upload + Restore with the "
            "resulting .dump."
        )
    return _restore_legacy_backup(
        db, job, user_id=user_id, take_safety_snapshot=take_safety_snapshot
    )


# ---------------- Upload + Restore ----------------
def import_uploaded_dump(
    db: Session,
    *,
    filename: str,
    content: bytes,
    user_id: int | None,
) -> BackupJob:
    """Save a ``.dump`` an admin uploaded from their computer into the
    backups folder and register it as a BackupJob so the existing
    Restore flow can pick it up.

    Schema sanity-check: the dump's table-of-contents must include the
    Legal app's signature tables - we won't replay a Finance dump and
    silently wipe the Legal DB.
    """
    if not filename.endswith(PGDUMP_SUFFIX):
        raise ValueError("Only .dump files (pg_dump custom format) are accepted.")
    # Normalise the file name to our pattern so it sorts next to the
    # scheduled ones in the listing.
    safe_name = _filename_for(BACKUP_KIND_UPLOAD)
    dest = _backups_dir() / safe_name
    dest.write_bytes(content)

    if not pg_tools.looks_like_pgdump_custom(dest):
        dest.unlink(missing_ok=True)
        raise ValueError(
            "Uploaded file is not a pg_dump custom-format archive. Make "
            "sure the file was produced with `pg_dump -Fc` (same format "
            "as PUG Finance App backups)."
        )

    toc_tables = pg_tools.list_tables_in_dump(dest)
    missing = _LEGAL_SIGNATURE_TABLES - toc_tables
    if missing:
        dest.unlink(missing_ok=True)
        raise ValueError(
            "Uploaded dump doesn't look like a PUG Legal backup "
            f"(missing tables: {sorted(missing)}). Refusing to restore "
            "to avoid wiping the Legal database with a different app's "
            "dump."
        )

    checksum = hashlib.sha256(content).hexdigest()
    job = BackupJob(
        kind=BACKUP_KIND_UPLOAD,
        status=JOB_STATUS_COMPLETED,
        format=BACKUP_FORMAT_PGDUMP,
        started_at=_utcnow(),
        finished_at=_utcnow(),
        storage_path=safe_name,
        size_bytes=len(content),
        checksum_sha256=checksum,
        is_encrypted=False,
        created_by_id=user_id,
        notes=f"Uploaded {filename}",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    log_activity(
        db,
        activity_type=ACT_BACKUP_UPLOAD,
        file_name=safe_name,
        message=f"Uploaded by admin (source: {filename}).",
        actor_user_id=user_id,
        backup_job_id=job.id,
    )
    return job


# ============================================================
# Legacy .bkp.enc engine - kept verbatim so existing backups
# from before Phase 42 stay restorable. Do NOT use for new jobs.
# ============================================================
def _coerce(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (list, dict)):
        return v
    if isinstance(v, bytes):
        import base64

        return {"__bytes_b64__": base64.b64encode(v).decode()}
    return str(v)


def _serialise_db(db: Session) -> tuple[dict[str, list[dict]], dict[str, int]]:
    tables: dict[str, list[dict]] = {}
    counts: dict[str, int] = {}
    for table in Base.metadata.sorted_tables:
        rows: list[dict] = []
        for row in db.execute(table.select()).mappings():
            rows.append({k: _coerce(v) for k, v in row.items()})
        tables[table.name] = rows
        counts[table.name] = len(rows)
    return tables, counts


def _archive_storage(tar: tarfile.TarFile) -> int:
    root = settings.storage_path
    if not root.exists():
        return 0
    count = 0
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            full = Path(dirpath) / fn
            try:
                arcname = "storage/" + str(full.relative_to(root)).replace(os.sep, "/")
                tar.add(full, arcname=arcname)
                count += 1
            except Exception as e:  # pragma: no cover
                logger.warning("Skipping {}: {}", full, e)
    return count


def _create_legacy_backup(
    db: Session,
    *,
    kind: str = BACKUP_KIND_MANUAL,
    user_id: int | None = None,
    notes: str = "",
) -> BackupJob:
    """Old JSON+tar+optional-AES path. Used only on non-Postgres test
    backends (sqlite)."""
    job = BackupJob(
        kind=kind,
        status=JOB_STATUS_RUNNING,
        format=BACKUP_FORMAT_LEGACY,
        started_at=_utcnow(),
        is_encrypted=crypto_service.encryption_available(),
        created_by_id=user_id,
        notes=notes,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        tables, counts = _serialise_db(db)
        data_bytes = json.dumps(
            {"version": MANIFEST_VERSION, "tables": tables},
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")

        manifest = {
            "version": MANIFEST_VERSION,
            "created_at": _utcnow().isoformat(),
            "kind": kind,
            "job_id": job.id,
            "table_row_counts": counts,
            "encrypted": job.is_encrypted,
        }
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")

        buf = io.BytesIO()
        attachment_count = 0
        with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=6) as tar:
            mf = tarfile.TarInfo("manifest.json")
            mf.size = len(manifest_bytes)
            mf.mtime = int(_utcnow().timestamp())
            tar.addfile(mf, io.BytesIO(manifest_bytes))

            df = tarfile.TarInfo("data.json")
            df.size = len(data_bytes)
            df.mtime = int(_utcnow().timestamp())
            tar.addfile(df, io.BytesIO(data_bytes))

            attachment_count = _archive_storage(tar)

        bundle = buf.getvalue()
        if job.is_encrypted:
            blob = crypto_service.encrypt_bytes(bundle)
            ext = ENC_SUFFIX
        else:
            blob = bundle
            ext = PLAIN_SUFFIX

        stamp = _utcnow().strftime("%Y%m%d-%H%M%S")
        filename = f"backup-{job.id:06d}-{stamp}{ext}"
        path = _backups_dir() / filename
        path.write_bytes(blob)
        checksum = hashlib.sha256(blob).hexdigest()

        job.storage_path = filename
        job.size_bytes = len(blob)
        job.checksum_sha256 = checksum
        job.table_row_counts = counts
        job.attachment_count = attachment_count
        job.manifest = manifest
        job.status = JOB_STATUS_COMPLETED
        job.finished_at = _utcnow()
        db.commit()
        db.refresh(job)
        return job
    except Exception as e:
        job.status = JOB_STATUS_FAILED
        job.error = f"{type(e).__name__}: {e}"
        job.finished_at = _utcnow()
        db.commit()
        raise


def _verify_legacy(job: BackupJob) -> dict[str, Any]:
    try:
        blob = read_backup_file(job)
    except FileNotFoundError as e:
        return {"ok": False, "message": str(e)}
    sha = hashlib.sha256(blob).hexdigest()
    if sha != job.checksum_sha256:
        return {
            "ok": False,
            "message": "Checksum mismatch (file modified after creation)",
            "expected_sha256": job.checksum_sha256,
            "actual_sha256": sha,
        }
    if job.is_encrypted:
        try:
            plain = crypto_service.decrypt_bytes(blob)
        except Exception as e:
            return {"ok": False, "message": f"Decryption failed: {e}"}
        try:
            with tarfile.open(fileobj=io.BytesIO(plain), mode="r:gz") as tar:
                names = set(tar.getnames())
        except Exception as e:
            return {"ok": False, "message": f"Bundle unreadable: {e}"}
    else:
        try:
            with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
                names = set(tar.getnames())
        except Exception as e:
            return {"ok": False, "message": f"Bundle unreadable: {e}"}
    missing = {"manifest.json", "data.json"} - names
    if missing:
        return {"ok": False, "message": f"Missing entries: {sorted(missing)}"}
    return {
        "ok": True,
        "message": "Backup intact (legacy format).",
        "checksum_sha256": sha,
        "entries": len(names),
    }


def _restore_attachments_legacy(tar: tarfile.TarFile) -> None:
    root = settings.storage_path
    if root.exists():
        for child in root.iterdir():
            try:
                if child.is_file() or child.is_symlink():
                    child.unlink()
                else:
                    shutil.rmtree(child, ignore_errors=True)
            except Exception as e:  # pragma: no cover
                logger.warning("Could not clear {}: {}", child, e)
    root.mkdir(parents=True, exist_ok=True)
    for member in tar.getmembers():
        if not member.name.startswith("storage/"):
            continue
        rel = member.name[len("storage/") :]
        target = (root / rel).resolve()
        if not str(target).startswith(str(root.resolve())):
            continue
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        f = tar.extractfile(member)
        if not f:
            continue
        with open(target, "wb") as out:
            out.write(f.read())


def _open_legacy_bundle(job: BackupJob) -> tarfile.TarFile:
    blob = read_backup_file(job)
    if job.is_encrypted:
        blob = crypto_service.decrypt_bytes(blob)
    return tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")


def _restore_legacy_backup(
    db: Session,
    job: BackupJob,
    *,
    user_id: int | None,
    take_safety_snapshot: bool,
) -> RestoreJob:
    """The old JSON-replay restore - retained to recover backups taken
    before Phase 42. The wipe + reinsert mutates the DB outside
    SQLAlchemy's unit-of-work tracking, so we close the caller's
    session and do every step on fresh sessions to keep the bookkeeping
    consistent.
    """
    from app.db.session import SessionLocal

    job_id = job.id
    file_name = job.storage_path
    is_encrypted_flag = job.is_encrypted

    # Hand back the FastAPI session before we touch the DB - any rows
    # still attached to it would otherwise stale-UPDATE after the wipe.
    db.commit()
    db.close()

    safety_id: int | None = None
    if take_safety_snapshot:
        snap_db = SessionLocal()
        try:
            snap_job = (
                snap_db.get(BackupJob, job_id)
            )  # ensure object exists in this session
            if snap_job is None:
                raise RuntimeError("Backup job vanished before snapshot")
            safety = _create_legacy_backup(
                snap_db,
                kind=BACKUP_KIND_SAFETY,
                user_id=user_id,
                notes=f"Pre-restore of #{job_id}",
            )
            safety_id = safety.id
        finally:
            snap_db.close()

    started_at = _utcnow()

    # Re-fetch the backup with a session we own.
    wipe_db = SessionLocal()
    dialect = wipe_db.bind.dialect.name if wipe_db.bind is not None else ""
    tables_restored = 0
    rows_restored = 0
    try:
        # Rebuild a BackupJob handle without keeping it dirty in the
        # session - we only need its blob path.
        fresh_job = wipe_db.get(BackupJob, job_id)
        if fresh_job is None:
            raise RuntimeError(f"Backup #{job_id} not found")
        with _open_legacy_bundle(fresh_job) as tar:
            data_member = tar.extractfile("data.json")
            if not data_member:
                raise ValueError("data.json missing from backup")
            payload = json.loads(data_member.read())
            tables_by_name: dict[str, list[dict]] = payload.get("tables", {})

            # Expunge so the upcoming raw wipe doesn't leave a dangling
            # session image of fresh_job.
            wipe_db.expunge_all()

            if dialect == "postgresql":
                wipe_db.execute(text("SET session_replication_role = replica"))
            elif dialect == "sqlite":
                wipe_db.execute(text("PRAGMA foreign_keys = OFF"))
            try:
                for table in reversed(Base.metadata.sorted_tables):
                    wipe_db.execute(table.delete())
                for table in Base.metadata.sorted_tables:
                    rows = tables_by_name.get(table.name) or []
                    if not rows:
                        continue
                    cols = set(table.c.keys())
                    cleaned = [
                        {k: v for k, v in row.items() if k in cols} for row in rows
                    ]
                    wipe_db.execute(table.insert(), cleaned)
                    tables_restored += 1
                    rows_restored += len(cleaned)
                if dialect == "postgresql":
                    for table in Base.metadata.sorted_tables:
                        if "id" in table.c:
                            wipe_db.execute(
                                text(
                                    "SELECT setval(pg_get_serial_sequence(:t, 'id'), "
                                    "COALESCE((SELECT MAX(id) FROM "
                                    + table.name
                                    + "), 1))"
                                ),
                                {"t": table.name},
                            )
            finally:
                if dialect == "postgresql":
                    wipe_db.execute(text("SET session_replication_role = DEFAULT"))
                elif dialect == "sqlite":
                    wipe_db.execute(text("PRAGMA foreign_keys = ON"))
            wipe_db.commit()
            _restore_attachments_legacy(tar)
    except Exception as e:
        wipe_db.rollback()
        # Record failure on a clean session - the wipe session can't
        # be trusted to insert RestoreJob if it half-committed.
        fail_db = SessionLocal()
        try:
            rj = RestoreJob(
                backup_id=job_id,
                safety_snapshot_id=safety_id,
                status=JOB_STATUS_FAILED,
                started_at=started_at,
                finished_at=_utcnow(),
                error=f"{type(e).__name__}: {e}",
                created_by_id=user_id,
            )
            fail_db.add(rj)
            fail_db.commit()
            log_activity(
                fail_db,
                activity_type=ACT_RESTORE,
                status="Failed",
                file_name=file_name,
                message=str(e),
                actor_user_id=user_id,
                backup_job_id=job_id,
            )
        finally:
            fail_db.close()
        logger.exception("Restore from backup {} failed", job_id)
        raise
    finally:
        wipe_db.close()

    # Record success on a session opened post-wipe so the only state
    # it sees is the new DB image.
    ok_db = SessionLocal()
    try:
        rj = RestoreJob(
            backup_id=job_id,
            safety_snapshot_id=safety_id,
            status=JOB_STATUS_COMPLETED,
            started_at=started_at,
            finished_at=_utcnow(),
            tables_restored=tables_restored,
            rows_restored=rows_restored,
            created_by_id=user_id,
        )
        ok_db.add(rj)
        ok_db.commit()
        ok_db.refresh(rj)
        log_activity(
            ok_db,
            activity_type=ACT_RESTORE,
            file_name=file_name,
            message="Legacy restore completed.",
            actor_user_id=user_id,
            backup_job_id=job_id,
        )
        return rj
    finally:
        ok_db.close()
