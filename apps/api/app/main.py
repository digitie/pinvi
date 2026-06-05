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
from app.core.config import settings
from app.core.errors import http_exception_handler, validation_exception_handler
from app.core.logging import configure_logging, get_logger
from app.etl_bridge.krtour_map import krtour_map_lifespan
from app.middleware.geofence import GeofenceMiddleware
from app.middleware.location_audit import LocationAuditMiddleware
from app.middleware.request_id import RequestIdMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log = get_logger("startup")
    log.info(
        "tripmate.api.start",
        version=__version__,
        environment=settings.tripmate_environment,
    )
    # python-krtour-map client lifespan (ADR-002) — 라이브러리 ready 전이면 client=None
    async with krtour_map_lifespan(app):
        yield
    log.info("tripmate.api.stop")


app = FastAPI(
    title="TripMate API",
    version=__version__,
    description="TripMate v2 backend — `app` schema 소유. `feature` schema는 python-krtour-map.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(LocationAuditMiddleware)
app.add_middleware(GeofenceMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.tripmate_cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

app.include_router(api_router)
