"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1 import (
    approvals,
    audit,
    auth,
    backup,
    bulk_admin,
    cases,
    court,
    dashboard,
    diagnostics,
    email_log,
    health,
    masters,
    notifications,
    reports,
    roles,
    saved_filters,
    scheduled_reports,
    settings as settings_router,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
api_router.include_router(masters.router, prefix="/masters")
api_router.include_router(cases.router)
api_router.include_router(approvals.router)
api_router.include_router(bulk_admin.router)
api_router.include_router(court.cases_router)
api_router.include_router(court.cash_router)
api_router.include_router(court.hearings_router)
api_router.include_router(notifications.router)
api_router.include_router(email_log.router)
api_router.include_router(saved_filters.router)
api_router.include_router(reports.router)
api_router.include_router(scheduled_reports.router)
api_router.include_router(audit.router)
api_router.include_router(backup.router)
api_router.include_router(settings_router.router)
api_router.include_router(diagnostics.router)
api_router.include_router(dashboard.router)
