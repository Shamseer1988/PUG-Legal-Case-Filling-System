"""Execute scheduled reports: query, render Excel + PDF, send branded email."""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.scheduled_report import (
    LAST_RUN_FAILED,
    LAST_RUN_SUCCESS,
    RUN_STATUS_FAILED,
    RUN_STATUS_SUCCESS,
    ScheduledReport,
    ScheduledReportRun,
)
from app.models.user import User
from app.services import email_service, excel_renderer, pdf_renderer, reports
from app.services.scheduler_service import compute_next_run


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _filter_active_recipients(db: Session, emails: list[str]) -> list[str]:
    """Phase 27: drop recipients whose User row is inactive.

    Addresses that don't correspond to a User at all are kept
    (external recipients are a legitimate use case). Addresses
    whose User exists but is_active=False are silently dropped
    so a manager who left the company stops receiving scheduled
    reports they no longer have access to.
    """
    addrs = [e.strip() for e in (emails or []) if e and e.strip()]
    if not addrs:
        return []
    rows = (
        db.query(User.email, User.is_active)
        .filter(User.email.in_([a.lower() for a in addrs]))
        .all()
    )
    status_by_email = {email.lower(): is_active for email, is_active in rows}
    out: list[str] = []
    for a in addrs:
        # Unknown email -> external recipient, keep.
        # Known email -> only keep if still active.
        is_active = status_by_email.get(a.lower(), True)
        if is_active:
            out.append(a)
        else:
            logger.info(
                "Scheduled report: dropping inactive recipient {}", a
            )
    return out


def _sample_rows(data: dict, n: int = 8) -> tuple[list[dict], list[dict]]:
    cols = data.get("columns") or []
    rows = data.get("rows") or []
    # Format complex types into strings so the HTML preview is readable
    out_rows = []
    for r in rows[:n]:
        out: dict = {}
        for col in cols:
            v = r.get(col["key"])
            if v is None:
                out[col["key"]] = ""
            elif col.get("type") in ("datetime",):
                out[col["key"]] = str(v).replace("T", " ")[:16]
            elif col.get("type") == "date":
                out[col["key"]] = str(v)[:10]
            elif col.get("type") in ("number",):
                try:
                    out[col["key"]] = f"{float(v):,.2f}"
                except (TypeError, ValueError):
                    out[col["key"]] = str(v)
            else:
                out[col["key"]] = str(v)
        out_rows.append(out)
    return cols[:5], out_rows


def execute_one(db: Session, schedule: ScheduledReport) -> ScheduledReportRun:
    run = ScheduledReportRun(
        schedule_id=schedule.id,
        started_at=_utcnow(),
        status=RUN_STATUS_SUCCESS,
    )
    db.add(run)
    db.flush()

    try:
        rd = reports.get_report(schedule.report_key)
        if not rd:
            raise ValueError(f"Unknown report key: {schedule.report_key}")

        creator = db.get(User, schedule.created_by_id)
        if not creator:
            raise ValueError("Schedule creator no longer exists")

        params = schedule.params or {}
        data = rd.query(db, creator, params)
        rows_count = len(data.get("rows") or [])
        run.rows_count = rows_count

        attachments: list[tuple[str, bytes, str]] = []
        stamp = _utcnow().strftime("%Y%m%d-%H%M")
        formats = [f.lower() for f in (schedule.formats or ["pdf"]) if f]

        if "xlsx" in formats:
            blob = excel_renderer.render_xlsx(
                title=data["title"],
                subtitle=data.get("subtitle", ""),
                columns=data["columns"],
                rows=data["rows"],
                params=params,
            )
            attachments.append(
                (
                    f"{schedule.report_key}-{stamp}.xlsx",
                    blob,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            )
        if "pdf" in formats:
            blob = pdf_renderer.render_pdf(
                title=data["title"],
                subtitle=data.get("subtitle", ""),
                columns=data["columns"],
                rows=data["rows"],
                params=params,
                landscape_mode=rd.landscape,
            )
            attachments.append(
                (f"{schedule.report_key}-{stamp}.pdf", blob, "application/pdf")
            )

        sample_cols, sample_rows = _sample_rows(data)

        subject = f"[Scheduled] {schedule.name} - {data['title']}"
        # Phase 27: prune recipients whose User row has been
        # deactivated since the schedule was last edited.
        to_list = _filter_active_recipients(db, list(schedule.recipients or []))
        cc_list = _filter_active_recipients(db, list(schedule.cc or []))
        bcc_list = _filter_active_recipients(db, list(schedule.bcc or []))
        if not to_list and not cc_list and not bcc_list:
            raise ValueError(
                "All recipients are inactive; nothing to send. "
                "Update the schedule with at least one active recipient."
            )
        log = email_service.queue_email(
            db,
            to_emails=to_list,
            cc_emails=cc_list,
            bcc_emails=bcc_list,
            subject=subject,
            template="scheduled_report_email.html",
            context={
                "schedule_name": schedule.name,
                "report_title": data["title"],
                "report_subtitle": data.get("subtitle", ""),
                "rows_count": rows_count,
                "formats": formats,
                "sample_cols": sample_cols,
                "sample_rows": sample_rows,
                "notes": schedule.notes or "",
                "action_url": f"{settings.brand_app_url.rstrip('/')}/reports/{schedule.report_key}",
                "run_at": _utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            },
            event=f"scheduled_report.{schedule.report_key}",
            attachments=attachments,
        )

        run.email_log_id = log.id
        run.status = RUN_STATUS_SUCCESS
        schedule.last_run_status = LAST_RUN_SUCCESS
        schedule.last_run_error = ""
    except Exception as e:
        run.status = RUN_STATUS_FAILED
        run.error = f"{type(e).__name__}: {e}"
        schedule.last_run_status = LAST_RUN_FAILED
        schedule.last_run_error = run.error
        logger.warning("Scheduled report {} failed: {}", schedule.id, run.error)

    run.finished_at = _utcnow()
    schedule.last_run_at = run.finished_at
    schedule.next_run_at = compute_next_run(schedule.cron, base=schedule.last_run_at)
    db.commit()
    db.refresh(run)
    return run


def run_due(db: Session) -> int:
    """Run every active schedule whose next_run_at is past. Returns count."""
    now = _utcnow()
    due = (
        db.query(ScheduledReport)
        .filter(
            ScheduledReport.is_active == True,  # noqa: E712
            ScheduledReport.next_run_at != None,  # noqa: E711
            ScheduledReport.next_run_at <= now,
        )
        .all()
    )
    for s in due:
        execute_one(db, s)
    return len(due)
