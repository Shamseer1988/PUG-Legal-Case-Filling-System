"""Case view tracking (Phase 30).

Records who opened which case + when, dedup'd within a small time
window so a tab refresh doesn't spam the log. Used by the admin
audit page to answer "who has accessed case X?".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core import request_context
from app.models.case_view import CaseView
from app.models.user import User

# Coalesce window: within this many seconds of a previous view by
# the same user on the same case, don't write a new row.
COALESCE_SECONDS = 300


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def record_view(db: Session, case_id: int, user: User | None) -> CaseView | None:
    """Insert a CaseView row unless a recent one already exists.

    Returns the inserted row, or None if a near-identical view was
    already recorded inside COALESCE_SECONDS.
    """
    if user is None:
        return None
    cutoff = _utcnow() - timedelta(seconds=COALESCE_SECONDS)
    recent = (
        db.query(CaseView)
        .filter(
            CaseView.case_id == case_id,
            CaseView.user_id == user.id,
            CaseView.viewed_at >= cutoff,
        )
        .order_by(CaseView.id.desc())
        .first()
    )
    if recent:
        return None

    ctx = request_context.get_ctx()
    row = CaseView(
        case_id=case_id,
        user_id=user.id,
        viewed_at=_utcnow(),
        ip_address=(ctx.ip if ctx else "")[:45],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
