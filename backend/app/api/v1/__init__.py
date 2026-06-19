"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1 import (
    approvals,
    auth,
    cases,
    court,
    email_log,
    health,
    masters,
    notifications,
    reports,
    roles,
    scheduled_reports,
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
api_router.include_router(court.cases_router)
api_router.include_router(court.cash_router)
api_router.include_router(court.hearings_router)
api_router.include_router(notifications.router)
api_router.include_router(email_log.router)
api_router.include_router(reports.router)
api_router.include_router(scheduled_reports.router)
