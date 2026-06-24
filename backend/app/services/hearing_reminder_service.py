"""Phase 34: scheduled hearing reminders.

For every hearing on a live case we fire two reminders:
 - 24h before the hearing
 - 1h  before the hearing

Each window has its own ``reminder_*_sent_at`` flag on the Hearing
row so the scheduler can run as often as it likes and never
double-notify. Both reminders reuse the existing notification
``_emit`` so the user gets an in-app bell + branded email + Web
Push (Phase 32) in a single call.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.court import Hearing


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Windows are (label, lead-time, attribute-on-Hearing).
# Ordering matters only for logging — the scanner checks each
# independently.
WINDOWS: list[tuple[str, timedelta, str]] = [
    ("24h", timedelta(hours=24), "reminder_24h_sent_at"),
    ("1h", timedelta(hours=1), "reminder_1h_sent_at"),
]


def _due(hearing: Hearing, lead: timedelta, sent_attr: str, now: datetime) -> bool:
    """A window is due when:
      - it hasn't been sent yet,
      - the hearing is in the future, and
      - we're inside the lead time (now + lead >= hearing_date).
    """
    if getattr(hearing, sent_attr) is not None:
        return False
    hd = hearing.hearing_date
    if hd is None:
        return False
    if hd.tzinfo is None:
        # SQLite gives back naive datetimes; treat as UTC so we can
        # compare safely against ``now``.
        hd = hd.replace(tzinfo=timezone.utc)
    if hd <= now:
        return False
    return now + lead >= hd


def scan_and_notify(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    """Walk every hearing in any active window and fire reminders.

    Returns a small stats dict for the scheduler log.
    """
    from app.services import notification_service

    cutoff = now or _utcnow()
    # Skip hearings whose case is already closed or rejected — those
    # are historical records, not actionable.
    rows = (
        db.query(Hearing, Case)
        .join(Case, Case.id == Hearing.case_id)
        .filter(Case.status.notin_(("Closed", "Rejected")))
        .all()
    )

    sent_24h = 0
    sent_1h = 0
    for hearing, case in rows:
        for label, lead, attr in WINDOWS:
            if not _due(hearing, lead, attr, cutoff):
                continue
            try:
                notification_service.on_hearing_reminder(
                    db, hearing=hearing, case=case, window=label
                )
                setattr(hearing, attr, cutoff)
                if label == "24h":
                    sent_24h += 1
                else:
                    sent_1h += 1
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Hearing reminder ({}) failed for hearing {}: {}",
                    label,
                    hearing.id,
                    exc,
                )
    if sent_24h or sent_1h:
        db.commit()
    return {"scanned": len(rows), "sent_24h": sent_24h, "sent_1h": sent_1h}
