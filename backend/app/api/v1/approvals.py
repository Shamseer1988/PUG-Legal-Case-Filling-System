"""Approval inbox + workflow descriptor + bulk transitions."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.data_scope import allowed_division_ids
from app.core.deps import get_current_user
from app.core.workflow import WORKFLOW_STAGES
from app.db.session import get_db
from app.models.case import Case
from app.models.user import User
from app.schemas.approval import (
    BulkTransitionItem,
    BulkTransitionRequest,
    BulkTransitionResult,
    InboxItem,
    StageDescriptor,
    WorkflowDescriptor,
)
from app.services import workflow_service

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("/inbox", response_model=list[InboxItem])
def inbox(
    scope: str = "all",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[InboxItem]:
    """Cases waiting for action.

    ``scope`` is one of:
      - ``all`` (default): every case the user could act on at its
        current stage, including ones assigned to a teammate.
      - ``mine``: only cases where the user is explicitly listed in
        the signatory slot for the current stage (e.g.
        ``sales_manager_id == user.id`` when stage = Sales Manager).
        Clarification-requested cases authored by the user are also
        included so they can be re-submitted.
    """
    cases = workflow_service.inbox_for(db, user)
    out: list[InboxItem] = []
    for c in cases:
        user_field = workflow_service.assigned_user_field_for(c)
        assigned_to_me = bool(user_field) and getattr(c, user_field) == user.id  # type: ignore[arg-type]
        # Clarification cases: "mine" if the clarification is aimed at
        # the current user's stage or (for Accountant targets) at the
        # case creator.
        if not assigned_to_me and c.status == "Clarification Requested":
            target = c.clarify_from_stage or "Accountant"
            if target == "Accountant":
                assigned_to_me = c.created_by_id == user.id
            else:
                from app.core.workflow import get_stage as _get_stage
                _tcfg = _get_stage(target)
                if _tcfg and _tcfg.user_field:
                    assigned_to_me = getattr(c, _tcfg.user_field, None) == user.id
        if scope == "mine" and not assigned_to_me:
            continue
        out.append(
            InboxItem(
                id=c.id,
                case_no=c.case_no,
                customer_id=c.customer_id,
                division_id=c.division_id,
                current_stage=c.current_stage,
                status=c.status,
                stage_entered_at=c.stage_entered_at,
                sla_due_at=c.sla_due_at,
                overdue=workflow_service.is_overdue(c),
                legal_filing_amount=str(c.legal_filing_amount),
                assigned_to_me=assigned_to_me,
            )
        )
    return out


@router.get("/workflow", response_model=WorkflowDescriptor)
def workflow_descriptor(_: User = Depends(get_current_user)) -> WorkflowDescriptor:
    return WorkflowDescriptor(
        stages=[
            StageDescriptor(
                key=s.key,
                stage=s.stage,
                permission=s.permission,
                user_field=s.user_field,
                next_stage=s.next_stage,
                sla_hours=s.sla_hours,
            )
            for s in WORKFLOW_STAGES
        ],
        accountant_stage="Accountant",
        lawyer_stage="Lawyer",
    )


# ---------------------------------------------------------------------------
# Bulk transitions (Phase 28)
# ---------------------------------------------------------------------------
def _scoped_case(db: Session, user: User, case_id: int) -> Case | None:
    """Return the case if it exists AND the user is within division scope."""
    q = db.query(Case)
    allowed = allowed_division_ids(user)
    if allowed is not None and allowed:
        q = q.filter(Case.division_id.in_(allowed))
    return q.filter(Case.id == case_id).first()


@router.post("/bulk-transition", response_model=BulkTransitionResult)
def bulk_transition(
    payload: BulkTransitionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BulkTransitionResult:
    """Apply one approval action to a batch of cases.

    Each case is evaluated independently:
      - if the user isn't authorised for the case's current stage,
        it is skipped with a per-row "Not authorised" reason;
      - workflow errors (wrong status, missing comment for reject,
        ...) are captured per-row and don't abort the batch;
      - successful transitions are committed by ``workflow_service``
        so a single broken transition doesn't roll the batch back.

    Returns a per-case result so the UI can show "12 approved,
    2 skipped (not authorised)" without an extra request.
    """
    # ``reject`` and ``request_clarification`` require a non-empty
    # comment in the single-case endpoint; enforce the same here so
    # the user gets a clear error before we touch any rows.
    if payload.action in ("reject", "request_clarification") and not payload.comment.strip():
        raise HTTPException(
            status_code=400,
            detail=f"A comment is required for action '{payload.action}'",
        )

    # De-duplicate while preserving order so the UI's reported list
    # matches what the user picked.
    seen: set[int] = set()
    ordered_ids: list[int] = []
    for cid in payload.case_ids:
        if cid not in seen:
            seen.add(cid)
            ordered_ids.append(cid)

    items: list[BulkTransitionItem] = []
    succeeded = 0
    failed = 0

    for case_id in ordered_ids:
        case = _scoped_case(db, user, case_id)
        if not case:
            items.append(
                BulkTransitionItem(
                    case_id=case_id, ok=False, detail="Case not found or out of scope"
                )
            )
            failed += 1
            continue

        case_no = case.case_no
        if not workflow_service.can_act(user, case):
            items.append(
                BulkTransitionItem(
                    case_id=case_id,
                    case_no=case_no,
                    ok=False,
                    detail=f"Not authorised at stage '{case.current_stage}'",
                )
            )
            failed += 1
            continue

        try:
            if payload.action == "approve":
                workflow_service.approve(db, case, user, payload.comment)
            elif payload.action == "reject":
                workflow_service.reject(db, case, user, payload.comment)
            elif payload.action == "request_clarification":
                workflow_service.request_clarification(
                    db, case, user, payload.comment
                )
            elif payload.action == "lawyer_approve":
                workflow_service.lawyer_approve(db, case, user, payload.comment)
            else:
                raise workflow_service.WorkflowError(
                    f"Unknown action: {payload.action}"
                )
        except workflow_service.WorkflowError as e:
            db.rollback()
            items.append(
                BulkTransitionItem(
                    case_id=case_id, case_no=case_no, ok=False, detail=str(e)
                )
            )
            failed += 1
            continue
        except Exception as e:  # pragma: no cover - defensive
            db.rollback()
            items.append(
                BulkTransitionItem(
                    case_id=case_id,
                    case_no=case_no,
                    ok=False,
                    detail=f"{type(e).__name__}: {e}",
                )
            )
            failed += 1
            continue

        items.append(
            BulkTransitionItem(case_id=case_id, case_no=case_no, ok=True, detail="OK")
        )
        succeeded += 1

    return BulkTransitionResult(
        succeeded=succeeded, failed=failed, items=items
    )
