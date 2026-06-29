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
        response = await call_next(request)
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


async def security_headers_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """500 handler that attaches baseline security headers to the error response.

    Registered on the app (ServerErrorMiddleware) rather than caught in the
    SecurityHeadersMiddleware: Starlette's ServerErrorMiddleware still re-raises
    ``exc`` after sending this response, so the traceback is logged by the server and
    tests asserting exception propagation keep working — while real clients still get a
    500 carrying X-Content-Type-Options/X-Frame-Options/CSP (#343, replaces the
    swallow-in-middleware approach that broke rollback tests).
    """
    del exc  # response is identical for any unhandled error; ServerErrorMiddleware re-raises
    response = _fallback_server_error_response()
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
    # Deliberately does NOT trust ``X-Forwarded-Proto``: any client can set that
    # header, which would let an attacker force an ``Strict-Transport-Security``
    # response over plain HTTP (#344). HSTS is instead gated on the genuine
    # request scheme here plus ``pinvi_environment == "production"`` in
    # ``apply_security_headers``.
    return request.url.scheme == "https"
