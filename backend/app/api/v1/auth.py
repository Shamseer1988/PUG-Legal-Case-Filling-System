"""Auth endpoints: login, refresh, me."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core import request_context
from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, MeResponse, RefreshRequest, TokenResponse
from app.services import audit_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(user_id: int) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
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
    user.last_login_at = datetime.now(timezone.utc)
    # Make the actor available to the audit row so it shows the user, not an anonymous request.
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
    )
