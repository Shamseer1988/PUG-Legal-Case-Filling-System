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
from app.models.masters import CustomerPartner
from app.models.physical_document import (
    DOC_KIND_CASE_FOLDER,
    DocumentCustodyLog,
    PhysicalDocument,
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


def _apply_cheque_signatories(
    db: Session, case: Case, partner_ids: list[int] | None
) -> None:
    """Phase 40: replace the case -> partner join rows with the
    payload-supplied ids.

    Validation:
      - duplicates are silently de-duped
      - every id must reference an active CustomerPartner that
        belongs to ``case.customer_id`` (otherwise we'd allow
        cross-customer leakage)
    """
    if partner_ids is None:
        return  # caller didn't touch the field
    uniq = list(dict.fromkeys(int(x) for x in partner_ids))
    if uniq:
        rows = (
            db.query(CustomerPartner)
            .filter(CustomerPartner.id.in_(uniq))
            .all()
        )
        found = {r.id: r for r in rows}
        for pid in uniq:
            if pid not in found:
                raise ValueError(f"Unknown partner id: {pid}")
            if found[pid].customer_id != case.customer_id:
                raise ValueError(
                    f"Partner {pid} does not belong to the case's customer"
                )
        case.cheque_signatories = [found[pid] for pid in uniq]
    else:
        case.cheque_signatories = []
    db.flush()


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
        **payload.model_dump(
            exclude={"cheques", "cheque_signatory_partner_ids"}
        ),
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
    # Phase 40: link joint cheque signatories. Validation runs
    # even at create-time so a malformed payload fails fast.
    _apply_cheque_signatories(db, case, payload.cheque_signatory_partner_ids)

    # Phase 41B: auto-register one "Case Folder" physical document
    # so every case starts the chain-of-custody log on day 1.
    # Filed and Closed transitions check this row's whereabouts -
    # see workflow_service.guard_filed / guard_closed.
    folder = PhysicalDocument(
        case_id=case.id,
        kind=DOC_KIND_CASE_FOLDER,
        label="Case Folder",
        notes="Physical originals bundle for this case",
        is_active=True,
    )
    db.add(folder)
    db.flush()
    db.add(
        DocumentCustodyLog(
            document_id=folder.id,
            transferred_at=datetime.utcnow(),
            recorded_by_user_id=current_user.id,
            from_user_id=None,
            to_user_id=None,
            location_id=None,
            location_text="",
            note="Case opened",
        )
    )
    db.flush()

    db.commit()
    db.refresh(case)
    return case


def can_edit_case(case: Case, user: User) -> bool:
    """Phase 39: an Accountant can keep editing a case until the
    Sales Manager takes their first action.

    Edit-window rules:
    - Draft -> the creator can edit (existing behaviour).
    - Submitted AND still at Sales Manager AND user is the creator
      -> the Accountant can keep fixing data they typed before SM
      gets to it. Once SM approves / rejects / requests clarification,
      the stage or status flips and the window closes.
    - Anything else -> locked.

    Super users keep their bypass (mostly used for admin fix-ups).
    """
    if user.is_super:
        return True
    if case.status == CASE_STATUS_DRAFT and case.created_by_id == user.id:
        return True
    if (
        case.status == CASE_STATUS_SUBMITTED
        and case.current_stage == STAGE_SALES_MGR
        and case.created_by_id == user.id
    ):
        return True
    return False


def update_case(db: Session, case: Case, payload: CaseUpdate, user: User) -> Case:
    if not can_edit_case(case, user):
        raise ValueError(
            "Case is no longer editable: an approver has already acted on it"
            if case.status != CASE_STATUS_DRAFT
            else "Only the case owner can edit a draft"
        )
    data = payload.model_dump(exclude_unset=True)
    cheques = data.pop("cheques", None)
    signatory_ids = data.pop("cheque_signatory_partner_ids", None)
    for k, v in data.items():
        setattr(case, k, v)
    if cheques is not None:
        _apply_cheques(db, case, [ChequeUpdate(**c) for c in cheques])
    _apply_cheque_signatories(db, case, signatory_ids)
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
