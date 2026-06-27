"""Admin API 라우터 — RBAC + audit chain."""

from fastapi import APIRouter

from app.api.v1.admin import (
    api_calls,
    audit,
    backup,
    category_mappings,
    debug_logs,
    dedup_review,
    emails,
    etl,
    feature_requests,
    features,
    files,
    integrity,
    mcp_tokens,
    notice_plans,
    pois,
    provider_sync,
    reset,
    rustfs,
    seed,
    settings,
    stats,
    system,
    trips,
    users,
)
from app.api.v1.admin.dev_safety import is_dev_safety_route_enabled

admin_router = APIRouter()
admin_router.include_router(users.router)
admin_router.include_router(trips.router)
admin_router.include_router(pois.router)
admin_router.include_router(features.router)
admin_router.include_router(feature_requests.router)
admin_router.include_router(category_mappings.router)
admin_router.include_router(dedup_review.router)
admin_router.include_router(provider_sync.router)
admin_router.include_router(integrity.router)
admin_router.include_router(debug_logs.router)
admin_router.include_router(files.router)
admin_router.include_router(audit.router)
admin_router.include_router(api_calls.router)
admin_router.include_router(stats.router)
admin_router.include_router(emails.router)
admin_router.include_router(backup.router)
admin_router.include_router(mcp_tokens.router)
admin_router.include_router(rustfs.router)
admin_router.include_router(notice_plans.router)
admin_router.include_router(system.router)
admin_router.include_router(etl.router)
admin_router.include_router(settings.router)

if is_dev_safety_route_enabled():
    admin_router.include_router(seed.router)
    admin_router.include_router(reset.router)
