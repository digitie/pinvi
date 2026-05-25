"""FastAPI 의존성 — DB session / 현재 사용자 / RBAC.

Sprint 1 시점에는 DB session + 현재 사용자만. Admin / location_audit는 Sprint 2~3에서.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import async_session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user_id(
    tripmate_access: Annotated[str | None, Cookie(alias="tripmate_access")] = None,
) -> str:
    """cookie에서 access JWT 추출 + `sub` 클레임 반환.

    DB 조회는 호출자가 직접 (필요 시) — 본 함수는 토큰 유효성만.
    """
    if not tripmate_access:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": "인증 cookie가 없습니다."},
        )
    try:
        payload = decode_access_token(tripmate_access)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": str(exc)},
        ) from exc
    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": "토큰 sub 클레임이 잘못되었습니다."},
        )
    return subject


CurrentUserId = Annotated[str, Depends(get_current_user_id)]
