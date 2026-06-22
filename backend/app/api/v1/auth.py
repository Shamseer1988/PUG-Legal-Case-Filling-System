"""Auth endpoints: login, refresh, me, TOTP enroll/verify/disable."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core import request_context
from app.core.deps import get_current_user
from app.core.hardening import login_rate_limit, reset_login_rate
from app.core.permissions import capabilities_for_role
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_stream_ticket,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    CapabilitiesResponse,
    ChangePasswordRequest,
    LocaleUpdateRequest,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    TokenResponse,
    TotpEnrollResponse,
    TotpVerifyRequest,
)
from app.services import audit_service, storage, totp_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(user_id: int) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    _rate: None = Depends(login_rate_limit),
) -> TokenResponse:
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        audit_service.record_event(
            db,
            action=audit_service.ACTION_LOGIN_FAILED,
            entity_type="User",
            entity_id=user.id if user else None,
            summary=f"Failed login for {payload.email}",
            meta={"reason": "invalid_credentials" if user else "unknown_email"},
            commit=True,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        audit_service.record_event(
            db,
            action=audit_service.ACTION_LOGIN_FAILED,
            entity_type="User",
            entity_id=user.id,
            summary=f"Login blocked for inactive account {user.email}",
            actor=user,
            commit=True,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    # 2FA challenge if enabled
    if user.totp_enabled and not totp_service.check_login_code(user, payload.totp_code):
        audit_service.record_event(
            db,
            action=audit_service.ACTION_LOGIN_FAILED,
            entity_type="User",
            entity_id=user.id,
            summary=f"2FA required / invalid for {user.email}",
            meta={"reason": "totp_required" if not payload.totp_code else "totp_invalid"},
            actor=user,
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="totp_required" if not payload.totp_code else "totp_invalid",
        )

    user.last_login_at = datetime.now(timezone.utc)
    reset_login_rate(request)
    request_context.attach_user(user.id, user.email, user.role.name if user.role else "")
    audit_service.record_event(
        db,
        action=audit_service.ACTION_LOGIN,
        entity_type="User",
        entity_id=user.id,
        summary=f"Login: {user.email}",
        actor=user,
    )
    db.commit()
    return _issue_tokens(user.id)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        data = decode_token(payload.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    if data.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not a refresh token")
    user = db.get(User, int(data["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User invalid")
    return _issue_tokens(user.id)


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.name if user.role else "",
        permissions=list(user.role.permissions) if user.role else [],
        is_super=user.is_super,
        divisions=[d.id for d in user.divisions],
        totp_enabled=user.totp_enabled,
        has_signature=bool(user.signature_path),
        locale=user.locale or "en",
    )


@router.post("/me/locale", response_model=MeResponse)
def update_my_locale(
    payload: LocaleUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MeResponse:
    """Phase 31: set the signed-in user's preferred locale.

    Used by the language switcher on the profile page. The new
    locale is also picked up by the notification email pipeline
    on the next event so emails land in the user's preferred
    language without an extra restart.
    """
    user.locale = payload.locale
    audit_service.record_event(
        db,
        action="locale_change",
        entity_type="User",
        entity_id=user.id,
        summary=f"Locale set to {payload.locale} for {user.email}",
        actor=user,
    )
    db.commit()
    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.name if user.role else "",
        permissions=list(user.role.permissions) if user.role else [],
        is_super=user.is_super,
        divisions=[d.id for d in user.divisions],
        totp_enabled=user.totp_enabled,
        has_signature=bool(user.signature_path),
        locale=user.locale,
    )


@router.post("/stream-ticket")
def issue_stream_ticket(user: User = Depends(get_current_user)) -> dict:
    """Phase 26: hand out a 60-second JWT scoped to streaming.

    The browser's EventSource API can't send an Authorization
    header, so the SSE endpoint authenticates via this short-lived
    ticket passed as a query parameter instead.
    """
    return {
        "ticket": create_stream_ticket(user.id, ttl_seconds=60),
        "ttl_seconds": 60,
    }


@router.get("/me/capabilities", response_model=CapabilitiesResponse)
def my_capabilities(user: User = Depends(get_current_user)) -> CapabilitiesResponse:
    """Return the role's menu / action / data-scope bundle.

    The frontend reads this once after login (and after refresh) and
    uses it to hide unauthorised menu items, action buttons and panels
    instead of re-deriving role logic in TypeScript.
    """
    role_name = user.role.name if user.role else ""
    bundle = capabilities_for_role(role_name, user.is_super)
    return CapabilitiesResponse(
        role=role_name,
        is_super=user.is_super,
        menus=bundle["menus"],
        actions=bundle["actions"],
        scope=bundle["scope"],
        divisions=[d.id for d in user.divisions],
    )


# ---------------- TOTP 2FA ----------------
@router.post("/2fa/enroll", response_model=TotpEnrollResponse)
def totp_enroll(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TotpEnrollResponse:
    secret, otpauth, qr = totp_service.begin_enrollment(db, user)
    audit_service.record_event(
        db,
        action="2fa_enroll_started",
        entity_type="User",
        entity_id=user.id,
        summary=f"Started 2FA enrolment for {user.email}",
        actor=user,
        commit=True,
    )
    return TotpEnrollResponse(secret=secret, otpauth_url=otpauth, qr_data_url=qr)


@router.post("/2fa/verify")
def totp_verify(
    payload: TotpVerifyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if not totp_service.activate(db, user, payload.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")
    audit_service.record_event(
        db,
        action="2fa_enabled",
        entity_type="User",
        entity_id=user.id,
        summary=f"Enabled 2FA for {user.email}",
        actor=user,
        commit=True,
    )
    return {"enabled": True}


@router.post("/2fa/disable")
def totp_disable(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if not user.totp_enabled:
        return {"enabled": False}
    totp_service.disable(db, user)
    audit_service.record_event(
        db,
        action="2fa_disabled",
        entity_type="User",
        entity_id=user.id,
        summary=f"Disabled 2FA for {user.email}",
        actor=user,
        commit=True,
    )
    return {"enabled": False}


# ---------------- Change password ----------------
@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Allow the signed-in user to rotate their own password.

    Requires the current password to defeat session-hijack attacks
    (a stolen token alone shouldn't be enough to lock the account
    owner out).
    """
    if not verify_password(payload.current_password, user.password_hash):
        audit_service.record_event(
            db,
            action="password_change_failed",
            entity_type="User",
            entity_id=user.id,
            summary=f"Wrong current password for {user.email}",
            actor=user,
            commit=True,
        )
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=400, detail="New password must be different from the current one"
        )
    user.password_hash = hash_password(payload.new_password)
    audit_service.record_event(
        db,
        action="password_change",
        entity_type="User",
        entity_id=user.id,
        summary=f"Password changed by {user.email}",
        actor=user,
    )
    db.commit()
    return {"changed": True}


# ---------------- Signature image ----------------
@router.post("/me/signature")
def upload_signature(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Save a signature image so it can be embedded in printed forms."""
    try:
        rel_path, size = storage.save_user_signature(user.id, file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    user.signature_path = rel_path
    audit_service.record_event(
        db,
        action="signature_uploaded",
        entity_type="User",
        entity_id=user.id,
        summary=f"Uploaded signature for {user.email}",
        meta={"size_bytes": size},
        actor=user,
    )
    db.commit()
    return {"signature_path": rel_path, "size_bytes": size}


@router.get("/me/signature")
def get_my_signature(
    user: User = Depends(get_current_user),
) -> FileResponse:
    if not user.signature_path:
        raise HTTPException(status_code=404, detail="No signature on file")
    p = storage.get_user_signature_path(user.signature_path)
    if not p.exists():
        raise HTTPException(status_code=410, detail="Signature file missing")
    return FileResponse(p)


@router.delete("/me/signature", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_signature(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    if not user.signature_path:
        return
    storage.delete_user_signature(user.signature_path)
    user.signature_path = ""
    audit_service.record_event(
        db,
        action="signature_deleted",
        entity_type="User",
        entity_id=user.id,
        summary=f"Removed signature for {user.email}",
        actor=user,
    )
    db.commit()
