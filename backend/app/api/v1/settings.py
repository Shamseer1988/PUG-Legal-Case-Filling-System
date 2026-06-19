"""System settings + admin actions (test send, diagnostics)."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
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
    log = email_service.queue_email(
        db,
        to_emails=[str(payload.to)],
        subject="PUG Legal: SMTP Test",
        template="notification_email.html",
        context={
            "title": "SMTP Test",
            "subtitle": "If you can read this, your SMTP settings work.",
            "lines": [
                f"Sent by {user.full_name} ({user.email}).",
                "Use the Email Log page to review delivery state.",
            ],
            "facts": [],
            "action_url": "",
        },
        event="smtp.test_send",
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
