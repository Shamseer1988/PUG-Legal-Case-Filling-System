"""User CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_permission
from app.core.permissions import USERS_READ, USERS_WRITE
from app.core.security import hash_password
from app.db.session import get_db
from app.models.user import Role, User, UserDivisionMap
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services import audit_service

router = APIRouter(prefix="/users", tags=["users"])


def _to_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role_id=user.role_id,
        role_name=user.role.name if user.role else "",
        is_active=user.is_active,
        is_super=user.is_super,
        last_login_at=user.last_login_at,
        division_ids=[d.id for d in user.divisions],
    )


@router.get("", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(USERS_READ)),
) -> list[UserRead]:
    return [_to_read(u) for u in db.query(User).order_by(User.email).all()]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(USERS_WRITE)),
) -> UserRead:
    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status_code=409, detail="Email already exists")
    role = db.get(Role, payload.role_id)
    if not role:
        raise HTTPException(status_code=400, detail="Invalid role_id")
    user = User(
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role_id=payload.role_id,
        is_active=payload.is_active,
        is_super=payload.is_super,
    )
    db.add(user)
    db.flush()
    for did in payload.division_ids:
        db.add(UserDivisionMap(user_id=user.id, division_id=did))
    audit_service.audit_create(
        db,
        "User",
        user.id,
        f"Created user {user.email} (role={role.name})",
        {
            "email": user.email,
            "full_name": user.full_name,
            "role_id": user.role_id,
            "is_active": user.is_active,
            "is_super": user.is_super,
            "division_ids": list(payload.division_ids),
        },
    )
    db.commit()
    db.refresh(user)
    return _to_read(user)


@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(USERS_READ)),
) -> UserRead:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_read(user)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(USERS_WRITE)),
) -> UserRead:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    before = {
        "full_name": user.full_name,
        "role_id": user.role_id,
        "is_active": user.is_active,
        "is_super": user.is_super,
        "division_ids": [d.id for d in user.divisions],
    }

    data = payload.model_dump(exclude_unset=True)
    password_changed = False
    if "password" in data and data["password"]:
        user.password_hash = hash_password(data.pop("password"))
        password_changed = True
    else:
        data.pop("password", None)
    division_ids = data.pop("division_ids", None)

    for k, v in data.items():
        setattr(user, k, v)

    if division_ids is not None:
        db.query(UserDivisionMap).filter(UserDivisionMap.user_id == user.id).delete()
        for did in division_ids:
            db.add(UserDivisionMap(user_id=user.id, division_id=did))

    after = {
        "full_name": user.full_name,
        "role_id": user.role_id,
        "is_active": user.is_active,
        "is_super": user.is_super,
        "division_ids": division_ids if division_ids is not None else before["division_ids"],
    }
    audit_service.audit_update(
        db, "User", user.id, f"Updated user {user.email}", before, after
    )
    if password_changed:
        audit_service.record_event(
            db,
            action="password_change",
            entity_type="User",
            entity_id=user.id,
            summary=f"Password reset for {user.email}",
        )
    db.commit()
    db.refresh(user)
    return _to_read(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(USERS_WRITE)),
) -> None:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    audit_service.audit_delete(
        db,
        "User",
        user.id,
        f"Deleted user {user.email}",
        {"email": user.email, "role_id": user.role_id, "is_super": user.is_super},
    )
    db.delete(user)
    db.commit()
