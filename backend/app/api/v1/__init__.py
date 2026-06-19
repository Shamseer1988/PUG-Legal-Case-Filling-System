"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1 import approvals, auth, cases, court, health, masters, roles, users

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
api_router.include_router(masters.router, prefix="/masters")
api_router.include_router(cases.router)
api_router.include_router(approvals.router)

# Phase 4 court / hearings / cash routers
api_router.include_router(court.cases_router)
api_router.include_router(court.cash_router)
api_router.include_router(court.hearings_router)
