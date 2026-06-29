"""HTTP security headers for API responses."""

from __future__ import annotations

from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings

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
        response = await call_next(request)
        apply_security_headers(
            response,
            path=request.url.path,
            secure_transport=_is_secure_request(request),
        )
        return response


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
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    return request.url.scheme == "https" or forwarded_proto == "https"
