"""Health & Diagnostics for the Admin console."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.core.deps import require_permission
from app.core.permissions import ADMIN_SETTINGS
from app.db.session import get_db
from app.models.backup import BackupJob
from app.models.user import User

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.get("")
def diagnostics(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_SETTINGS)),
) -> dict:
    out: dict = {
        "app": {
            "version": __version__,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        },
        "checks": [],
    }

    # ---- DB ----
    try:
        db.execute(text("SELECT 1"))
        out["checks"].append({"name": "Database", "ok": True, "detail": str(db.bind.dialect.name)})
    except Exception as e:
        out["checks"].append({"name": "Database", "ok": False, "detail": str(e)})

    # ---- Redis (best-effort) ----
    try:
        from app.core.config import settings
        import redis

        # Force RESP2 + skip HELLO so the check works against older Redis
        # builds (e.g. the redis-windows community port) which would
        # otherwise return "unknown command 'HELLO'".
        try:
            client = redis.Redis.from_url(
                settings.redis_url,
                socket_connect_timeout=2,
                socket_timeout=2,
                protocol=2,
            )
        except TypeError:
            # Older redis-py without `protocol` kwarg
            client = redis.Redis.from_url(
                settings.redis_url,
                socket_connect_timeout=2,
                socket_timeout=2,
            )

        try:
            client.ping()
            out["checks"].append(
                {"name": "Redis", "ok": True, "detail": settings.redis_url}
            )
        except redis.exceptions.ResponseError as e:
            msg = str(e).lower()
            if "unknown command" in msg and "hello" in msg:
                # Server is up but pre-Redis-6 - tolerate it.
                out["checks"].append(
                    {
                        "name": "Redis",
                        "ok": True,
                        "detail": (
                            f"{settings.redis_url} (older Redis; consider upgrading to 6+)"
                        ),
                    }
                )
            else:
                out["checks"].append(
                    {"name": "Redis", "ok": False, "detail": str(e)[:200]}
                )
    except Exception as e:
        out["checks"].append({"name": "Redis", "ok": False, "detail": str(e)[:200]})

    # ---- Scheduler (Phase 7) ----
    try:
        from app.services import scheduler_service

        running = scheduler_service._scheduler is not None and (
            scheduler_service._scheduler.running  # type: ignore[union-attr]
        )
        out["checks"].append(
            {"name": "Scheduler", "ok": bool(running), "detail": "BackgroundScheduler"}
        )
    except Exception as e:
        out["checks"].append({"name": "Scheduler", "ok": False, "detail": str(e)})

    # ---- Last backup ----
    try:
        latest = (
            db.query(BackupJob).order_by(BackupJob.id.desc()).limit(1).first()
        )
        if latest:
            out["checks"].append(
                {
                    "name": "Last Backup",
                    "ok": latest.status == "Completed",
                    "detail": f"#{latest.id} {latest.status} "
                    f"({latest.finished_at.isoformat() if latest.finished_at else '-'})",
                }
            )
        else:
            out["checks"].append(
                {"name": "Last Backup", "ok": False, "detail": "No backups yet"}
            )
    except Exception as e:
        out["checks"].append({"name": "Last Backup", "ok": False, "detail": str(e)})

    # ---- Encryption ----
    try:
        from app.services import crypto_service

        out["checks"].append(
            {
                "name": "Backup Encryption Key",
                "ok": crypto_service.encryption_available(),
                "detail": "AES-256-GCM ready"
                if crypto_service.encryption_available()
                else "BACKUP_ENCRYPTION_KEY not set",
            }
        )
    except Exception as e:
        out["checks"].append({"name": "Backup Encryption Key", "ok": False, "detail": str(e)})

    return out
