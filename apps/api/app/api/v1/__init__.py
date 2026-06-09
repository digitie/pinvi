"""FastAPI v1 라우터 모음."""

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    features,
    geo,
    healthz,
    notice_plans,
    oauth,
    pois,
    storage,
    trips,
    users,
    ws,
)
from app.api.v1.admin import admin_router
from app.mcp.server import router as mcp_router
from app.webhooks import resend as resend_webhook

api_router = APIRouter()
api_router.include_router(healthz.router)
api_router.include_router(auth.router)
api_router.include_router(oauth.router)
api_router.include_router(users.router)
api_router.include_router(trips.router)
api_router.include_router(pois.router)
api_router.include_router(ws.router)
api_router.include_router(notice_plans.router)
api_router.include_router(features.router)
api_router.include_router(geo.geo_router)
api_router.include_router(geo.regions_router)
api_router.include_router(storage.router)
api_router.include_router(mcp_router)
api_router.include_router(resend_webhook.router)
api_router.include_router(admin_router)
