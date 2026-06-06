"""표준 API 에러 응답.

`docs/api/common.md` §2.2.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def build_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return body


async def http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=build_error("INTERNAL_ERROR", "서버 오류가 발생했습니다."),
        )
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        body = {"error": detail}
    else:
        body = build_error(
            code=_default_code_for_status(exc.status_code),
            message=str(detail),
        )
    return JSONResponse(status_code=exc.status_code, content=body)


async def validation_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=build_error("INTERNAL_ERROR", "서버 오류가 발생했습니다."),
        )
    details: dict[str, Any] = {"errors": _json_safe(exc.errors())}
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=build_error("VALIDATION_ERROR", "요청이 올바르지 않습니다.", details),
    )


def _default_code_for_status(http_status: int) -> str:
    return {
        400: "VALIDATION_ERROR",
        401: "TOKEN_INVALID",
        403: "PERMISSION_DENIED",
        404: "RESOURCE_NOT_FOUND",
        409: "VERSION_CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        503: "SERVICE_UNAVAILABLE",
    }.get(http_status, "INTERNAL_ERROR")
