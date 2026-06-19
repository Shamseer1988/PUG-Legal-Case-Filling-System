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
        log = email_service.queue_email(
            db,
            to_emails=list(schedule.recipients or []),
            cc_emails=list(schedule.cc or []),
            bcc_emails=list(schedule.bcc or []),
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
