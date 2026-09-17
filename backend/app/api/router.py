from fastapi import APIRouter

from app.api.routes import (
    admin,
    audit,
    auth,
    claims,
    dashboard,
    documents,
    health,
    investigations,
    reports,
    users,
    verification,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(claims.router)
api_router.include_router(documents.router)
api_router.include_router(verification.router)
api_router.include_router(investigations.router)
api_router.include_router(reports.router)
api_router.include_router(audit.router)
api_router.include_router(users.router)
api_router.include_router(admin.router)
