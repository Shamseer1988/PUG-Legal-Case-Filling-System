"""Auth endpoints: login, refresh, me, TOTP enroll/verify/disable."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core import request_context
from app.core.deps import get_current_user
from app.core.hardening import login_rate_limit, reset_login_rate
from app.core.permissions import capabilities_for_role
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    CapabilitiesResponse,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    TokenResponse,
    TotpEnrollResponse,
    TotpVerifyRequest,
)
from app.services import audit_service, totp_service

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
    )


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
