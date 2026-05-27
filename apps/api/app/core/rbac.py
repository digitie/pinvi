"""RBAC dependency — `app.users.roles` 배열 검사.

`docs/api/admin.md` §1 / SPEC V8 M-14.
권한 없으면 `404 RESOURCE_NOT_FOUND` (존재 자체 숨김).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUserId, DbSession
from app.models.user import User

Role = Literal["user", "admin", "operator", "cpo"]


def require_role(*allowed: Role) -> Callable[[CurrentUserId, DbSession], Awaitable[User]]:
    """`require_role("admin")` / `require_role("admin", "operator")` 등 사용."""

    async def dependency(current_user_id: CurrentUserId, db: DbSession) -> User:
        user = await db.scalar(select(User).where(User.user_id == uuid.UUID(current_user_id)))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "Not found."},
            )
        roles = set(user.roles or [])
        if not roles.intersection(allowed):
            # SPEC V8 M-4: 권한 없으면 존재 자체 숨김 (404)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "Not found."},
            )
        return user

    return dependency
