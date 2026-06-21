"""Saved report filter CRUD (Phase 27).

A "saved filter" is a named bundle of report parameters that a
user can re-apply with one click. Private by default; flip
``is_public`` to share with the rest of the workspace.

Visibility rules:
  - Owner sees their own filters whether public or private.
  - Other users see only ``is_public`` filters.
  - Edit / delete is restricted to the owner or a super user.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.saved_filter import SavedReportFilter
from app.models.user import User
from app.schemas.saved_filter import (
    SavedFilterCreate,
    SavedFilterRead,
    SavedFilterUpdate,
)
from app.services import reports as reports_registry

router = APIRouter(prefix="/reports/saved", tags=["reports"])


def _to_read(db: Session, row: SavedReportFilter, current_user_id: int) -> SavedFilterRead:
    creator = db.get(User, row.created_by_id)
    return SavedFilterRead(
        id=row.id,
        name=row.name,
        report_key=row.report_key,
        params=row.params or {},
        is_public=row.is_public,
        created_by_id=row.created_by_id,
        created_by_name=creator.full_name if creator else "",
        is_mine=row.created_by_id == current_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[SavedFilterRead])
def list_saved_filters(
    report_key: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SavedFilterRead]:
    """List saved filters visible to the current user.

    Owner sees their own + everyone's public filters; other users
    see only the public ones. Filter by ``report_key`` to keep the
    UI dropdown scoped to the report it's rendered on.
    """
    q = db.query(SavedReportFilter)
    if not user.is_super:
        q = q.filter(
            or_(
                SavedReportFilter.created_by_id == user.id,
                SavedReportFilter.is_public.is_(True),
            )
        )
    if report_key:
        q = q.filter(SavedReportFilter.report_key == report_key)
    rows = q.order_by(SavedReportFilter.name.asc()).all()
    return [_to_read(db, r, user.id) for r in rows]


@router.post("", response_model=SavedFilterRead, status_code=status.HTTP_201_CREATED)
def create_saved_filter(
    payload: SavedFilterCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SavedFilterRead:
    if not reports_registry.get_report(payload.report_key):
        raise HTTPException(
            status_code=400, detail=f"Unknown report key: {payload.report_key}"
        )
    row = SavedReportFilter(
        name=payload.name.strip(),
        report_key=payload.report_key,
        params=payload.params or {},
        is_public=payload.is_public,
        created_by_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_read(db, row, user.id)


def _get_or_404(db: Session, user: User, fid: int) -> SavedReportFilter:
    row = db.get(SavedReportFilter, fid)
    if not row:
        raise HTTPException(status_code=404, detail="Filter not found")
    if (
        not user.is_super
        and row.created_by_id != user.id
        and not row.is_public
    ):
        # Hide private filters owned by someone else by returning
        # 404 - don't reveal that the row exists.
        raise HTTPException(status_code=404, detail="Filter not found")
    return row


@router.get("/{fid}", response_model=SavedFilterRead)
def get_saved_filter(
    fid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SavedFilterRead:
    row = _get_or_404(db, user, fid)
    return _to_read(db, row, user.id)


@router.patch("/{fid}", response_model=SavedFilterRead)
def update_saved_filter(
    fid: int,
    payload: SavedFilterUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SavedFilterRead:
    row = _get_or_404(db, user, fid)
    if row.created_by_id != user.id and not user.is_super:
        raise HTTPException(status_code=403, detail="Not your filter")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()
    if "params" in data and data["params"] is not None:
        row.params = data["params"]
    if "is_public" in data and data["is_public"] is not None:
        row.is_public = data["is_public"]
    db.commit()
    db.refresh(row)
    return _to_read(db, row, user.id)


@router.delete("/{fid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_filter(
    fid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    row = _get_or_404(db, user, fid)
    if row.created_by_id != user.id and not user.is_super:
        raise HTTPException(status_code=403, detail="Not your filter")
    db.delete(row)
    db.commit()
