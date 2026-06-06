"""Admin API 라우터 — RBAC + audit chain."""

from fastapi import APIRouter

from app.api.v1.admin import audit, backup, emails, pois, trips, users

admin_router = APIRouter()
admin_router.include_router(users.router)
admin_router.include_router(trips.router)
admin_router.include_router(pois.router)
admin_router.include_router(audit.router)
admin_router.include_router(emails.router)
admin_router.include_router(backup.router)
