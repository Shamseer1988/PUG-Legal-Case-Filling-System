"""Phase 41: physical-document chain-of-custody API.

Endpoints
- ``GET    /cases/{case_id}/documents``                  - list per-case
- ``POST   /cases/{case_id}/documents``                  - register a new doc
- ``GET    /documents/{doc_id}``                         - detail + log
- ``PATCH  /documents/{doc_id}``                         - edit metadata
- ``DELETE /documents/{doc_id}``                         - retire (soft-delete via is_active)
- ``POST   /documents/{doc_id}/transfer``                - record handover
- ``POST   /documents/transfers/{log_id}/signature``     - upload optional signature
- ``GET    /documents/transfers/{log_id}/signature``     - view signature image
- ``GET    /documents/reports/with-me``                  - my held files
- ``GET    /documents/reports/overdue?days=N``           - overdue out-of-storage

Permissions
- ``documents:read``       - list + view
- ``documents:transfer``   - register, transfer, retire, upload signature
- Division scoping mirrors cases: callers only see docs on cases
  inside ``allowed_division_ids`` (None = cross-division).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.data_scope import allowed_division_ids
from app.core.deps import require_permission
from app.core.permissions import DOCUMENTS_READ, DOCUMENTS_TRANSFER
from app.db.session import get_db
from app.models.case import Case
from app.models.masters import DocumentLocation
from app.models.physical_document import (
    DOC_KINDS,
    DocumentCustodyLog,
    PhysicalDocument,
)
from app.models.user import User
from app.schemas.physical_document import (
    CustodyLogRead,
    OverdueDocumentRow,
    PendingIncomingRead,
    PhysicalDocumentCreate,
    PhysicalDocumentDetail,
    PhysicalDocumentRead,
    PhysicalDocumentUpdate,
    TransferActionRequest,
    TransferRequest,
)
from app.services import audit_service, storage

router = APIRouter(tags=["physical-documents"])


# ---------- helpers ----------
def _scoped_case_or_404(db: Session, user: User, case_id: int) -> Case:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    allowed = allowed_division_ids(user)
    if allowed is not None:
        if not allowed or case.division_id not in allowed:
            raise HTTPException(status_code=404, detail="Case not found")
    return case


def _scoped_doc_or_404(
    db: Session, user: User, doc_id: int
) -> PhysicalDocument:
    doc = db.get(PhysicalDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # Reuse the case-scoping logic - if the user can't see the
    # parent case they can't see its physical docs either.
    _scoped_case_or_404(db, user, doc.case_id)
    return doc


def _name_or_empty(user: User | None) -> str:
    return user.full_name if user else ""


def _doc_to_read(db: Session, doc: PhysicalDocument) -> PhysicalDocumentRead:
    case = db.get(Case, doc.case_id)
    out = PhysicalDocumentRead.model_validate(doc)
    out.current_holder_name = _name_or_empty(doc.current_holder)
    out.current_location_name = doc.current_location.name if doc.current_location else ""
    out.case_no = case.case_no if case else ""
    # Expose the pending transfer (if any) so the UI can show Accept/Reject.
    pending = next(
        (l for l in doc.custody_log if l.transfer_status == "pending"), None
    )
    if pending:
        out.pending_transfer_log_id = pending.id
        out.pending_transfer_to_user_id = pending.to_user_id
        out.pending_transfer_to_name = _name_or_empty(pending.to_user)
    return out


def _log_to_read(log: DocumentCustodyLog) -> CustodyLogRead:
    out = CustodyLogRead.model_validate(log)
    out.from_user_name = _name_or_empty(log.from_user)
    out.to_user_name = _name_or_empty(log.to_user)
    out.location_name = log.location.name if log.location else ""
    out.recorded_by_name = _name_or_empty(log.recorded_by)
    return out


def _apply_snapshot(doc: PhysicalDocument, log: DocumentCustodyLog) -> None:
    """Mirror the latest log row back onto the document for fast
    "where is X?" lookups."""
    doc.current_holder_user_id = log.to_user_id
    doc.current_location_id = log.location_id
    doc.current_location_text = log.location_text or ""
    doc.last_transferred_at = log.transferred_at


# ---------- per-case endpoints ----------
@router.get(
    "/cases/{case_id}/documents",
    response_model=list[PhysicalDocumentRead],
)
def list_case_documents(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(DOCUMENTS_READ)),
) -> list[PhysicalDocumentRead]:
    case = _scoped_case_or_404(db, user, case_id)
    rows = (
        db.query(PhysicalDocument)
        .filter(PhysicalDocument.case_id == case.id)
        .order_by(PhysicalDocument.id.asc())
        .all()
    )
    return [_doc_to_read(db, d) for d in rows]


@router.post(
    "/cases/{case_id}/documents",
    response_model=PhysicalDocumentDetail,
    status_code=status.HTTP_201_CREATED,
)
def register_document(
    case_id: int,
    payload: PhysicalDocumentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(DOCUMENTS_TRANSFER)),
) -> PhysicalDocumentDetail:
    case = _scoped_case_or_404(db, user, case_id)
    if payload.kind and payload.kind not in DOC_KINDS:
        # Free-text is allowed, but log the unusual value via audit
        # rather than reject - schema already caps length.
        pass

    doc = PhysicalDocument(
        case_id=case.id,
        kind=payload.kind or "other",
        label=payload.label,
        notes=payload.notes,
        is_active=True,
    )
    db.add(doc)
    db.flush()

    # Always write at least one log entry so the chain has a head -
    # the "registered" event. Initial holder / location are optional.
    initial_log = DocumentCustodyLog(
        document_id=doc.id,
        transferred_at=datetime.utcnow(),
        recorded_by_user_id=user.id,
        from_user_id=None,
        to_user_id=payload.initial_holder_user_id,
        location_id=payload.initial_location_id,
        location_text=payload.initial_location_text or "",
        note=payload.initial_note or "Registered",
    )
    db.add(initial_log)
    db.flush()
    _apply_snapshot(doc, initial_log)

    audit_service.audit_create(
        db,
        "PhysicalDocument",
        doc.id,
        f"Registered physical doc \"{doc.label}\" on case #{case.id}",
        audit_service.snapshot(doc),
    )
    db.commit()
    db.refresh(doc)
    return _to_detail(db, doc)


# ---------- per-document endpoints ----------
@router.get(
    "/documents/{doc_id}",
    response_model=PhysicalDocumentDetail,
)
def get_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(DOCUMENTS_READ)),
) -> PhysicalDocumentDetail:
    doc = _scoped_doc_or_404(db, user, doc_id)
    return _to_detail(db, doc)


@router.patch(
    "/documents/{doc_id}",
    response_model=PhysicalDocumentRead,
)
def update_document(
    doc_id: int,
    payload: PhysicalDocumentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(DOCUMENTS_TRANSFER)),
) -> PhysicalDocumentRead:
    doc = _scoped_doc_or_404(db, user, doc_id)
    before = audit_service.snapshot(doc)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(doc, k, v)
    db.flush()
    audit_service.audit_update(
        db,
        "PhysicalDocument",
        doc.id,
        f"Updated physical doc #{doc.id}",
        before,
        audit_service.snapshot(doc),
    )
    db.commit()
    db.refresh(doc)
    return _doc_to_read(db, doc)


@router.delete(
    "/documents/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def retire_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(DOCUMENTS_TRANSFER)),
) -> None:
    """Soft-delete via ``is_active = False``.

    Physical docs are never hard-deleted from the API - the custody
    log is an audit trail and must remain readable. Set is_active
    to False when the doc has been archived / destroyed.
    """
    doc = _scoped_doc_or_404(db, user, doc_id)
    if not doc.is_active:
        return  # idempotent
    before = audit_service.snapshot(doc)
    doc.is_active = False
    db.flush()
    audit_service.audit_update(
        db,
        "PhysicalDocument",
        doc.id,
        f"Retired physical doc #{doc.id}",
        before,
        audit_service.snapshot(doc),
    )
    db.commit()


# ---------- transfer ----------
@router.post(
    "/documents/{doc_id}/transfer",
    response_model=PhysicalDocumentDetail,
)
def transfer_document(
    doc_id: int,
    payload: TransferRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(DOCUMENTS_TRANSFER)),
) -> PhysicalDocumentDetail:
    doc = _scoped_doc_or_404(db, user, doc_id)
    if not doc.is_active:
        raise HTTPException(status_code=409, detail="Document is retired")

    # Block new transfer while one is still pending acceptance.
    existing_pending = next(
        (l for l in doc.custody_log if l.transfer_status == "pending"), None
    )
    if existing_pending:
        raise HTTPException(
            status_code=409,
            detail="A transfer is already pending acceptance — wait for the receiver to accept or reject first",
        )

    # At least one destination is required so a transfer can't be
    # "nowhere". location_text alone counts as a destination.
    if not (payload.to_user_id or payload.to_location_id or (payload.location_text or "").strip()):
        raise HTTPException(
            status_code=422,
            detail="Pick a recipient, a location, or write a free-text destination",
        )

    if payload.to_location_id is not None:
        loc = db.get(DocumentLocation, payload.to_location_id)
        if not loc:
            raise HTTPException(status_code=422, detail="Unknown location")
    if payload.to_user_id is not None:
        recipient = db.get(User, payload.to_user_id)
        if not recipient:
            raise HTTPException(status_code=422, detail="Unknown recipient")

    # Transfers to a named user require their acceptance before custody
    # moves. Transfers to a location only are immediate.
    needs_acceptance = payload.to_user_id is not None
    transfer_status = "pending" if needs_acceptance else "accepted"

    log = DocumentCustodyLog(
        document_id=doc.id,
        transferred_at=payload.transferred_at or datetime.utcnow(),
        recorded_by_user_id=user.id,
        from_user_id=doc.current_holder_user_id,
        to_user_id=payload.to_user_id,
        location_id=payload.to_location_id,
        location_text=payload.location_text or "",
        note=payload.note or "",
        transfer_status=transfer_status,
    )
    db.add(log)
    db.flush()

    # Only move custody immediately for location-only transfers.
    if not needs_acceptance:
        _apply_snapshot(doc, log)

    audit_service.audit_update(
        db,
        "PhysicalDocument",
        doc.id,
        f"{'Initiated pending transfer' if needs_acceptance else 'Transferred'} physical doc #{doc.id}",
        {"holder": None, "location": None},
        {
            "to_user_id": log.to_user_id,
            "location_id": log.location_id,
            "location_text": log.location_text,
            "transfer_status": transfer_status,
        },
    )
    db.commit()
    db.refresh(doc)
    return _to_detail(db, doc)


# ---------- signature ----------
@router.post(
    "/documents/transfers/{log_id}/signature",
    response_model=CustodyLogRead,
)
def upload_transfer_signature(
    log_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(DOCUMENTS_TRANSFER)),
) -> CustodyLogRead:
    log = db.get(DocumentCustodyLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Transfer not found")
    # Scope: must be able to see the parent document.
    _scoped_doc_or_404(db, user, log.document_id)

    if log.signature_stored:
        storage.delete_custody_signature(log.id, log.signature_stored)
    stored, size = storage.save_custody_signature(log.id, file)
    log.signature_filename = file.filename or stored
    log.signature_stored = stored
    log.signature_mime = file.content_type or "application/octet-stream"
    log.signature_size = size
    db.commit()
    db.refresh(log)
    return _log_to_read(log)


@router.get("/documents/transfers/{log_id}/signature")
def view_transfer_signature(
    log_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(DOCUMENTS_READ)),
) -> FileResponse:
    log = db.get(DocumentCustodyLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Transfer not found")
    _scoped_doc_or_404(db, user, log.document_id)
    if not log.signature_stored:
        raise HTTPException(status_code=404, detail="No signature on file")
    path = storage.get_custody_signature_path(log.id, log.signature_stored)
    if not path.exists():
        raise HTTPException(status_code=410, detail="Signature missing on disk")
    return FileResponse(
        path,
        filename=log.signature_filename or "signature",
        media_type=log.signature_mime or "application/octet-stream",
        content_disposition_type="inline",
    )


# ---------- accept / reject ----------

@router.post(
    "/documents/transfers/{log_id}/accept",
    response_model=PhysicalDocumentDetail,
)
def accept_transfer(
    log_id: int,
    body: TransferActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(DOCUMENTS_TRANSFER)),
) -> PhysicalDocumentDetail:
    """Receiver accepts a pending transfer — custody moves to them."""
    log = db.get(DocumentCustodyLog, log_id)
    if not log or log.transfer_status != "pending":
        raise HTTPException(status_code=404, detail="Pending transfer not found")
    if log.to_user_id != user.id:
        raise HTTPException(
            status_code=403, detail="You are not the intended recipient of this transfer"
        )
    # Skip division scoping for the recipient: the sender already validated
    # the recipient when creating the transfer, and to_user_id == user.id is
    # a sufficiently narrow guard.
    doc = db.get(PhysicalDocument, log.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.is_active:
        raise HTTPException(status_code=409, detail="Document is retired")

    log.transfer_status = "accepted"
    log.accepted_at = datetime.utcnow()
    if body.note:
        log.note = (log.note + "\n[Accepted] " + body.note).strip()
    _apply_snapshot(doc, log)

    audit_service.audit_update(
        db,
        "PhysicalDocument",
        doc.id,
        f"Transfer of physical doc #{doc.id} accepted by user #{user.id}",
        {},
        {"transfer_status": "accepted", "new_holder": user.id},
    )
    db.commit()
    db.refresh(doc)
    return _to_detail(db, doc)


@router.post(
    "/documents/transfers/{log_id}/reject",
    response_model=CustodyLogRead,
)
def reject_transfer(
    log_id: int,
    body: TransferActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(DOCUMENTS_TRANSFER)),
) -> CustodyLogRead:
    """Receiver rejects a pending transfer — doc stays with the sender."""
    log = db.get(DocumentCustodyLog, log_id)
    if not log or log.transfer_status != "pending":
        raise HTTPException(status_code=404, detail="Pending transfer not found")
    if log.to_user_id != user.id:
        raise HTTPException(
            status_code=403, detail="You are not the intended recipient of this transfer"
        )
    # Same rationale as accept: skip division scoping for the named recipient.
    if not db.get(PhysicalDocument, log.document_id):
        raise HTTPException(status_code=404, detail="Document not found")

    log.transfer_status = "rejected"
    if body.note:
        log.note = (log.note + "\n[Rejected] " + body.note).strip()

    audit_service.audit_update(
        db,
        "PhysicalDocument",
        log.document_id,
        f"Transfer of physical doc #{log.document_id} rejected by user #{user.id}",
        {},
        {"transfer_status": "rejected"},
    )
    db.commit()
    db.refresh(log)
    return _log_to_read(log)


# ---------- acknowledgment (receiver uploads signed slip) ----------

@router.post(
    "/documents/transfers/{log_id}/acknowledgment",
    response_model=CustodyLogRead,
)
def upload_acknowledgment(
    log_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(DOCUMENTS_TRANSFER)),
) -> CustodyLogRead:
    """Receiver uploads a signed acknowledgment after accepting a transfer."""
    log = db.get(DocumentCustodyLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if log.to_user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the transfer recipient can upload the acknowledgment",
        )
    if log.transfer_status != "accepted":
        raise HTTPException(
            status_code=409,
            detail="Transfer must be accepted before uploading acknowledgment",
        )
    if not db.get(PhysicalDocument, log.document_id):
        raise HTTPException(status_code=404, detail="Document not found")

    if log.ack_stored:
        storage.delete_custody_acknowledgment(log.id, log.ack_stored)
    stored, size = storage.save_custody_acknowledgment(log.id, file)
    log.ack_filename = file.filename or stored
    log.ack_stored = stored
    log.ack_mime = file.content_type or "application/octet-stream"
    log.ack_size = size
    db.commit()
    db.refresh(log)
    return _log_to_read(log)


@router.get("/documents/transfers/{log_id}/acknowledgment")
def view_acknowledgment(
    log_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(DOCUMENTS_READ)),
) -> FileResponse:
    log = db.get(DocumentCustodyLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Transfer not found")
    _scoped_doc_or_404(db, user, log.document_id)
    if not log.ack_stored:
        raise HTTPException(status_code=404, detail="No acknowledgment on file")
    path = storage.get_custody_acknowledgment_path(log.id, log.ack_stored)
    if not path.exists():
        raise HTTPException(status_code=410, detail="Acknowledgment file missing on disk")
    return FileResponse(
        path,
        filename=log.ack_filename or "acknowledgment",
        media_type=log.ack_mime or "application/octet-stream",
        content_disposition_type="inline",
    )


# ---------- reports ----------
@router.get(
    "/documents/reports/with-me",
    response_model=list[PhysicalDocumentRead],
)
def files_with_me(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(DOCUMENTS_READ)),
) -> list[PhysicalDocumentRead]:
    """Every active physical doc whose latest holder is the caller."""
    rows = (
        db.query(PhysicalDocument)
        .filter(
            PhysicalDocument.is_active.is_(True),
            PhysicalDocument.current_holder_user_id == user.id,
        )
        .order_by(PhysicalDocument.last_transferred_at.desc().nullslast())
        .all()
    )
    # No extra scoping needed - if the user is the current holder
    # they can always see their own holdings even across divisions.
    return [_doc_to_read(db, d) for d in rows]


@router.get(
    "/documents/reports/overdue",
    response_model=list[OverdueDocumentRow],
)
def overdue_documents(
    days: int = Query(default=7, ge=1, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(DOCUMENTS_READ)),
) -> list[OverdueDocumentRow]:
    """Active documents currently in a user's hands (not in storage)
    that have been out for more than ``days`` days.

    "In storage" is decided by the latest log row's location:
    ``location_id`` pointing at a row with ``is_storage=True`` counts
    as parked, not overdue. A bare ``to_user_id`` with no location
    is always considered "with a person" regardless of how long.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    q = (
        db.query(PhysicalDocument)
        .outerjoin(
            DocumentLocation,
            PhysicalDocument.current_location_id == DocumentLocation.id,
        )
        .filter(
            PhysicalDocument.is_active.is_(True),
            PhysicalDocument.current_holder_user_id.isnot(None),
            PhysicalDocument.last_transferred_at < cutoff,
            or_(
                PhysicalDocument.current_location_id.is_(None),
                DocumentLocation.is_storage.is_(False),
            ),
        )
    )

    allowed = allowed_division_ids(user)
    if allowed is not None:
        if not allowed:
            return []
        q = q.join(Case, Case.id == PhysicalDocument.case_id).filter(
            Case.division_id.in_(allowed)
        )
    rows = q.order_by(PhysicalDocument.last_transferred_at.asc()).all()
    out: list[OverdueDocumentRow] = []
    now = datetime.utcnow()
    for d in rows:
        case = db.get(Case, d.case_id)
        last = d.last_transferred_at
        days_out = 0
        if last is not None:
            # Normalise tz-aware -> naive utc for the subtraction so
            # postgres-style timestamps don't blow up.
            if last.tzinfo is not None:
                last = last.astimezone(timezone.utc).replace(tzinfo=None)
            days_out = max(0, (now - last).days)
        out.append(
            OverdueDocumentRow(
                document_id=d.id,
                case_id=d.case_id,
                case_no=case.case_no if case else "",
                label=d.label,
                kind=d.kind,
                holder_user_id=d.current_holder_user_id,
                holder_name=_name_or_empty(d.current_holder),
                last_transferred_at=d.last_transferred_at,
                days_out=days_out,
            )
        )
    return out


@router.get(
    "/documents/reports/pending-incoming",
    response_model=list[PendingIncomingRead],
)
def pending_incoming(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(DOCUMENTS_READ)),
) -> list[PendingIncomingRead]:
    """All pending transfers where the caller is the intended recipient."""
    logs = (
        db.query(DocumentCustodyLog)
        .filter(
            DocumentCustodyLog.to_user_id == user.id,
            DocumentCustodyLog.transfer_status == "pending",
        )
        .order_by(DocumentCustodyLog.transferred_at.asc())
        .all()
    )
    result: list[PendingIncomingRead] = []
    for log in logs:
        doc = db.get(PhysicalDocument, log.document_id)
        if not doc or not doc.is_active:
            continue
        case = db.get(Case, doc.case_id)
        row = PendingIncomingRead.model_validate(log)
        row.from_user_name = _name_or_empty(log.from_user)
        row.to_user_name = _name_or_empty(log.to_user)
        row.location_name = log.location.name if log.location else ""
        row.recorded_by_name = _name_or_empty(log.recorded_by)
        row.document_label = doc.label
        row.case_id = doc.case_id
        row.case_no = case.case_no if case else ""
        result.append(row)
    return result


# ---------- internal ----------
def _to_detail(db: Session, doc: PhysicalDocument) -> PhysicalDocumentDetail:
    read = _doc_to_read(db, doc)
    detail = PhysicalDocumentDetail(
        **read.model_dump(),
        custody_log=[_log_to_read(l) for l in doc.custody_log],
    )
    return detail
