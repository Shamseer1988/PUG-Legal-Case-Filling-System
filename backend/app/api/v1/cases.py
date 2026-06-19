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
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_permission
from app.core.permissions import CASES_CREATE, CASES_READ
from app.db.session import get_db
from app.models.case import CASE_STATUS_DRAFT, Case, CaseAttachment
from app.models.user import User
from app.schemas.case import (
    AttachmentRead,
    CaseCreate,
    CaseListItem,
    CaseRead,
    CaseUpdate,
)
from app.services import case_service, render, storage

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
        case = case_service.submit_case(db, case)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return CaseRead.model_validate(case)


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_CREATE)),
) -> None:
    case = _get_case_or_404(db, user, case_id)
    if case.status != CASE_STATUS_DRAFT:
        raise HTTPException(status_code=400, detail="Only Draft cases can be deleted")
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
@router.get("/{case_id}/print", response_class=HTMLResponse)
def print_case(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(CASES_READ)),
) -> HTMLResponse:
    case = _get_case_or_404(db, user, case_id)
    html = render.render_case_print(db, case)
    return HTMLResponse(html)


# This dep is used by the print route to prove auth via either header or query token.
# Kept for future enhancement; currently relies on the standard bearer token.
_ = get_current_user
