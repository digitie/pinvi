"""ADR-018 한국 전용 geofencing FastAPI fallback."""

from __future__ import annotations

from collections.abc import Iterable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.security import InvalidTokenError, decode_access_token

ADMIN_ROLES = {"admin", "operator", "cpo"}


def _normalized_set(values: Iterable[str]) -> set[str]:
    return {value.strip().upper() for value in values if value.strip()}


def _token_roles(request: Request) -> set[str]:
    token = request.cookies.get("tripmate_access")
    if not token:
        return set()
    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        return set()
    roles = payload.get("roles")
    if not isinstance(roles, list):
        return set()
    return {role for role in roles if isinstance(role, str)}


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

    운영 기본 판정은 Cloudflare `CF-IPCountry` header다. GeoIP DB lookup은 nginx 2차
    안전망이 맡고, FastAPI는 header 기반 fallback과 health/admin 우회를 담당한다.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not settings.tripmate_geofence_enabled:
            return await call_next(request)

        if _is_bypass_path(request.url.path):
            return await call_next(request)

        if _token_roles(request).intersection(ADMIN_ROLES):
            return await call_next(request)

        allowed_countries = _normalized_set(settings.tripmate_geofence_allowed_countries)
        country = _detected_country(request)

        if country is None and not settings.tripmate_geofence_block_unknown:
            return await call_next(request)

        if country not in allowed_countries:
            return _blocked_response(country)

        return await call_next(request)
