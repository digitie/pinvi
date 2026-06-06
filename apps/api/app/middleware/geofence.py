"""ADR-018 한국 전용 geofencing FastAPI fallback."""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Awaitable, Callable, Iterable
from typing import cast

from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import async_session_factory
from app.models.user import User

ADMIN_ROLES = {"admin", "operator", "cpo"}
RoleResolver = Callable[[str], Awaitable[Iterable[str]] | Iterable[str]]


def _normalized_set(values: Iterable[str]) -> set[str]:
    return {value.strip().upper() for value in values if value.strip()}


def _roles_set(values: Iterable[str] | None) -> set[str]:
    if values is None:
        return set()
    return {role for role in values if isinstance(role, str)}


async def _current_user_roles(request: Request) -> set[str]:
    token = request.cookies.get("tripmate_access")
    if not token:
        return set()
    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        return set()
    subject = payload.get("sub")
    if not isinstance(subject, str):
        return set()

    resolver = cast(
        RoleResolver | None,
        getattr(request.app.state, "geofence_role_resolver", None),
    )
    if resolver is not None:
        resolved = resolver(subject)
        if inspect.isawaitable(resolved):
            resolved = await resolved
        return _roles_set(resolved)

    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        return set()

    async with async_session_factory() as session:
        roles = await session.scalar(select(User.roles).where(User.user_id == user_id))
    return _roles_set(roles)


def _is_bypass_path(path: str) -> bool:
    return any(
        path == bypass or path.startswith(f"{bypass}/")
        for bypass in settings.tripmate_geofence_bypass_paths
    )


def _detected_country(request: Request) -> str | None:
    header = settings.tripmate_geofence_country_header
    country = request.headers.get(header)
    if country:
        return country.strip().upper()
    return None


def _blocked_response(country: str | None) -> JSONResponse:
    detected = country or "UNKNOWN"
    return JSONResponse(
        status_code=451,
        content={
            "error": {
                "code": "GEO_BLOCKED",
                "message": "TripMate는 대한민국 거주자 전용 서비스입니다.",
                "details": {
                    "detected_country": detected,
                    "contact": "support@tripmate.kr",
                },
            }
        },
        headers={"X-TripMate-Geofence": "blocked"},
    )


class GeofenceMiddleware(BaseHTTPMiddleware):
    """Cloudflare/nginx 다음 단계의 application-level KR-only fallback.

    운영 기본 판정은 Cloudflare `CF-IPCountry` header다. nginx GeoIP2는 선택 계층이고,
    FastAPI는 header 기반 fallback과 health/admin 우회를 담당한다.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not settings.tripmate_geofence_enabled:
            return await call_next(request)

        if _is_bypass_path(request.url.path):
            return await call_next(request)

        allowed_countries = _normalized_set(settings.tripmate_geofence_allowed_countries)
        country = _detected_country(request)

        if country is None and not settings.tripmate_geofence_block_unknown:
            return await call_next(request)

        if country in allowed_countries:
            return await call_next(request)

        if (await _current_user_roles(request)).intersection(ADMIN_ROLES):
            return await call_next(request)

        return _blocked_response(country)
