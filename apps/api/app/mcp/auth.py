"""MCP Bearer token dependency."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from app.core.config import settings
from app.core.deps import DbSession
from app.models.api_call_log import ApiCallLog
from app.models.mcp_token import McpToken
from app.services.hash_chain import sha256_hex
from app.services.mcp_tokens import (
    McpPrincipal,
    McpTokenError,
    McpTokenPermissionError,
    authenticate_mcp_token,
)

_CALLS: dict[str, deque[float]] = defaultdict(deque)


async def require_mcp_read(
    request: Request,
    db: DbSession,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> McpPrincipal:
    raw = _bearer_token(authorization)
    try:
        principal = await authenticate_mcp_token(db, raw_token=raw)
    except McpTokenPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except McpTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    _enforce_rate_limit(principal)
    endpoint = request.url.path
    if request.url.query:
        endpoint = f"{endpoint}?{request.url.query}"
    token_row = await db.get(McpToken, principal.token_id)
    if token_row is not None:
        token_row.last_used_at = datetime.now(UTC)
        token_row.last_used_ip_hash = sha256_hex(request.client.host if request.client else "")
    db.add(
        ApiCallLog(
            provider="mcp",
            endpoint=endpoint,
            status_code=200,
            request_id=getattr(request.state, "request_id", None),
        )
    )
    await db.commit()
    return principal


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": "Authorization 헤더가 필요합니다."},
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": "Bearer 토큰 형식이 아닙니다."},
        )
    return token


def _enforce_rate_limit(principal: McpPrincipal) -> None:
    now = time.monotonic()
    key = str(principal.user_id)
    window = _CALLS[key]
    while window and now - window[0] >= 60:
        window.popleft()
    limit = max(1, settings.pinvi_mcp_rate_limit_per_minute)
    if len(window) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMITED",
                "message": "MCP 호출 한도를 초과했습니다.",
            },
            headers={"Retry-After": "60"},
        )
    window.append(now)
