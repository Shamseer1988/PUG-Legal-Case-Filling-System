"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1 import approvals, auth, cases, health, masters, roles, users

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
api_router.include_router(masters.router, prefix="/masters")
api_router.include_router(cases.router)
api_router.include_router(approvals.router)
