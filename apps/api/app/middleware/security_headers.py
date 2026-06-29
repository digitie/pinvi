"""HTTP security headers for API responses."""

from __future__ import annotations

from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.errors import build_error

API_CONTENT_SECURITY_POLICY: Final[str] = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
)
STRICT_TRANSPORT_SECURITY: Final[str] = "max-age=31536000; includeSubDomains"
SECURITY_HEADERS: Final[dict[str, str]] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(self)",
    "X-Frame-Options": "DENY",
}
CSP_BYPASS_PATHS: Final[set[str]] = {"/docs", "/redoc", "/openapi.json"}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            response = await call_next(request)
        except Exception:
            # An unhandled exception escapes every inner middleware/handler and is
            # otherwise emitted by Starlette's outermost ServerErrorMiddleware with
            # *no* security headers (scanners flag missing nosniff on 500s, #343).
            # Build the fallback 500 here so the baseline headers are still applied.
            response = _fallback_server_error_response()
        apply_security_headers(
            response,
            path=request.url.path,
            secure_transport=_is_secure_request(request),
        )
        return response


def _fallback_server_error_response() -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=build_error("INTERNAL_ERROR", "서버 오류가 발생했습니다."),
    )


def apply_security_headers(
    response: Response,
    *,
    path: str,
    secure_transport: bool = False,
) -> None:
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)

    if _should_apply_csp(path):
        response.headers.setdefault("Content-Security-Policy", API_CONTENT_SECURITY_POLICY)

    if secure_transport or settings.pinvi_environment == "production":
        response.headers.setdefault("Strict-Transport-Security", STRICT_TRANSPORT_SECURITY)


def _should_apply_csp(path: str) -> bool:
    if path in CSP_BYPASS_PATHS:
        return False
    return not (path.startswith("/docs/") or path.startswith("/redoc/"))


def _is_secure_request(request: Request) -> bool:
    # Deliberately does NOT trust ``X-Forwarded-Proto``: any client can set that
    # header, which would let an attacker force an ``Strict-Transport-Security``
    # response over plain HTTP (#344). HSTS is instead gated on the genuine
    # request scheme here plus ``pinvi_environment == "production"`` in
    # ``apply_security_headers``.
    return request.url.scheme == "https"
