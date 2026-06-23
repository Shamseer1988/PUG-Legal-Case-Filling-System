"""User CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_permission
from app.core.permissions import USERS_READ, USERS_WRITE
from app.core.security import hash_password
from app.db.session import get_db
from app.models.user import Role, User, UserDivisionMap
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services import audit_service

router = APIRouter(prefix="/users", tags=["users"])


# Roles that don't need to be division-scoped on the case form — they
# represent group-wide approvers / sign-offs.
_CROSS_DIVISION_ROLES = {"Auditor", "Chairman / MD", "Admin"}


class UserOption(BaseModel):
    id: int
    full_name: str
    email: str
    role_name: str
    division_ids: list[int]


@router.get("/options", response_model=list[UserOption])
def user_options(
    role: str | None = None,
    division_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[UserOption]:
    """Dropdown options for the case form's signatory selectors.

    ``role`` filters by role name (Sales Manager / Division Manager /
    Finance Manager / Executive Director / Auditor / Chairman / MD).

    ``division_id`` filters out users who don't belong to that
    division — but is ignored for the cross-division approver roles
    (Auditor and Chairman / MD), who sign across every division.
    """
    q = db.query(User).join(Role, User.role_id == Role.id).filter(User.is_active.is_(True))
    if role:
        q = q.filter(Role.name == role)
    rows = q.order_by(User.full_name).all()
    apply_division_filter = division_id is not None and role not in _CROSS_DIVISION_ROLES
    out: list[UserOption] = []
    for u in rows:
        div_ids = [d.id for d in u.divisions]
        # Phase 37: an ``is_all_divisions`` user is visible on every
        # division's signatory picker even if their mapping list is
        # empty.
        if (
            apply_division_filter
            and division_id not in div_ids
            and not u.is_all_divisions
        ):
            continue
        out.append(
            UserOption(
                id=u.id,
                full_name=u.full_name,
                email=u.email,
                role_name=u.role.name if u.role else "",
                division_ids=div_ids,
            )
        )
    return out


def _to_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role_id=user.role_id,
        role_name=user.role.name if user.role else "",
        is_active=user.is_active,
        is_super=user.is_super,
        is_all_divisions=user.is_all_divisions,
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
        is_all_divisions=payload.is_all_divisions,
    )
    db.add(user)
    db.flush()
    # is_all_divisions wins - drop per-division mappings to keep
    # the row's state coherent (matches Lawyer semantics).
    division_ids = [] if payload.is_all_divisions else list(payload.division_ids)
    for did in division_ids:
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
            "is_all_divisions": user.is_all_divisions,
            "division_ids": division_ids,
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
        "is_all_divisions": user.is_all_divisions,
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

    # When "All Companies" wins, drop every per-division mapping so
    # the row's state stays coherent. Otherwise apply whatever list
    # the client sent.
    if user.is_all_divisions:
        db.query(UserDivisionMap).filter(UserDivisionMap.user_id == user.id).delete()
        division_ids = []
    elif division_ids is not None:
        db.query(UserDivisionMap).filter(UserDivisionMap.user_id == user.id).delete()
        for did in division_ids:
            db.add(UserDivisionMap(user_id=user.id, division_id=did))

    after = {
        "full_name": user.full_name,
        "role_id": user.role_id,
        "is_active": user.is_active,
        "is_super": user.is_super,
        "is_all_divisions": user.is_all_divisions,
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
