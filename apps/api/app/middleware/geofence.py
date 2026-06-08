"""ADR-018 한국 전용 geofencing FastAPI fallback."""

from __future__ import annotations

import hmac
import inspect
import ipaddress
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
IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


class GeofenceConfigError(RuntimeError):
    """Geofence strict mode가 운영자를 조용한 전체 차단 상태로 몰지 않게 막는다."""


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
    if country and _is_trusted_country_proxy(request):
        return country.strip().upper()
    return None


def _trusted_proxy_networks() -> list[IpNetwork]:
    networks: list[IpNetwork] = []
    for raw in settings.tripmate_geofence_trusted_proxy_cidrs:
        value = raw.strip()
        if value:
            try:
                networks.append(ipaddress.ip_network(value, strict=False))
            except ValueError as exc:
                raise GeofenceConfigError(
                    "TRIPMATE_GEOFENCE_TRUSTED_PROXY_CIDRS contains an invalid CIDR."
                ) from exc
    return networks


def _client_ip(request: Request) -> IpAddress | None:
    if request.client is None:
        return None
    try:
        return ipaddress.ip_address(request.client.host)
    except ValueError:
        return None


def _source_ip_is_trusted(request: Request, networks: list[IpNetwork]) -> bool:
    if not networks:
        return True
    client_ip = _client_ip(request)
    if client_ip is None:
        return False
    return any(client_ip in network for network in networks)


def _shared_secret_is_trusted(request: Request, expected: str) -> bool:
    if not expected:
        return True
    header = settings.tripmate_geofence_trusted_proxy_header
    provided = request.headers.get(header, "")
    return hmac.compare_digest(provided, expected)


def _mtls_header_is_trusted(request: Request, header: str, expected: str) -> bool:
    if not header:
        return True
    if not expected:
        return False
    provided = request.headers.get(header, "")
    return hmac.compare_digest(provided, expected)


def _configured_trust_factor_names() -> set[str]:
    names: set[str] = set()
    if settings.tripmate_geofence_trusted_proxy_secret.strip():
        names.add("shared_secret")
    if _trusted_proxy_networks():
        names.add("proxy_cidr")
    if settings.tripmate_geofence_mtls_verified_header.strip():
        names.add("mtls")
    return names


def validate_geofence_configuration() -> list[str]:
    """Geofence startup guard.

    반환값은 startup log에 남길 경고다. secret/header 원문은 절대 포함하지 않는다.
    """
    if not settings.tripmate_geofence_enabled:
        return []

    warnings: list[str] = []
    factors = _configured_trust_factor_names()
    if settings.tripmate_geofence_block_unknown and not factors:
        raise GeofenceConfigError(
            "TRIPMATE_GEOFENCE_BLOCK_UNKNOWN=true requires at least one trusted "
            "country-header source: TRIPMATE_GEOFENCE_TRUSTED_PROXY_SECRET, "
            "TRIPMATE_GEOFENCE_TRUSTED_PROXY_CIDRS, or "
            "TRIPMATE_GEOFENCE_MTLS_VERIFIED_HEADER."
        )

    mtls_header = settings.tripmate_geofence_mtls_verified_header.strip()
    if mtls_header and not settings.tripmate_geofence_mtls_verified_value.strip():
        raise GeofenceConfigError(
            "TRIPMATE_GEOFENCE_MTLS_VERIFIED_VALUE must be non-empty when "
            "TRIPMATE_GEOFENCE_MTLS_VERIFIED_HEADER is set."
        )

    if settings.tripmate_geofence_block_unknown and len(factors) == 1:
        warnings.append(
            "geofence strict mode has only one trusted country-header factor; "
            "configure proxy CIDR allowlist or mTLS verification for defense in depth."
        )
    return warnings


def _is_trusted_country_proxy(request: Request) -> bool:
    expected = settings.tripmate_geofence_trusted_proxy_secret.strip()
    networks = _trusted_proxy_networks()
    mtls_header = settings.tripmate_geofence_mtls_verified_header.strip()
    mtls_value = settings.tripmate_geofence_mtls_verified_value.strip()
    if not (expected or networks or mtls_header):
        return False

    return (
        _shared_secret_is_trusted(request, expected)
        and _source_ip_is_trusted(request, networks)
        and _mtls_header_is_trusted(request, mtls_header, mtls_value)
    )


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

    운영 기본 판정은 Cloudflare `CF-IPCountry` header다. strict fallback에서는
    shared secret proxy header가 맞을 때만 country header를 신뢰한다.
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
