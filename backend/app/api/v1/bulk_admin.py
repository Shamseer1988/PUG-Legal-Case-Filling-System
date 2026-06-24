"""Admin-only bulk operations (Phase 28).

Currently only ``bulk_reassign`` is here. Useful when a Sales
Manager / Auditor / FM leaves the company or moves divisions and
their cases need to be transferred to a different signatory in
one shot, instead of opening each case individually.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import require_permission
from app.core.permissions import USERS_WRITE
from app.db.session import get_db
from app.models.case import Case
from app.models.user import User
from app.schemas.approval import BulkReassignRequest, BulkReassignResult
from app.services import audit_service

router = APIRouter(prefix="/admin/cases", tags=["admin"])

# Statuses that count as "closed" for the only_open=True default.
_CLOSED_STATUSES = ("Closed", "Rejected")


@router.post("/bulk-reassign", response_model=BulkReassignResult)
def bulk_reassign_signatory(
    payload: BulkReassignRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(USERS_WRITE)),
) -> BulkReassignResult:
    """Move every ``user_field`` reference from ``from_user_id`` to
    ``to_user_id`` across cases.

    Restricted to users:write (Admin in the default seed). When
    ``only_open=True`` (the default), closed / rejected cases keep
    their historic signatory record intact so the audit trail
    isn't rewritten.
    """
    if payload.from_user_id == payload.to_user_id:
        raise HTTPException(
            status_code=400,
            detail="from_user_id and to_user_id must differ",
        )
    from_user = db.get(User, payload.from_user_id)
    to_user = db.get(User, payload.to_user_id)
    if not from_user or not to_user:
        raise HTTPException(status_code=404, detail="from_user or to_user not found")
    if not to_user.is_active:
        raise HTTPException(
            status_code=400,
            detail=f"to_user '{to_user.email}' is inactive",
        )

    column = getattr(Case, payload.user_field)
    q = db.query(Case).filter(column == payload.from_user_id)
    closed_rows: list[Case] = []
    updatable_rows: list[Case] = []
    for c in q.all():
        if payload.only_open and c.status in _CLOSED_STATUSES:
            closed_rows.append(c)
            continue
        updatable_rows.append(c)

    updated = 0
    for c in updatable_rows:
        setattr(c, payload.user_field, payload.to_user_id)
        updated += 1

    if updated:
        audit_service.record_event(
            db,
            action="case_bulk_reassign",
            entity_type="User",
            entity_id=payload.from_user_id,
            summary=(
                f"Reassigned {updated} case(s) at {payload.user_field}: "
                f"{from_user.email} -> {to_user.email}"
            ),
            meta={
                "user_field": payload.user_field,
                "from_user_id": payload.from_user_id,
                "to_user_id": payload.to_user_id,
                "only_open": payload.only_open,
                "case_ids": [c.id for c in updatable_rows][:200],
            },
            actor=actor,
        )
    db.commit()

    return BulkReassignResult(
        updated=updated,
        skipped_closed=len(closed_rows),
    )
