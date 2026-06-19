"""Case business logic: number generation, creation, update of cheques."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.case import (
    CASE_STATUS_DRAFT,
    CASE_STATUS_SUBMITTED,
    STAGE_ACCOUNTANT,
    STAGE_SALES_MGR,
    Case,
    CaseNoSequence,
    Cheque,
)
from app.models.user import User
from app.schemas.case import CaseCreate, CaseUpdate, ChequeCreate

CASE_NO_PREFIX = "PUG-LEGAL"


def next_case_no(db: Session, year: int | None = None) -> str:
    year = year or datetime.now(timezone.utc).year
    seq = db.query(CaseNoSequence).filter(CaseNoSequence.year == year).with_for_update().first()
    if seq is None:
        seq = CaseNoSequence(year=year, last_number=0)
        db.add(seq)
        db.flush()
    seq.last_number += 1
    db.flush()
    return f"{CASE_NO_PREFIX}-{year}-{seq.last_number:04d}"


def _apply_cheques(db: Session, case: Case, payload: list[ChequeCreate]) -> None:
    case.cheques.clear()
    db.flush()
    for c in payload:
        case.cheques.append(Cheque(**c.model_dump()))


def create_case(db: Session, payload: CaseCreate, current_user: User) -> Case:
    case = Case(
        **payload.model_dump(exclude={"cheques"}),
        case_no=next_case_no(db),
        created_by_id=current_user.id,
        status=CASE_STATUS_DRAFT,
        current_stage=STAGE_ACCOUNTANT,
    )
    db.add(case)
    db.flush()
    if payload.cheques:
        for c in payload.cheques:
            case.cheques.append(Cheque(**c.model_dump()))
    db.commit()
    db.refresh(case)
    return case


def update_case(db: Session, case: Case, payload: CaseUpdate) -> Case:
    if case.status != CASE_STATUS_DRAFT:
        raise ValueError("Only Draft cases can be edited")
    data = payload.model_dump(exclude_unset=True)
    cheques = data.pop("cheques", None)
    for k, v in data.items():
        setattr(case, k, v)
    if cheques is not None:
        _apply_cheques(db, case, [ChequeCreate(**c) for c in cheques])
    db.commit()
    db.refresh(case)
    return case


def submit_case(db: Session, case: Case) -> Case:
    if case.status != CASE_STATUS_DRAFT:
        raise ValueError("Only Draft cases can be submitted")
    if not case.cheques:
        raise ValueError("At least one cheque is required before submitting")
    case.status = CASE_STATUS_SUBMITTED
    case.current_stage = STAGE_SALES_MGR
    case.submitted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(case)
    return case
