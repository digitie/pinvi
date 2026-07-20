"""위치 감사 미들웨어 — `docs/compliance/lbs-act.md` §3.

좌표(`lat`/`lon`)가 query/body에 있는 endpoint 접근을 자동 적재. T-146(D-20): 요청 경로에서는
체인 해시를 동기 계산하지 않고 **async outbox에 빠르게 append**하고, worker가 체인으로 drain한다
(단일 노드 hotspot 제거). 체인 로직은 `app.services.location_audit`.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.db.session import async_session_factory
from app.services.hash_chain import sha256_hex
from app.services.location_audit import append_location_log, enqueue_location_audit_outbox

log = structlog.get_logger("location_audit")

PURPOSE_BY_PATH: dict[str, str] = {
    "/features/in-bounds": "viewport_query",
    "/features/nearby": "nearby_attractions",
    "/regions/covering-point": "region_covering",
    "/regions/within-radius": "region_radius",
    # "내 주변 검색"으로 사용자 좌표를 Kakao에 제3자 제공(ADR-054 §9). 좌표는 핸들러가
    # request.state.location_audit_coord로 세팅하며, 좌표 없는 키워드 검색은 감사 대상이 아니다.
    "/search": "third_party_place_search",
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

        # 좌표가 실제로 없으면 위치정보 제3자 제공/사용이 없었던 것이므로 감사하지 않는다.
        # (좌표 없는 키워드-only `/search` 등이 거짓 감사 기록을 남기지 않게 한다. 다른 감사 경로는
        # 모두 필수 좌표를 지니므로 영향 없음.)
        if lat is None and lng is None:
            return response

        user_id_str = getattr(request.state, "user_id", None)
        if user_id_str is None:
            return response

        try:
            user_id = uuid.UUID(str(user_id_str))
        except ValueError:
            return response

        request_id_raw = (
            getattr(request.state, "request_id", None)
            or request.headers.get("X-Request-Id")
            or response.headers.get("X-Request-Id")
        )
        if request_id_raw is None:
            return response
        try:
            request_id = uuid.UUID(str(request_id_raw))
        except ValueError:
            return response

        ip_hash = sha256_hex(request.client.host) if request.client else sha256_hex("")

        try:
            async with async_session_factory() as session:
                await enqueue_location_audit_outbox(
                    session,
                    user_id=user_id,
                    endpoint=request.url.path,
                    purpose=purpose,
                    lat=lat,
                    lng=lng,
                    request_id=request_id,
                    ip_hash=ip_hash,
                )
        except Exception as exc:
            log.warning("location_audit.enqueue_failed", error=str(exc))

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
    state_coord = getattr(request.state, "location_audit_coord", None)
    if state_coord is not None:
        lat, lng = state_coord
        return (
            Decimal(str(lat)) if lat is not None else None,
            Decimal(str(lng)) if lng is not None else None,
        )

    lat = request.query_params.get("lat") or request.query_params.get("latitude")
    lng = (
        request.query_params.get("lng")
        or request.query_params.get("lon")
        or request.query_params.get("longitude")
    )
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
    """동기 체인 append(legacy/직접 적재). 체인 로직은 services.location_audit로 이전."""
    await append_location_log(
        session,
        user_id=user_id,
        endpoint=endpoint,
        purpose=purpose,
        lat=lat,
        lng=lng,
        request_id=request_id,
        ip_hash=ip_hash,
    )
