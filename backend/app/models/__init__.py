"""Aggregate models import."""

from app.db.base import Base
from app.models.audit import AuditLog
from app.models.backup import BackupJob, RestoreJob
from app.models.case import (
    Case,
    CaseAttachment,
    CaseNoSequence,
    CaseStatusUpdate,
    CaseTransitionAttachment,
    Cheque,
    ChequeAttachment,
)
from app.models.case_view import CaseView
from app.models.closure import CaseClosure
from app.models.court import CashRequest, CourtFiling, Hearing
from app.models.job_run import JobRun
from app.models.masters import (
    Bank,
    CaseChequeSignatory,
    CaseType,
    Customer,
    CustomerPartner,
    Division,
    DocumentLocation,
    Lawyer,
    LawyerDivisionMap,
    Salesman,
)
from app.models.notification import EmailLog, EmailLogAttachment, Notification
from app.models.physical_document import DocumentCustodyLog, PhysicalDocument
from app.models.push import PushSubscription
from app.models.saved_filter import SavedReportFilter
from app.models.scheduled_report import ScheduledReport, ScheduledReportRun
from app.models.settings import SettingsKV
from app.models.user import Role, User, UserDivisionMap

__all__ = [
    "Base",
    "Role",
    "User",
    "UserDivisionMap",
    "Division",
    "Bank",
    "Salesman",
    "Customer",
    "CustomerPartner",
    "CaseChequeSignatory",
    "DocumentLocation",
    "PhysicalDocument",
    "DocumentCustodyLog",
    "Lawyer",
    "LawyerDivisionMap",
    "CaseType",
    "Case",
    "Cheque",
    "ChequeAttachment",
    "CaseView",
    "CaseAttachment",
    "CaseNoSequence",
    "CaseStatusUpdate",
    "CaseTransitionAttachment",
    "CourtFiling",
    "Hearing",
    "CashRequest",
    "CaseClosure",
    "Notification",
    "EmailLog",
    "EmailLogAttachment",
    "PushSubscription",
    "ScheduledReport",
    "ScheduledReportRun",
    "SavedReportFilter",
    "AuditLog",
    "BackupJob",
    "RestoreJob",
    "JobRun",
    "SettingsKV",
]
