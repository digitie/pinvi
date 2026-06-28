"""Prometheus HTTP metrics for FastAPI.

Route labels use FastAPI templates (for example ``/trips/{trip_id}``) instead of
raw URLs to keep Prometheus series cardinality bounded.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from time import perf_counter
from typing import Final, cast

from fastapi import HTTPException, Request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import settings

UNKNOWN_ROUTE: Final[str] = "__unmatched__"

HTTP_REQUESTS_TOTAL = Counter(
    "pinvi_api_http_requests_total",
    "Total Pinvi API HTTP requests.",
    ("method", "route", "status_code"),
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "pinvi_api_http_request_duration_seconds",
    "Pinvi API HTTP request duration in seconds.",
    ("method", "route", "status_code"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "pinvi_api_http_requests_in_progress",
    "Pinvi API HTTP requests currently in progress.",
    ("method",),
    multiprocess_mode="livesum",
)
DB_POOL_CONNECTIONS = Gauge(
    "pinvi_api_db_pool_connections",
    "Pinvi SQLAlchemy DB pool connection counts by state.",
    ("state",),
    multiprocess_mode="livesum",
)


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not settings.pinvi_prometheus_metrics_enabled:
            return await call_next(request)
        if _is_excluded_path(request.url.path):
            return await call_next(request)

        method = request.method
        status_code = 500
        start = perf_counter()
        HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            elapsed = perf_counter() - start
            route = _route_template(request)
            labels = {
                "method": method,
                "route": route,
                "status_code": str(status_code),
            }
            HTTP_REQUESTS_TOTAL.labels(**labels).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(**labels).observe(elapsed)
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()


async def prometheus_metrics() -> Response:
    if not settings.pinvi_prometheus_metrics_enabled:
        raise HTTPException(status_code=404)
    update_db_pool_metrics()
    return Response(content=_generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _is_excluded_path(path: str) -> bool:
    return path in settings.pinvi_prometheus_exclude_paths


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return UNKNOWN_ROUTE


def _generate_latest() -> bytes:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multi_process_collector = cast(
            Callable[[CollectorRegistry], object], multiprocess.MultiProcessCollector
        )
        multi_process_collector(registry)
        return bytes(generate_latest(registry))
    return bytes(generate_latest())


def update_db_pool_metrics() -> None:
    """SQLAlchemy pool 상태를 scrape 직전에 gauge로 반영한다."""

    for state, value in _db_pool_snapshot().items():
        DB_POOL_CONNECTIONS.labels(state=state).set(value)


def _db_pool_snapshot() -> dict[str, float]:
    try:
        from app.db import session as db_session

        pool = db_session.engine.sync_engine.pool
        return {
            "size": _pool_value(pool, "size"),
            "checked_in": _pool_value(pool, "checkedin"),
            "checked_out": _pool_value(pool, "checkedout"),
            "overflow": _pool_value(pool, "overflow"),
        }
    except Exception:
        return {"size": 0.0, "checked_in": 0.0, "checked_out": 0.0, "overflow": 0.0}


def _pool_value(pool: object, attr: str) -> float:
    value = getattr(pool, attr, None)
    if not callable(value):
        return 0.0
    try:
        return float(value())
    except Exception:
        return 0.0
