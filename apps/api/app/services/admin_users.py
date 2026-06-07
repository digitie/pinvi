"""Admin 사용자 관리 — force-verify / disable / resend-verify."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.models.audit import AdminAuditLog
from app.models.session import UserSession
from app.models.user import User


class AdminUserError(Exception):
    code: str = "INTERNAL_ERROR"


class AdminUserNotFoundError(AdminUserError):
    code = "RESOURCE_NOT_FOUND"


async def force_verify(
    db: AsyncSession, *, user_id: uuid.UUID, actor_id: uuid.UUID
) -> tuple[User, dict[str, str | None]]:
    """email_verified_at 강제 설정 (디버그)."""
    user = await db.scalar(select(User).where(User.user_id == user_id))
    if user is None or actor_id == user_id:
        raise AdminUserNotFoundError("Not found.")
    before_state = {
        "status": user.status,
        "email_verified_at": user.email_verified_at.isoformat() if user.email_verified_at else None,
    }
    user.email_verified_at = datetime.now(UTC)
    if user.status == "pending_verification":
        user.status = "pending_profile"
    return user, before_state


async def disable_user(
    db: AsyncSession, *, user_id: uuid.UUID, actor_id: uuid.UUID
) -> tuple[User, dict[str, str | bool]]:
    user = await db.scalar(select(User).where(User.user_id == user_id))
    if user is None or actor_id == user_id:
        raise AdminUserNotFoundError("Not found.")
    before_state: dict[str, str | bool] = {
        "status": user.status,
        "is_active": user.is_active,
    }
    user.status = "disabled"
    user.is_active = False
    # 모든 active 세션 폐기
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    return user, before_state


async def list_users(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 50,
    status_filter: str | None = None,
    q: str | None = None,
) -> tuple[list[User], int]:
    filters: list[ColumnElement[bool]] = [User.deleted_at.is_(None)]
    if status_filter:
        filters.append(User.status == status_filter)
    q_value = q.strip() if q else ""
    if q_value:
        pattern = f"%{q_value}%"
        search_filters: list[ColumnElement[bool]] = [
            User.email.ilike(pattern),
            User.nickname.ilike(pattern),
        ]
        try:
            search_filters.append(User.user_id == uuid.UUID(q_value))
        except ValueError:
            pass
        filters.append(or_(*search_filters))

    base = select(User).where(*filters)
    count_base = select(func.count(User.user_id)).where(*filters)
    total = await db.scalar(count_base) or 0
    offset = max(0, (page - 1) * limit)
    paged_q = base.order_by(User.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(paged_q)
    users = list(result.scalars())
    return users, total


async def list_recent_user_audit(
    db: AsyncSession, *, user_id: uuid.UUID, limit: int = 10
) -> list[AdminAuditLog]:
    result = await db.execute(
        select(AdminAuditLog)
        .where(
            AdminAuditLog.resource_type == "user",
            AdminAuditLog.resource_id == str(user_id),
        )
        .order_by(AdminAuditLog.log_id.desc())
        .limit(limit)
    )
    return list(result.scalars())


def mask_email(email: str) -> str:
    """`docs/api/admin.md` §6.4 PII 마스킹."""
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        return f"{local}***@{domain}"
    return f"{local[0]}***@{domain}"
