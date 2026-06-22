"""Phase 33: SLA breach escalation.

The case lifecycle already stamps ``sla_due_at`` on every stage
transition (workflow_service._set_stage). This module is the active
side of the deal: a scheduled tick walks the case table looking
for cases that have blown past their due-by and haven't been
escalated yet, and fires a real-time notification + email + push
to the currently-assigned signatory. The ``sla_breach_notified_at``
column gates the work so we only ping once per stage.
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.case import (
    CASE_STATUS_IN_REVIEW,
    CASE_STATUS_SUBMITTED,
    Case,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Stages whose SLA we actively police. Closed/Approved/Rejected
# cases never need escalation; clarification requests are on the
# accountant's plate, not the signatory's, and have no SLA.
_LIVE_STATUSES = (CASE_STATUS_SUBMITTED, CASE_STATUS_IN_REVIEW)


def find_breaches(db: Session, *, now: datetime | None = None) -> list[Case]:
    """Return cases whose SLA has lapsed and haven't been escalated.

    A "breach" is: sla_due_at is set, in the past, the case is still
    live (not Closed/Rejected/Approved-final), and we haven't already
    sent a breach notification for the current stage.
    """
    cutoff = now or _utcnow()
    rows = (
        db.query(Case)
        .filter(
            Case.sla_due_at.is_not(None),
            Case.sla_due_at < cutoff,
            Case.status.in_(_LIVE_STATUSES),
            or_(
                Case.sla_breach_notified_at.is_(None),
                # Re-arm if a previous breach was stamped before the
                # current stage entry (defensive — _set_stage already
                # clears the flag, but covers data migrated from a
                # pre-Phase 33 deployment).
                and_(
                    Case.stage_entered_at.is_not(None),
                    Case.sla_breach_notified_at < Case.stage_entered_at,
                ),
            ),
        )
        .all()
    )
    return rows


def scan_and_escalate(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    """Find every breached case and fire ``on_case_sla_breached``.

    Returns a small stats dict so the scheduler can log how busy the
    tick was. Each row is stamped with ``sla_breach_notified_at`` so
    the next tick is a no-op until the case moves to a new stage.
    """
    from app.services import notification_service

    cutoff = now or _utcnow()
    cases = find_breaches(db, now=cutoff)
    sent = 0
    for case in cases:
        try:
            notification_service.on_case_sla_breached(db, case)
            case.sla_breach_notified_at = cutoff
            sent += 1
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "SLA escalation failed for case {} ({}): {}",
                case.id,
                case.case_no,
                exc,
            )
    if cases:
        db.commit()
    return {"scanned": len(cases), "escalated": sent}
