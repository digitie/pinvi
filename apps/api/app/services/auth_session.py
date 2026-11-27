"""사용자 refresh session 발급/회전/폐기.

세션 수명(`docs/api/auth.md` §3.5 "로그인 유지"):

- access JWT는 늘 `pinvi_access_token_minutes`(기본 10분)다. 로그인 유지는 access 수명을 바꾸지 않는다.
- 로그인 1회가 refresh 회전 계열(`family_id`) 하나를 만든다. 계열의 절대 만료는 로그인 +
  `pinvi_remember_me_days`(기본 365일)이고 회전은 이 시각을 넘겨 연장하지 않는다.
- 유지하지 않은 계열: 회전마다 `pinvi_refresh_token_days`(기본 7일) 미끄럼 만료(절대 만료로 자른다).
- 유지한 계열(`remember_me`): refresh 만료 = 절대 만료. 7일 동안 안 써도 끊기지 않는다.
- 운영 권한 역할(admin/operator/cpo)은 로그인 유지를 받지 않는다(`PRIVILEGED_ROLES`).
- 회전된 토큰이 유예(`REFRESH_REUSE_GRACE`) 뒤 다시 오면 탈취로 보고 계열 전체를 폐기한다.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.rbac import PRIVILEGED_ROLES
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    generate_opaque_token,
)
from app.core.time import utc_now
from app.models.session import UserSession
from app.models.user import User

log = get_logger("auth_session")

# 같은 refresh token의 거의 동시 재사용(탭 두 개가 함께 갱신, 응답 유실 뒤 재시도)은 공격이 아니다 — 이 유예
# 안의 재사용은 지금처럼 401만 돌려주고, 유예가 지난 재사용만 계열 전체를 폐기한다.
REFRESH_REUSE_GRACE = timedelta(seconds=60)


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
    # refresh session(=`pinvi_refresh` cookie)의 만료. cookie Max-Age는 이 시각까지만 둔다.
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


def remember_me_allowed(roles: Iterable[str] | None) -> bool:
    """운영 권한 역할은 장기 세션을 받지 않는다(`docs/compliance/pipa.md` §6 Admin 세션)."""
    return not PRIVILEGED_ROLES.intersection(roles or ())


def _session_expires_at(
    *, now: datetime, remember_me: bool, absolute_expires_at: datetime
) -> datetime:
    if remember_me:
        return absolute_expires_at
    return min(now + timedelta(days=settings.pinvi_refresh_token_days), absolute_expires_at)


def _new_session_row(
    *,
    user: User,
    now: datetime,
    family_id: uuid.UUID,
    remember_me: bool,
    absolute_expires_at: datetime,
    user_agent: str | None,
    ip_address: str | None,
) -> tuple[UserSession, IssuedAuthSession]:
    refresh_token = generate_opaque_token(32)
    expires_at = _session_expires_at(
        now=now, remember_me=remember_me, absolute_expires_at=absolute_expires_at
    )
    issue = IssuedAuthSession(
        access_token=create_access_token(
            subject=str(user.user_id),
            extra={"token_version": user.access_token_version or 0},
        ),
        refresh_token=refresh_token,
        expires_at=expires_at,
    )
    row = UserSession(
        user_id=user.user_id,
        session_token_hash=hash_session_token(refresh_token),
        family_id=family_id,
        remember_me=remember_me,
        absolute_expires_at=absolute_expires_at,
        expires_at=expires_at,
        user_agent=_truncate_user_agent(user_agent),
        ip_address=ip_address,
    )
    return row, issue


async def issue_user_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    user_agent: str | None = None,
    ip_address: str | None = None,
    remember_me: bool = False,
) -> IssuedAuthSession:
    """새 로그인 — 새 refresh 회전 계열을 연다. `remember_me`는 권한 역할이면 무시된다."""
    user = await db.scalar(
        select(User).where(
            User.user_id == user_id,
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
    )
    if user is None or user.status in {"disabled", "pending_delete", "deleted"}:
        raise RefreshTokenInvalidError("세션 사용자를 찾을 수 없습니다.")

    now = utc_now()
    granted = remember_me and remember_me_allowed(user.roles)
    family_id = uuid.uuid4()
    row, issue = _new_session_row(
        user=user,
        now=now,
        family_id=family_id,
        remember_me=granted,
        absolute_expires_at=now + timedelta(days=settings.pinvi_remember_me_days),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(row)
    await db.commit()
    log.info(
        "auth.session_issued",
        user_id=str(user.user_id),
        family_id=str(family_id),
        remember_me=granted,
        remember_me_requested=remember_me,
    )
    return issue


async def _revoke_family_after_reuse(
    db: AsyncSession, *, session: UserSession, now: datetime
) -> None:
    """회전된 토큰의 늦은 재사용 — 계열의 살아 있는 row를 모두 폐기하고 access JWT도 끊는다."""
    revoked = await db.execute(
        update(UserSession)
        .where(UserSession.family_id == session.family_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
        .returning(UserSession.session_id)
    )
    revoked_count = len(revoked.all())
    await db.execute(
        update(User)
        .where(User.user_id == session.user_id)
        .values(access_token_version=func.coalesce(User.access_token_version, 0) + 1)
    )
    await db.commit()
    log.warning(
        "auth.refresh_reuse_detected",
        user_id=str(session.user_id),
        family_id=str(session.family_id),
        session_id=str(session.session_id),
        remember_me=session.remember_me,
        revoked_sessions=revoked_count,
    )


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
        if session.rotated_at is not None and now - session.rotated_at > REFRESH_REUSE_GRACE:
            await _revoke_family_after_reuse(db, session=session, now=now)
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
    session.rotated_at = now
    row, issue = _new_session_row(
        user=user,
        now=now,
        family_id=session.family_id,
        # 계열이 열린 뒤 권한 역할을 받았으면(역할 부여는 세션을 폐기하지만 방어적으로) 유지를 떼어낸다.
        remember_me=session.remember_me and remember_me_allowed(user.roles),
        absolute_expires_at=session.absolute_expires_at,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(row)
    await db.commit()
    return RefreshedAuthSession(user=user, issue=issue)


async def session_remember_me(
    db: AsyncSession, *, user_id: uuid.UUID, refresh_token: str | None
) -> bool:
    """그 사용자의 살아 있는 refresh session이 "로그인 유지" 계열인지.

    계정 연결(OAuth link) callback이 새 세션을 발급할 때 지금 세션의 선택을 잇는 데 쓴다 — 클라이언트 값이
    아니라 서버에 있는 세션에서 읽는다.
    """
    if not refresh_token:
        return False
    remember_me = await db.scalar(
        select(UserSession.remember_me).where(
            UserSession.session_token_hash == hash_session_token(refresh_token),
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > utc_now(),
        )
    )
    return bool(remember_me)


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
