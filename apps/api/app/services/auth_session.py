"""사용자 refresh session 발급/회전/폐기."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    generate_opaque_token,
)
from app.core.time import utc_now
from app.models.session import UserSession
from app.models.user import User


class AuthSessionError(Exception):
    code: str = "TOKEN_INVALID"


class RefreshTokenExpiredError(AuthSessionError):
    code = "TOKEN_EXPIRED"


class RefreshTokenInvalidError(AuthSessionError):
    code = "TOKEN_INVALID"


@dataclass(frozen=True)
class IssuedAuthSession:
    access_token: str
    refresh_token: str
    expires_at: datetime


@dataclass(frozen=True)
class RefreshedAuthSession:
    user: User
    issue: IssuedAuthSession


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _truncate_user_agent(user_agent: str | None) -> str | None:
    if not user_agent:
        return None
    return user_agent[:512]


def _issue_tokens(*, user: User) -> IssuedAuthSession:
    refresh_token = generate_opaque_token(32)
    return IssuedAuthSession(
        access_token=create_access_token(
            subject=str(user.user_id),
            extra={"token_version": user.access_token_version or 0},
        ),
        refresh_token=refresh_token,
        expires_at=utc_now() + timedelta(days=settings.pinvi_refresh_token_days),
    )


async def issue_user_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> IssuedAuthSession:
    user = await db.scalar(
        select(User).where(
            User.user_id == user_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
    )
    if user is None or user.status in {"disabled", "pending_delete", "deleted"}:
        raise RefreshTokenInvalidError("세션 사용자를 찾을 수 없습니다.")

    issue = _issue_tokens(user=user)
    db.add(
        UserSession(
            user_id=user_id,
            session_token_hash=hash_session_token(issue.refresh_token),
            expires_at=issue.expires_at,
            user_agent=_truncate_user_agent(user_agent),
            ip_address=ip_address,
        )
    )
    await db.commit()
    return issue


async def refresh_user_session(
    db: AsyncSession,
    *,
    refresh_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> RefreshedAuthSession:
    now = utc_now()
    session = await db.scalar(
        select(UserSession)
        .where(UserSession.session_token_hash == hash_session_token(refresh_token))
        .with_for_update()
    )
    if session is None:
        raise RefreshTokenInvalidError("refresh token을 찾을 수 없습니다.")
    if session.revoked_at is not None:
        raise RefreshTokenExpiredError("refresh token이 폐기되었습니다.")
    if session.expires_at <= now:
        session.revoked_at = now
        await db.commit()
        raise RefreshTokenExpiredError("refresh token이 만료되었습니다.")

    user = await db.scalar(
        select(User).where(
            User.user_id == session.user_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
    )
    if user is None or user.status in {"disabled", "pending_delete", "deleted"}:
        session.revoked_at = now
        await db.commit()
        raise RefreshTokenInvalidError("세션 사용자를 찾을 수 없습니다.")

    session.revoked_at = now
    issue = _issue_tokens(user=user)
    db.add(
        UserSession(
            user_id=user.user_id,
            session_token_hash=hash_session_token(issue.refresh_token),
            expires_at=issue.expires_at,
            user_agent=_truncate_user_agent(user_agent),
            ip_address=ip_address,
        )
    )
    await db.commit()
    return RefreshedAuthSession(user=user, issue=issue)


async def revoke_active_user_sessions(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    revoked_at: datetime | None = None,
) -> None:
    now = revoked_at or utc_now()
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def _access_token_subject(access_token: str | None) -> uuid.UUID | None:
    """서명·만료가 유효한 access JWT의 사용자 id. 아니면 None(로그아웃은 예외를 던지지 않는다)."""
    if not access_token:
        return None
    try:
        payload = decode_access_token(access_token)
    except InvalidTokenError:
        return None
    if payload.get("typ") != "access" or not isinstance(payload.get("sub"), str):
        return None
    try:
        return uuid.UUID(payload["sub"])
    except ValueError:
        return None


async def revoke_user_session(
    db: AsyncSession,
    *,
    refresh_token: str | None,
    access_token: str | None = None,
) -> None:
    """로그아웃 — refresh session을 폐기하고 그 사용자의 access JWT도 무효로 만든다(#672).

    access JWT는 stateless라 refresh session 폐기만으로는 만료(기본 10분)까지 살아 있다 — 로그아웃
    응답의 cookie 삭제가 반영되기 전에 나간 요청이나 cookie 밖으로 복사된 토큰이 `/auth/me` 200을
    받았다. 그래서 `access_token_version`을 올린다(관리자 세션 폐기와 같은 장치). 같은 사용자의
    다른 기기 access JWT도 무효가 되지만 refresh session은 살아 있어 다음 요청에서 한 번 갱신된다.
    """
    user_ids: set[uuid.UUID] = set()
    if refresh_token:
        session_user_id = await db.scalar(
            update(UserSession)
            .where(
                UserSession.session_token_hash == hash_session_token(refresh_token),
                UserSession.revoked_at.is_(None),
            )
            .values(revoked_at=utc_now())
            .returning(UserSession.user_id)
        )
        if session_user_id is not None:
            user_ids.add(session_user_id)
    access_user_id = _access_token_subject(access_token)
    if access_user_id is not None:
        user_ids.add(access_user_id)
    if user_ids:
        await db.execute(
            update(User)
            .where(User.user_id.in_(user_ids))
            .values(access_token_version=func.coalesce(User.access_token_version, 0) + 1)
        )
    await db.commit()
