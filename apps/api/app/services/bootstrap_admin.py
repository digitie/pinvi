"""운영/개발 첫 진입용 bootstrap admin 보장.

`PINVI_BOOTSTRAP_ADMIN_PASSWORD`가 설정된 환경에서만 동작한다. 비밀번호 원문은
로그/DB에 남기지 않고 Argon2id hash만 저장한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.core.time import utc_now
from app.db import session as db_session
from app.models.user import User
from app.services.auth_session import revoke_active_user_sessions

BootstrapAdminAction = Literal["skipped", "created", "updated", "unchanged"]

log = get_logger("bootstrap-admin")


@dataclass(frozen=True)
class BootstrapAdminResult:
    action: BootstrapAdminAction
    email: str
    password_configured: bool


def _roles_with_admin(roles: list[str] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for role in [*(roles or []), "user", "admin"]:
        if role not in seen:
            seen.add(role)
            result.append(role)
    return result


async def ensure_bootstrap_admin() -> BootstrapAdminResult:
    """Create or repair the configured bootstrap admin account.

    Empty `PINVI_BOOTSTRAP_ADMIN_PASSWORD` intentionally disables the flow so production
    cannot accidentally inherit an insecure default. When the password is configured,
    the account is kept active, verified, and admin-capable; if the configured password
    differs from the stored hash, active sessions for that user are revoked.
    """

    email = settings.pinvi_bootstrap_admin_email.strip()
    password = settings.pinvi_bootstrap_admin_password
    if not email or not password:
        log.info(
            "pinvi.bootstrap_admin.skip",
            email_configured=bool(email),
            password_configured=bool(password),
        )
        return BootstrapAdminResult(
            action="skipped",
            email=email,
            password_configured=bool(password),
        )

    now = utc_now()
    # 모듈 속성으로 동적 참조한다. 통합 테스트가 `db_session.async_session_factory`를
    # 함수 스코프 엔진으로 monkeypatch하므로, 값을 직접 import하면 기본 localhost
    # factory를 잡아 테스트 격리가 깨진다.
    async with db_session.async_session_factory() as db:
        user = await db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(password),
                nickname="Pinvi Admin",
                status="active",
                roles=["user", "admin"],
                email_verified_at=now,
                email_status="active",
                is_active=True,
                deleted_at=None,
            )
            db.add(user)
            await db.commit()
            log.warning("pinvi.bootstrap_admin.created", email=email)
            return BootstrapAdminResult(
                action="created",
                email=email,
                password_configured=True,
            )

        changed = False
        password_changed = False

        if not user.password_hash or not verify_password(password, user.password_hash):
            user.password_hash = hash_password(password)
            user.access_token_version = (user.access_token_version or 0) + 1
            changed = True
            password_changed = True

        roles = _roles_with_admin(user.roles)
        if roles != list(user.roles or []):
            user.roles = roles
            changed = True

        if user.nickname is None:
            user.nickname = "Pinvi Admin"
            changed = True
        if user.status != "active":
            user.status = "active"
            changed = True
        if user.email_verified_at is None:
            user.email_verified_at = now
            changed = True
        if user.email_status != "active":
            user.email_status = "active"
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True
        if user.deleted_at is not None:
            user.deleted_at = None
            changed = True

        if password_changed:
            await revoke_active_user_sessions(db, user_id=user.user_id, revoked_at=now)

        if changed:
            await db.commit()
            log.warning(
                "pinvi.bootstrap_admin.updated",
                email=email,
                password_rotated=password_changed,
            )
            return BootstrapAdminResult(
                action="updated",
                email=email,
                password_configured=True,
            )

        await db.rollback()
        log.info("pinvi.bootstrap_admin.unchanged", email=email)
        return BootstrapAdminResult(
            action="unchanged",
            email=email,
            password_configured=True,
        )
