"""FastAPI 의존성 — DB session / 현재 사용자 / RBAC.

Sprint 1 시점에는 DB session + 현재 사용자만. Admin / location_audit는 Sprint 2~3에서.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import InvalidTokenError, decode_access_token
from app.db import session as db_session
from app.models.user import User


async def get_db() -> AsyncIterator[AsyncSession]:
    # 모듈 속성으로 동적 참조 — 통합 테스트가 `db_session.async_session_factory` 를
    # 함수 스코프 엔진으로 monkeypatch 한다. `from ... import async_session_factory`
    # 로 이름을 박으면 import 순서(테스트 모듈이 app 을 top-level import 하는 경우)에
    # 따라 패치 이전의 기본(localhost) 팩토리를 잡아 "relation app.users does not
    # exist" 가 난다.
    async with db_session.async_session_factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user_id(
    request: Request,
    db: DbSession,
    pinvi_access: Annotated[str | None, Cookie(alias="pinvi_access")] = None,
) -> str:
    """cookie에서 access JWT 추출 + 사용자 상태와 token version 검증."""
    if not pinvi_access:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": "인증 cookie가 없습니다."},
        )
    try:
        payload = decode_access_token(pinvi_access)
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
    try:
        user_id = uuid.UUID(subject)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": "토큰 sub 클레임이 잘못되었습니다."},
        ) from exc

    user = await db.scalar(
        select(User).where(
            User.user_id == user_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
    )
    if user is None or user.status in {"disabled", "deleted"}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": "사용자를 찾을 수 없습니다."},
        )

    current_version = user.access_token_version or 0
    token_version = payload.get("token_version")
    if token_version is None:
        if current_version != 0:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "TOKEN_INVALID", "message": "토큰 버전이 만료되었습니다."},
            )
    elif (
        not isinstance(token_version, int)
        or isinstance(token_version, bool)
        or token_version != current_version
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": "토큰 버전이 만료되었습니다."},
        )

    request.state.user_id = str(user.user_id)
    return str(user.user_id)


CurrentUserId = Annotated[str, Depends(get_current_user_id)]
