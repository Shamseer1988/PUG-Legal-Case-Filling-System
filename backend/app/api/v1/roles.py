"""Role CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_permission
from app.core.permissions import ROLES_READ, ROLES_WRITE
from app.db.session import get_db
from app.models.user import Role, User
from app.schemas.user import RoleCreate, RoleRead, RoleUpdate

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=list[RoleRead])
def list_roles(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ROLES_READ)),
) -> list[RoleRead]:
    return [RoleRead.model_validate(r) for r in db.query(Role).order_by(Role.name).all()]


@router.post("", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ROLES_WRITE)),
) -> RoleRead:
    if db.query(Role).filter(Role.name == payload.name).first():
        raise HTTPException(status_code=409, detail="Role name already exists")
    role = Role(**payload.model_dump())
    db.add(role)
    db.commit()
    db.refresh(role)
    return RoleRead.model_validate(role)


@router.patch("/{role_id}", response_model=RoleRead)
def update_role(
    role_id: int,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ROLES_WRITE)),
) -> RoleRead:
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system and payload.name and payload.name != role.name:
        raise HTTPException(status_code=400, detail="Cannot rename a system role")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(role, k, v)
    db.commit()
    db.refresh(role)
    return RoleRead.model_validate(role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ROLES_WRITE)),
) -> None:
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete a system role")
    db.delete(role)
    db.commit()
