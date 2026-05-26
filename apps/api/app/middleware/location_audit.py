"""위치 감사 미들웨어 — `docs/compliance/lbs-act.md` §3.

좌표(`lat`/`lng`)가 query/body에 있는 endpoint에 자동 적재. content_hash chain.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.db.session import async_session_factory
from app.models.audit import LocationAccessLog
from app.services.hash_chain import GENESIS_HASH, compute_content_hash, sha256_hex

log = structlog.get_logger("location_audit")

PURPOSE_BY_PATH: dict[str, str] = {
    "/features/in-bounds": "viewport_query",
    "/features/nearby": "nearby_attractions",
    "/regions/covering-point": "region_covering",
    "/regions/within-radius": "region_radius",
}


class LocationAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)

        purpose = _classify_purpose(request.url.path)
        if purpose is None:
            return response
        if response.status_code >= 400:
            return response

        try:
            lat, lng = _extract_coord(request)
        except ValueError:
            return response

        user_id_str = request.headers.get("X-User-Id") or getattr(
            request.state, "user_id", None
        )
        if user_id_str is None:
            return response

        try:
            user_id = uuid.UUID(str(user_id_str))
        except ValueError:
            return response

        request_id = request.headers.get("X-Request-Id")
        if request_id is None:
            return response

        ip_hash = sha256_hex(request.client.host) if request.client else sha256_hex("")

        try:
            async with async_session_factory() as session:
                await _append_log(
                    session,
                    user_id=user_id,
                    endpoint=request.url.path,
                    purpose=purpose,
                    lat=lat,
                    lng=lng,
                    request_id=uuid.UUID(request_id),
                    ip_hash=ip_hash,
                )
        except Exception as exc:
            log.warning("location_audit.append_failed", error=str(exc))

        return response


def _classify_purpose(path: str) -> str | None:
    if path in PURPOSE_BY_PATH:
        return PURPOSE_BY_PATH[path]
    if path.startswith("/features/") and path.endswith("/weather"):
        return "weather_at_coord"
    if path == "/features/requests":
        return "feature_request"
    return None


def _extract_coord(request: Request) -> tuple[Decimal | None, Decimal | None]:
    lat = request.query_params.get("lat") or request.query_params.get("latitude")
    lng = request.query_params.get("lng") or request.query_params.get("longitude")
    if lat is None and lng is None:
        return None, None
    return (
        Decimal(lat) if lat is not None else None,
        Decimal(lng) if lng is not None else None,
    )


async def _append_log(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    endpoint: str,
    purpose: str,
    lat: Decimal | None,
    lng: Decimal | None,
    request_id: uuid.UUID,
    ip_hash: str,
) -> None:
    last = await session.scalar(
        select(LocationAccessLog).order_by(LocationAccessLog.log_id.desc()).limit(1)
    )
    prev_hash = last.content_hash if last else GENESIS_HASH
    now = datetime.now(UTC)
    payload = {
        "user_id": str(user_id),
        "occurred_at": now.isoformat(),
        "endpoint": endpoint,
        "purpose": purpose,
        "lat": str(lat) if lat is not None else None,
        "lng": str(lng) if lng is not None else None,
        "request_id": str(request_id),
        "ip_hash": ip_hash,
    }
    content_hash = compute_content_hash(prev_hash, payload)
    row = LocationAccessLog(
        user_id=user_id,
        occurred_at=now,
        endpoint=endpoint,
        purpose=purpose,
        lat=lat,
        lng=lng,
        request_id=request_id,
        ip_hash=ip_hash,
        prev_hash=prev_hash,
        content_hash=content_hash,
    )
    session.add(row)
    await session.commit()
