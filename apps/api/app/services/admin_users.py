"""Admin 사용자 관리 — force-verify / disable / resend-verify."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import UserSession
from app.models.user import User


class AdminUserError(Exception):
    code: str = "INTERNAL_ERROR"


class AdminUserNotFoundError(AdminUserError):
    code = "RESOURCE_NOT_FOUND"


async def force_verify(db: AsyncSession, *, user_id: uuid.UUID, actor_id: uuid.UUID) -> User:
    """email_verified_at 강제 설정 (디버그)."""
    user = await db.scalar(select(User).where(User.user_id == user_id))
    if user is None or actor_id == user_id:
        raise AdminUserNotFoundError("Not found.")
    user.email_verified_at = datetime.now(UTC)
    if user.status == "pending_verification":
        user.status = "pending_profile"
    await db.commit()
    await db.refresh(user)
    return user


async def disable_user(db: AsyncSession, *, user_id: uuid.UUID, actor_id: uuid.UUID) -> User:
    user = await db.scalar(select(User).where(User.user_id == user_id))
    if user is None or actor_id == user_id:
        raise AdminUserNotFoundError("Not found.")
    user.status = "disabled"
    user.is_active = False
    # 모든 active 세션 폐기
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()
    await db.refresh(user)
    return user


async def list_users(
    db: AsyncSession, *, page: int = 1, limit: int = 50, status_filter: str | None = None
) -> tuple[list[User], int]:
    base = select(User).where(User.deleted_at.is_(None))
    count_base = select(func.count(User.user_id)).where(User.deleted_at.is_(None))
    if status_filter:
        base = base.where(User.status == status_filter)
        count_base = count_base.where(User.status == status_filter)
    total = await db.scalar(count_base) or 0
    offset = max(0, (page - 1) * limit)
    paged_q = base.order_by(User.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(paged_q)
    users = list(result.scalars())
    return users, total


def mask_email(email: str) -> str:
    """`docs/api/admin.md` §6.4 PII 마스킹."""
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        return f"{local}***@{domain}"
    return f"{local[0]}***@{domain}"
