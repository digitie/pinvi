"""Admin 사용자 관리 — force-verify / disable / role grant/revoke."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

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


class AdminUserRoleTransitionError(AdminUserError):
    code = "INVALID_STATE"


class AdminUserPermissionError(AdminUserError):
    code = "PERMISSION_DENIED"


AdminRole = Literal["user", "admin", "operator", "cpo"]
MutableAdminRole = Literal["admin", "operator", "cpo"]
ROLE_ORDER: tuple[AdminRole, ...] = ("user", "admin", "operator", "cpo")


def normalize_roles(roles: list[str] | None) -> list[AdminRole]:
    """정해진 role vocabulary와 순서로 roles 배열을 정규화한다."""

    role_set = set(roles or [])
    role_set.add("user")
    return [role for role in ROLE_ORDER if role in role_set]


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


async def grant_user_role(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    actor_id: uuid.UUID,
    role: MutableAdminRole,
) -> tuple[User, dict[str, list[AdminRole]]]:
    user = await db.scalar(select(User).where(User.user_id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise AdminUserNotFoundError("Not found.")
    before_state = {"roles": normalize_roles(user.roles)}
    if role in before_state["roles"]:
        raise AdminUserRoleTransitionError(f"{role} role은 이미 부여되어 있습니다.")
    user.roles = [str(existing) for existing in normalize_roles([*before_state["roles"], role])]
    return user, before_state


async def revoke_user_role(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    actor_id: uuid.UUID,
    role: MutableAdminRole,
) -> tuple[User, dict[str, list[AdminRole]]]:
    user = await db.scalar(select(User).where(User.user_id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise AdminUserNotFoundError("Not found.")
    before_roles = normalize_roles(user.roles)
    before_state = {"roles": before_roles}
    if role not in before_roles:
        raise AdminUserRoleTransitionError(f"{role} role은 부여되어 있지 않습니다.")
    if role == "admin" and actor_id == user_id:
        raise AdminUserPermissionError("자기 자신의 admin role은 회수할 수 없습니다.")
    if role == "admin":
        other_admin_rows = await db.execute(
            select(User.roles).where(
                User.user_id != user_id,
                User.deleted_at.is_(None),
            )
        )
        other_admin_count = sum(
            1 for roles in other_admin_rows.scalars() if "admin" in normalize_roles(roles)
        )
        if other_admin_count < 1:
            raise AdminUserPermissionError("마지막 admin role은 회수할 수 없습니다.")
    user.roles = [
        str(existing)
        for existing in normalize_roles([existing for existing in before_roles if existing != role])
    ]
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
