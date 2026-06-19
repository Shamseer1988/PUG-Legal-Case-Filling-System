"""Approval inbox + workflow descriptor."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.workflow import WORKFLOW_STAGES
from app.db.session import get_db
from app.models.user import User
from app.schemas.approval import InboxItem, StageDescriptor, WorkflowDescriptor
from app.services import workflow_service

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("/inbox", response_model=list[InboxItem])
def inbox(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[InboxItem]:
    cases = workflow_service.inbox_for(db, user)
    out: list[InboxItem] = []
    for c in cases:
        user_field = workflow_service.assigned_user_field_for(c)
        assigned_to_me = bool(user_field) and getattr(c, user_field) == user.id  # type: ignore[arg-type]
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
