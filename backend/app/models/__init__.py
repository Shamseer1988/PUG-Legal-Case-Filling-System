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
)
from app.models.closure import CaseClosure
from app.models.court import CashRequest, CourtFiling, Hearing
from app.models.masters import (
    Bank,
    CaseType,
    Customer,
    Division,
    Lawyer,
    LawyerDivisionMap,
    Salesman,
)
from app.models.notification import EmailLog, Notification
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
    "Lawyer",
    "LawyerDivisionMap",
    "CaseType",
    "Case",
    "Cheque",
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
    "ScheduledReport",
    "ScheduledReportRun",
    "AuditLog",
    "BackupJob",
    "RestoreJob",
    "SettingsKV",
]
