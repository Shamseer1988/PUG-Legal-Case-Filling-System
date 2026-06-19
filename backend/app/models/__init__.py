"""Aggregate models import — extended in subsequent phases."""

from app.db.base import Base
from app.models.masters import Bank, CaseType, Customer, Division, Lawyer, Salesman
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
    "CaseType",
]
