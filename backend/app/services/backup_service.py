"""DB-row + attachment archive backup with optional AES-256-GCM encryption.

Bundle layout (inside the tar.gz, before encryption):

    manifest.json
    data.json
    storage/<case_id>/<file>...

Encrypted backups have the file extension ``.bkp.enc`` and contain the
AES-GCM envelope produced by :mod:`crypto_service`.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
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
    BACKUP_KIND_MANUAL,
    BACKUP_KIND_SAFETY,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
)
from app.services import crypto_service

MANIFEST_VERSION = 1
ENC_SUFFIX = ".bkp.enc"
PLAIN_SUFFIX = ".bkp.tar.gz"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _backups_dir() -> Path:
    p = settings.backup_path
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------- helpers ----------------
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
    """Return (tables_dict, row_counts) ordered by FK dependency."""
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
    """Add the local storage directory to the tar; return file count."""
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


# ---------------- create ----------------
def create_backup(
    db: Session,
    *,
    kind: str = BACKUP_KIND_MANUAL,
    user_id: int | None = None,
    notes: str = "",
) -> BackupJob:
    job = BackupJob(
        kind=kind,
        status=JOB_STATUS_RUNNING,
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
            "company": settings.brand_company_name,
            "app": "PUG Legal Case Control System",
            "encrypted": job.is_encrypted,
        }
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")

        # Build tar.gz in memory
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
        logger.info(
            "Backup {} written ({} bytes, encrypted={})",
            job.id,
            job.size_bytes,
            job.is_encrypted,
        )
        return job
    except Exception as e:
        job.status = JOB_STATUS_FAILED
        job.error = f"{type(e).__name__}: {e}"
        job.finished_at = _utcnow()
        db.commit()
        logger.exception("Backup {} failed", job.id)
        raise


# ---------------- read / verify ----------------
def list_backups(db: Session) -> list[BackupJob]:
    return db.query(BackupJob).order_by(BackupJob.id.desc()).all()


def get_backup_or_none(db: Session, backup_id: int) -> BackupJob | None:
    return db.get(BackupJob, backup_id)


def read_backup_file(job: BackupJob) -> bytes:
    path = _backups_dir() / job.storage_path
    if not path.exists():
        raise FileNotFoundError("Backup file missing from disk")
    return path.read_bytes()


def verify_backup(job: BackupJob) -> dict[str, Any]:
    """Check the on-disk file's checksum and, if encrypted, that we can
    decrypt it.

    Returns ``{ok, message, ...}``.
    """
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
        # Confirm the bundle is a valid tar.gz with the expected entries
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
        "message": "Backup intact",
        "checksum_sha256": sha,
        "entries": len(names),
    }


# ---------------- delete ----------------
def delete_backup(db: Session, job: BackupJob) -> None:
    path = _backups_dir() / job.storage_path
    if path.exists():
        path.unlink()
    db.delete(job)
    db.commit()


# ---------------- restore ----------------
def _open_bundle(job: BackupJob) -> tarfile.TarFile:
    blob = read_backup_file(job)
    if job.is_encrypted:
        blob = crypto_service.decrypt_bytes(blob)
    return tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")


def _restore_attachments(tar: tarfile.TarFile) -> None:
    """Extract any ``storage/...`` entries to the local storage path,
    replacing the current attachments tree."""
    root = settings.storage_path
    # Wipe existing storage so the restore is exact
    if root.exists():
        for child in root.iterdir():
            try:
                if child.is_file() or child.is_symlink():
                    child.unlink()
                else:
                    import shutil

                    shutil.rmtree(child, ignore_errors=True)
            except Exception as e:  # pragma: no cover
                logger.warning("Could not clear {}: {}", child, e)
    root.mkdir(parents=True, exist_ok=True)
    for member in tar.getmembers():
        if not member.name.startswith("storage/"):
            continue
        # Avoid tar traversal
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


def restore_backup(
    db: Session,
    job: BackupJob,
    *,
    user_id: int | None = None,
    take_safety_snapshot: bool = True,
) -> RestoreJob:
    """Destructive: wipes all tables and replays the backup contents.

    A safety snapshot of the *current* state is captured first by
    default and recorded as the restore-job's safety_snapshot_id.
    """
    safety: BackupJob | None = None
    if take_safety_snapshot:
        safety = create_backup(
            db, kind=BACKUP_KIND_SAFETY, user_id=user_id, notes=f"Pre-restore of #{job.id}"
        )

    rj = RestoreJob(
        backup_id=job.id,
        safety_snapshot_id=safety.id if safety else None,
        status=JOB_STATUS_RUNNING,
        started_at=_utcnow(),
        created_by_id=user_id,
    )
    db.add(rj)
    db.commit()
    db.refresh(rj)

    dialect = db.bind.dialect.name if db.bind is not None else ""

    try:
        with _open_bundle(job) as tar:
            data_member = tar.extractfile("data.json")
            if not data_member:
                raise ValueError("data.json missing from backup")
            payload = json.loads(data_member.read())
            tables_by_name: dict[str, list[dict]] = payload.get("tables", {})

            # Disable FK enforcement
            if dialect == "postgresql":
                db.execute(text("SET session_replication_role = replica"))
            elif dialect == "sqlite":
                db.execute(text("PRAGMA foreign_keys = OFF"))

            try:
                # Wipe in reverse FK order
                for table in reversed(Base.metadata.sorted_tables):
                    db.execute(table.delete())

                # Load in forward order
                tables_restored = 0
                rows_restored = 0
                for table in Base.metadata.sorted_tables:
                    rows = tables_by_name.get(table.name) or []
                    if not rows:
                        continue
                    # Only keep columns that still exist (forward-compat)
                    cols = set(table.c.keys())
                    cleaned = [
                        {k: v for k, v in row.items() if k in cols} for row in rows
                    ]
                    db.execute(table.insert(), cleaned)
                    tables_restored += 1
                    rows_restored += len(cleaned)

                # Reset Postgres sequences so future inserts don't collide
                if dialect == "postgresql":
                    for table in Base.metadata.sorted_tables:
                        if "id" in table.c:
                            db.execute(
                                text(
                                    "SELECT setval(pg_get_serial_sequence(:t, 'id'), "
                                    "COALESCE((SELECT MAX(id) FROM " + table.name + "), 1))"
                                ),
                                {"t": table.name},
                            )
            finally:
                if dialect == "postgresql":
                    db.execute(text("SET session_replication_role = DEFAULT"))
                elif dialect == "sqlite":
                    db.execute(text("PRAGMA foreign_keys = ON"))

            db.commit()

            # Replay attachments
            _restore_attachments(tar)

            rj.status = JOB_STATUS_COMPLETED
            rj.tables_restored = tables_restored
            rj.rows_restored = rows_restored
            rj.finished_at = _utcnow()
            db.add(rj)  # rj may have been detached by the wipe above
            db.commit()
            db.refresh(rj)
    except Exception as e:
        rj.status = JOB_STATUS_FAILED
        rj.error = f"{type(e).__name__}: {e}"
        rj.finished_at = _utcnow()
        db.add(rj)
        db.commit()
        logger.exception("Restore from backup {} failed", job.id)
        raise

    return rj
