"""Audit log endpoints: list with filters, detail, verify, CSV / PDF
/ signed-JSON export, case-view forensics."""

import csv
import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import require_permission
from app.core.permissions import ADMIN_AUDIT_LOG
from app.db.session import get_db
from app.models.audit import AuditLog
from app.models.case_view import CaseView
from app.models.user import User
from app.schemas.audit import (
    AuditLogDetail,
    AuditLogListItem,
    CaseViewItem,
    SignedExportInfo,
    VerifyResult,
)
from app.services import audit_export, audit_service, pdf_renderer

router = APIRouter(prefix="/audit-log", tags=["audit"])


def _row_to_item(r: AuditLog) -> AuditLogListItem:
    return AuditLogListItem.model_validate(r)


def _scoped_query(db: Session):
    return db.query(AuditLog)


def _filtered_query(
    db: Session,
    *,
    action: str | None,
    entity_type: str | None,
    actor_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
    q: str | None,
):
    qy = _scoped_query(db)
    if action:
        qy = qy.filter(AuditLog.action == action)
    if entity_type:
        qy = qy.filter(AuditLog.entity_type == entity_type)
    if actor_id is not None:
        qy = qy.filter(AuditLog.actor_id == actor_id)
    if date_from:
        qy = qy.filter(AuditLog.created_at >= date_from)
    if date_to:
        qy = qy.filter(AuditLog.created_at <= date_to)
    if q:
        like = f"%{q}%"
        qy = qy.filter(
            (AuditLog.summary.ilike(like))
            | (AuditLog.actor_email.ilike(like))
            | (AuditLog.entity_type.ilike(like))
        )
    return qy.order_by(AuditLog.id.desc())


@router.get("", response_model=list[AuditLogListItem])
def list_entries(
    action: str | None = None,
    entity_type: str | None = None,
    actor_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_AUDIT_LOG)),
) -> list[AuditLogListItem]:
    rows = _filtered_query(
        db,
        action=action,
        entity_type=entity_type,
        actor_id=actor_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
    ).limit(limit).all()
    return [_row_to_item(r) for r in rows]


@router.get("/verify", response_model=VerifyResult)
def verify(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_AUDIT_LOG)),
) -> VerifyResult:
    return VerifyResult(**audit_service.verify_chain(db))


@router.get(".csv")
def export_csv(
    action: str | None = None,
    entity_type: str | None = None,
    actor_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_AUDIT_LOG)),
) -> Response:
    rows = _filtered_query(
        db,
        action=action,
        entity_type=entity_type,
        actor_id=actor_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
    ).limit(10000).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "id",
            "created_at",
            "actor_email",
            "actor_role",
            "ip_address",
            "action",
            "entity_type",
            "entity_id",
            "summary",
            "row_hash",
        ]
    )
    for r in rows:
        w.writerow(
            [
                r.id,
                r.created_at.isoformat(),
                r.actor_email,
                r.actor_role,
                r.ip_address,
                r.action,
                r.entity_type,
                r.entity_id if r.entity_id is not None else "",
                r.summary,
                r.row_hash,
            ]
        )
    name = f"audit-log-{datetime.now(timezone.utc):%Y%m%d-%H%M}.csv"
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get(".pdf")
def export_pdf(
    action: str | None = None,
    entity_type: str | None = None,
    actor_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_AUDIT_LOG)),
) -> Response:
    rows = _filtered_query(
        db,
        action=action,
        entity_type=entity_type,
        actor_id=actor_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
    ).limit(2000).all()
    columns = [
        {"key": "id", "label": "ID", "type": "int"},
        {"key": "created_at", "label": "When", "type": "datetime"},
        {"key": "actor", "label": "Actor", "type": "text"},
        {"key": "action", "label": "Action", "type": "text"},
        {"key": "entity_type", "label": "Entity", "type": "text"},
        {"key": "entity_id", "label": "Entity ID", "type": "int"},
        {"key": "summary", "label": "Summary", "type": "text"},
    ]
    data_rows = []
    for r in rows:
        data_rows.append(
            {
                "id": r.id,
                "created_at": r.created_at,
                "actor": f"{r.actor_email} ({r.actor_role})" if r.actor_email else "-",
                "action": r.action,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "summary": r.summary,
            }
        )
    blob = pdf_renderer.render_pdf(
        title="Audit Trail",
        subtitle="Filtered audit log entries",
        columns=columns,
        rows=data_rows,
        params={
            "action": action or "",
            "entity_type": entity_type or "",
            "from": date_from.isoformat() if date_from else "",
            "to": date_to.isoformat() if date_to else "",
            "q": q or "",
        },
    )
    name = f"audit-log-{datetime.now(timezone.utc):%Y%m%d-%H%M}.pdf"
    return Response(
        content=blob,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


# ---------------------------------------------------------------------------
# Phase 30: case-view forensics + signed JSON exports
# ---------------------------------------------------------------------------
@router.get("/case-views/{case_id}", response_model=list[CaseViewItem])
def list_case_views(
    case_id: int,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_AUDIT_LOG)),
) -> list[CaseViewItem]:
    """Who has opened this case, and when. Newest first."""
    rows = (
        db.query(CaseView)
        .filter(CaseView.case_id == case_id)
        .order_by(CaseView.id.desc())
        .limit(limit)
        .all()
    )
    user_ids = {r.user_id for r in rows if r.user_id is not None}
    user_map: dict[int, User] = {}
    if user_ids:
        for u in db.query(User).filter(User.id.in_(user_ids)).all():
            user_map[u.id] = u
    out: list[CaseViewItem] = []
    for r in rows:
        u = user_map.get(r.user_id) if r.user_id else None
        out.append(
            CaseViewItem(
                id=r.id,
                case_id=r.case_id,
                user_id=r.user_id,
                viewed_at=r.viewed_at,
                ip_address=r.ip_address,
                user_email=u.email if u else "",
                user_full_name=u.full_name if u else "",
            )
        )
    return out


@router.get("/signing-key", response_model=SignedExportInfo)
def get_signing_key(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_AUDIT_LOG)),
) -> SignedExportInfo:
    """Public key (Ed25519, base64-PEM) used to sign audit exports.

    Hand this to an external auditor once; they can then verify any
    later signed export offline.
    """
    return SignedExportInfo(
        public_key=audit_export.get_public_key(db),
        format=audit_export.FORMAT_ID,
    )


@router.get(".signed.json")
def export_signed_json(
    action: str | None = None,
    entity_type: str | None = None,
    actor_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_AUDIT_LOG)),
) -> Response:
    """Tamper-evident JSON export of the filtered audit log slice.

    The bundle carries a base64 Ed25519 signature over the canonical
    JSON form of the body, plus the public key. Any later mutation
    of the rows / filters / generated_at will fail
    audit_export.verify_signed_export.
    """
    # Same filter pipeline as the CSV / PDF exports, but rows are
    # served in id-ASCENDING order so the bundle is reproducible
    # for a given filter set.
    qy = _filtered_query(
        db,
        action=action,
        entity_type=entity_type,
        actor_id=actor_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )
    # _filtered_query orders desc; we want asc for the export.
    rows = (
        qy.order_by(None)
        .order_by(AuditLog.id.asc())
        .limit(50000)
        .all()
    )
    filters = {
        "action": action or "",
        "entity_type": entity_type or "",
        "actor_id": actor_id,
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "q": q or "",
    }
    bundle = audit_export.build_signed_export(db, rows, filters)
    name = f"audit-log-{datetime.now(timezone.utc):%Y%m%d-%H%M}.signed.json"
    return Response(
        content=json.dumps(bundle, indent=2, default=str).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/{entry_id}", response_model=AuditLogDetail)
def detail(
    entry_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(ADMIN_AUDIT_LOG)),
) -> AuditLogDetail:
    """Single audit row by id. Registered LAST so the literal
    routes ``/signing-key``, ``/case-views/{case_id}`` and
    ``/verify`` aren't shadowed by the dynamic ``{entry_id}``."""
    r = db.get(AuditLog, entry_id)
    if not r:
        raise HTTPException(status_code=404, detail="Audit entry not found")
    return AuditLogDetail.model_validate(r)
