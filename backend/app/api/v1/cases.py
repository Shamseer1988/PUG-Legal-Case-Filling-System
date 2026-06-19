"""Case CRUD, attachments and branded print view."""

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_permission
from app.core.permissions import CASES_CREATE, CASES_READ
from app.db.session import get_db
from app.models.case import CASE_STATUS_DRAFT, Case, CaseAttachment
from app.models.user import User
from app.schemas.approval import TimelineEntry, TransitionRequest
from app.schemas.case import (
    AttachmentRead,
    CaseCreate,
    CaseListItem,
    CaseRead,
    CaseUpdate,
)
from app.services import audit_service, case_service, render, storage, workflow_service

router = APIRouter(prefix="/cases", tags=["cases"])


def _scoped_query(db: Session, user: User):
    q = db.query(Case)
    if user.is_super:
        return q
    # Scope by division mapping unless user has wildcard / admin permissions
    perms = user.role.permissions if user.role else []
    if "*" in perms:
        return q
    division_ids = [d.id for d in user.divisions]
    if not division_ids:
        return q.filter(Case.created_by_id == user.id)
    return q.filter(Case.division_id.in_(division_ids))


@router.get("", response_model=list[CaseListItem])
def list_cases(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_READ)),
) -> list[CaseListItem]:
    rows = _scoped_query(db, user).order_by(Case.id.desc()).limit(500).all()
    return [CaseListItem.model_validate(r) for r in rows]


@router.post("", response_model=CaseRead, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_CREATE)),
) -> CaseRead:
    case = case_service.create_case(db, payload, user)
    audit_service.audit_create(
        db,
        "Case",
        case.id,
        f"Created case {case.case_no}",
        {
            "case_no": case.case_no,
            "customer_id": case.customer_id,
            "division_id": case.division_id,
            "legal_filing_amount": str(case.legal_filing_amount),
            "is_criminal": case.is_criminal,
            "is_civil": case.is_civil,
            "status": case.status,
        },
        commit=True,
    )
    return CaseRead.model_validate(case)


def _get_case_or_404(db: Session, user: User, case_id: int) -> Case:
    case = _scoped_query(db, user).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.get("/{case_id}", response_model=CaseRead)
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_READ)),
) -> CaseRead:
    return CaseRead.model_validate(_get_case_or_404(db, user, case_id))


@router.patch("/{case_id}", response_model=CaseRead)
def update_case(
    case_id: int,
    payload: CaseUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_CREATE)),
) -> CaseRead:
    case = _get_case_or_404(db, user, case_id)
    try:
        case = case_service.update_case(db, case, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return CaseRead.model_validate(case)


@router.post("/{case_id}/submit", response_model=CaseRead)
def submit_case(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_CREATE)),
) -> CaseRead:
    case = _get_case_or_404(db, user, case_id)
    try:
        case = case_service.submit_case(db, case, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return CaseRead.model_validate(case)


@router.post("/{case_id}/transition", response_model=CaseRead)
def transition_case(
    case_id: int,
    payload: TransitionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CaseRead:
    case = _get_case_or_404(db, user, case_id)
    if not workflow_service.can_act(user, case):
        raise HTTPException(
            status_code=403,
            detail=f"Not authorised to act at stage '{case.current_stage}'",
        )
    try:
        if payload.action == "approve":
            case = workflow_service.approve(db, case, user, payload.comment)
        elif payload.action == "reject":
            case = workflow_service.reject(db, case, user, payload.comment)
        elif payload.action == "request_clarification":
            case = workflow_service.request_clarification(db, case, user, payload.comment)
        elif payload.action == "resubmit":
            case = workflow_service.resubmit(db, case, user, payload.comment)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {payload.action}")
    except workflow_service.WorkflowError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return CaseRead.model_validate(case)


@router.get("/{case_id}/timeline", response_model=list[TimelineEntry])
def case_timeline(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_READ)),
) -> list[TimelineEntry]:
    case = _get_case_or_404(db, user, case_id)
    from app.models.user import User as UserModel

    actor_ids = {t.actor_id for t in case.timeline}
    actors: dict[int, str] = {}
    if actor_ids:
        for u in db.query(UserModel).filter(UserModel.id.in_(actor_ids)).all():
            actors[u.id] = u.full_name
    out: list[TimelineEntry] = []
    for t in case.timeline:
        out.append(
            TimelineEntry(
                id=t.id,
                action_type=t.action_type,
                from_status=t.from_status,
                to_status=t.to_status,
                from_stage=t.from_stage,
                to_stage=t.to_stage,
                actor_id=t.actor_id,
                actor_name=actors.get(t.actor_id, ""),
                comment=t.comment,
                created_at=t.created_at,
            )
        )
    return out


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_CREATE)),
) -> None:
    case = _get_case_or_404(db, user, case_id)
    if case.status != CASE_STATUS_DRAFT:
        raise HTTPException(status_code=400, detail="Only Draft cases can be deleted")
    audit_service.audit_delete(
        db,
        "Case",
        case.id,
        f"Deleted draft case {case.case_no}",
        {"case_no": case.case_no, "status": case.status},
    )
    storage.delete_case_dir(case.id)
    db.delete(case)
    db.commit()


# ----------------- Attachments -----------------
@router.post(
    "/{case_id}/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_attachment(
    case_id: int,
    file: UploadFile = File(...),
    category: str = Form("Supporting Document"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_CREATE)),
) -> AttachmentRead:
    case = _get_case_or_404(db, user, case_id)
    stored, size = storage.save_case_attachment(case.id, file)
    att = CaseAttachment(
        case_id=case.id,
        original_filename=file.filename or stored,
        stored_filename=stored,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=size,
        category=category,
        uploaded_by_id=user.id,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return AttachmentRead.model_validate(att)


@router.get("/{case_id}/attachments/{att_id}/download")
def download_attachment(
    case_id: int,
    att_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_READ)),
) -> FileResponse:
    case = _get_case_or_404(db, user, case_id)
    att = db.get(CaseAttachment, att_id)
    if not att or att.case_id != case.id:
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = storage.get_case_attachment_path(case.id, att.stored_filename)
    if not path.exists():
        raise HTTPException(status_code=410, detail="File missing on disk")
    return FileResponse(
        path,
        filename=att.original_filename,
        media_type=att.mime_type,
    )


@router.delete(
    "/{case_id}/attachments/{att_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_attachment(
    case_id: int,
    att_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_CREATE)),
) -> None:
    case = _get_case_or_404(db, user, case_id)
    att = db.get(CaseAttachment, att_id)
    if not att or att.case_id != case.id:
        raise HTTPException(status_code=404, detail="Attachment not found")
    storage.delete_case_attachment(case.id, att.stored_filename)
    db.delete(att)
    db.commit()


# ----------------- Print -----------------
@router.get("/{case_id}/print")
def print_case(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_READ)),
) -> Response:
    case = _get_case_or_404(db, user, case_id)
    pdf_bytes = render.render_case_pdf(db, case)
    filename = f"{case.case_no}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# This dep is used by the print route to prove auth via either header or query token.
# Kept for future enhancement; currently relies on the standard bearer token.
_ = get_current_user
