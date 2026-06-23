"""Case business logic: number generation, creation, update of cheques."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.case import (
    CASE_STATUS_DRAFT,
    STAGE_ACCOUNTANT,
    Case,
    CaseNoSequence,
    Cheque,
)
from app.models.user import User
from app.schemas.case import CaseCreate, CaseUpdate, ChequeCreate, ChequeUpdate

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


def _apply_cheques(db: Session, case: Case, payload: list[ChequeUpdate]) -> None:
    """Phase 38: diff-merge cheque rows by id.

    Earlier revisions did ``case.cheques.clear()`` then re-appended
    a fresh ``Cheque`` per payload row. That cascade-deleted every
    ``ChequeAttachment`` (linked via ``cheque_id`` FK with
    ``ondelete=CASCADE``) on every save, so any cheque-copy the
    user had attached vanished the next time they touched the form.

    Now:

    - Each existing cheque is keyed by its id.
    - Each payload row with a matching id is updated in place
      (attachments stay intact).
    - Each payload row without an id (or with an unknown id) is
      created fresh.
    - Each existing cheque whose id is missing from the payload is
      removed - this is the intended behaviour when the user
      actually deletes a row; cascade then drops its attachments.
    """
    existing_by_id: dict[int, Cheque] = {c.id: c for c in list(case.cheques)}
    kept_ids: set[int] = set()

    for item in payload:
        cid = item.id
        data = item.model_dump(exclude={"id"})
        if cid is not None and cid in existing_by_id:
            row = existing_by_id[cid]
            for k, v in data.items():
                setattr(row, k, v)
            kept_ids.add(cid)
        else:
            case.cheques.append(Cheque(**data))

    for cid, row in existing_by_id.items():
        if cid not in kept_ids:
            case.cheques.remove(row)

    db.flush()


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
        _apply_cheques(db, case, [ChequeUpdate(**c) for c in cheques])
    db.commit()
    db.refresh(case)
    return case


def submit_case(db: Session, case: Case, current_user) -> Case:
    """Delegates to workflow service so the timeline log is consistent."""
    from app.services import workflow_service

    try:
        return workflow_service.submit(db, case, current_user)
    except workflow_service.WorkflowError as e:
        raise ValueError(str(e)) from e
