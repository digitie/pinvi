"""FastAPI 진입점.

자세히는 `docs/api/README.md` + `docs/conventions/coding-style.md` §2.4.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import api_router
from app.clients.kor_travel_geo import kor_travel_geo_client_lifespan
from app.clients.kor_travel_map import kor_travel_map_client_lifespan
from app.clients.kor_travel_map_admin import kor_travel_map_admin_client_lifespan
from app.core.config import settings
from app.core.errors import http_exception_handler, validation_exception_handler
from app.core.logging import configure_logging, get_logger
from app.middleware.geofence import GeofenceMiddleware, validate_geofence_configuration
from app.middleware.location_audit import LocationAuditMiddleware
from app.middleware.prometheus import PrometheusMetricsMiddleware, prometheus_metrics
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.services.location_audit import location_audit_outbox_worker_lifespan
from app.services.telegram_outbox import telegram_outbox_worker_lifespan


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log = get_logger("startup")
    log.info(
        "pinvi.api.start",
        version=__version__,
        environment=settings.pinvi_environment,
    )
    for warning in validate_geofence_configuration():
        log.warning("pinvi.geofence.config_warning", warning=warning)
    # kor-travel-map OpenAPI HTTP client (ADR-026/027) — feature read/batch 경로.
    # 레거시 in-process Protocol stub(etl_bridge)은 T-175에서 제거됨.
    # admin client(T-180)는 사용자 제안 승인 시 `/v1/admin/features*` change API 호출.
    async with (
        kor_travel_map_client_lifespan(app),
        kor_travel_map_admin_client_lifespan(app),
        kor_travel_geo_client_lifespan(app),
        location_audit_outbox_worker_lifespan(app),
        telegram_outbox_worker_lifespan(app),
    ):
        yield
    log.info("pinvi.api.stop")


app = FastAPI(
    title="Pinvi API",
    version=__version__,
    description="Pinvi v2 backend — `app` schema 소유. `feature` schema는 kor-travel-map.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(LocationAuditMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(GeofenceMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(PrometheusMetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.pinvi_cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

if settings.pinvi_prometheus_metrics_enabled:
    app.add_api_route(
        settings.pinvi_prometheus_metrics_path,
        prometheus_metrics,
        methods=["GET"],
        include_in_schema=False,
    )

app.include_router(api_router)
