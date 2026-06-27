"""Admin API 라우터 — RBAC + audit chain."""

from fastapi import APIRouter

from app.api.v1.admin import (
    api_calls,
    audit,
    backup,
    emails,
    feature_requests,
    features,
    mcp_tokens,
    notice_plans,
    pois,
    rustfs,
    stats,
    system,
    trips,
    users,
)

admin_router = APIRouter()
admin_router.include_router(users.router)
admin_router.include_router(trips.router)
admin_router.include_router(pois.router)
admin_router.include_router(features.router)
admin_router.include_router(feature_requests.router)
admin_router.include_router(audit.router)
admin_router.include_router(api_calls.router)
admin_router.include_router(stats.router)
admin_router.include_router(emails.router)
admin_router.include_router(backup.router)
admin_router.include_router(mcp_tokens.router)
admin_router.include_router(rustfs.router)
admin_router.include_router(notice_plans.router)
admin_router.include_router(system.router)
