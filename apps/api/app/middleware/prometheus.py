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
