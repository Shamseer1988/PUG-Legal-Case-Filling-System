"""System settings + admin actions (test send, diagnostics, logo, favicon)."""

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.deps import require_permission
from app.core.permissions import ADMIN_SETTINGS
from app.db.session import get_db
from app.models.user import User
from app.services import audit_service, email_service, settings_service
from app.services.settings_descriptors import GROUPS

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/groups")
def list_groups(_: User = Depends(require_permission(ADMIN_SETTINGS))) -> list[dict]:
    """Return the static descriptor of every settings group + field."""
    return GROUPS


@router.get("/groups/{group_key}")
def get_group(
    group_key: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_SETTINGS)),
) -> dict[str, Any]:
    try:
        return settings_service.get_group(db, group_key)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


class UpdateGroupPayload(BaseModel):
    values: dict[str, Any]


@router.put("/groups/{group_key}")
def update_group(
    group_key: str,
    payload: UpdateGroupPayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ADMIN_SETTINGS)),
) -> dict[str, Any]:
    try:
        before = settings_service.get_group(db, group_key)
        result = settings_service.set_group(
            db, group_key, payload.values, user_id=user.id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    # Snapshot what changed for the audit trail (sensitive values stay masked)
    audit_service.record_event(
        db,
        action="settings_changed",
        entity_type="SettingsGroup",
        entity_id=None,
        summary=f"Updated settings group '{group_key}'",
        before={k: v for k, v in before.items() if k != "_meta"},
        after={k: v for k, v in result.items() if k != "_meta"},
        meta={"group": group_key, "changed_keys": list(payload.values.keys())},
        actor=user,
        commit=True,
    )
    return result


class TestSendPayload(BaseModel):
    to: EmailStr


@router.post("/smtp/test-send")
def smtp_test_send(
    payload: TestSendPayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ADMIN_SETTINGS)),
) -> dict[str, Any]:
    """Render and send a one-off branded email to confirm SMTP works.

    In console mode the email is logged; the EmailLog still records
    status ``Sent`` with a note. Otherwise it goes through SMTP.
    """
    log = email_service.send_test_email(
        db,
        to_email=str(payload.to),
        requested_by=f"{user.full_name} ({user.email})",
    )
    audit_service.record_event(
        db,
        action="smtp_test",
        entity_type="EmailLog",
        entity_id=log.id,
        summary=f"SMTP test sent to {payload.to} (status={log.status})",
        actor=user,
        commit=True,
    )
    return {
        "ok": log.status == "Sent",
        "status": log.status,
        "error": log.error,
        "email_log_id": log.id,
    }


@router.post("/upload")
def upload_branding_file(
    type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(ADMIN_SETTINGS)),
) -> dict[str, Any]:
    if type not in ("logo", "favicon"):
        raise HTTPException(
            status_code=400,
            detail="Invalid upload type. Must be 'logo' or 'favicon'.",
        )

    ext = Path(file.filename or "").suffix.lower()
    allowed_exts = {
        "logo": {".png", ".jpg", ".jpeg", ".webp", ".svg"},
        "favicon": {".ico", ".png", ".jpg", ".jpeg", ".gif"},
    }[type]

    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension for {type}. Allowed extensions: {', '.join(allowed_exts)}",
        )

    # Validate size: 2MB limit
    MAX_SIZE = 2 * 1024 * 1024
    try:
        content = file.file.read(MAX_SIZE + 1)
        if len(content) > MAX_SIZE:
            raise HTTPException(
                status_code=400, detail="File too large. Max size is 2MB."
            )
        file.file.seek(0)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail="Failed to read file.")

    from app.core.config import settings as app_settings

    branding_dir = app_settings.storage_path / "branding"
    branding_dir.mkdir(parents=True, exist_ok=True)

    # Remove any existing files for this type
    for old_file in branding_dir.glob(f"{type}.*"):
        try:
            old_file.unlink()
        except Exception:
            pass

    dest_path = branding_dir / f"{type}{ext}"
    with dest_path.open("wb") as out:
        out.write(content)

    key = f"company.{type}_url"
    t = int(time.time())
    url = f"/api/v1/settings/public/{type}?t={t}"
    settings_service.set_value(db, key, url, user_id=user.id)
    db.commit()

    return {"key": key, "url": url}


@router.get("/public/logo")
def get_public_logo() -> FileResponse:
    from app.core.config import settings as app_settings

    branding_dir = app_settings.storage_path / "branding"
    if branding_dir.exists():
        for path in branding_dir.glob("logo.*"):
            if path.is_file():
                ext = path.suffix.lower()
                media_types = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                    ".svg": "image/svg+xml",
                }
                return FileResponse(path, media_type=media_types.get(ext, "image/png"))

    root_dir = Path(__file__).resolve().parents[4]
    fallback_path = root_dir / "assets" / "pug_logo_gold.png"
    if fallback_path.exists():
        return FileResponse(fallback_path, media_type="image/png")

    raise HTTPException(status_code=404, detail="Logo not found.")


@router.get("/public/favicon")
def get_public_favicon() -> FileResponse:
    from app.core.config import settings as app_settings

    branding_dir = app_settings.storage_path / "branding"
    if branding_dir.exists():
        for path in branding_dir.glob("favicon.*"):
            if path.is_file():
                ext = path.suffix.lower()
                media_types = {
                    ".ico": "image/x-icon",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".gif": "image/gif",
                }
                return FileResponse(
                    path, media_type=media_types.get(ext, "image/x-icon")
                )

    root_dir = Path(__file__).resolve().parents[4]
    fallback_path = root_dir / "assets" / "favicon.ico"
    if fallback_path.exists():
        return FileResponse(fallback_path, media_type="image/x-icon")

    raise HTTPException(status_code=404, detail="Favicon not found.")
