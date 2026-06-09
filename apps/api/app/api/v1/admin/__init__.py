"""Admin API 라우터 — RBAC + audit chain."""

from fastapi import APIRouter

from app.api.v1.admin import (
    api_calls,
    audit,
    backup,
    emails,
    mcp_tokens,
    pois,
    rustfs,
    stats,
    trips,
    users,
)

admin_router = APIRouter()
admin_router.include_router(users.router)
admin_router.include_router(trips.router)
admin_router.include_router(pois.router)
admin_router.include_router(audit.router)
admin_router.include_router(api_calls.router)
admin_router.include_router(stats.router)
admin_router.include_router(emails.router)
admin_router.include_router(backup.router)
admin_router.include_router(mcp_tokens.router)
admin_router.include_router(rustfs.router)
