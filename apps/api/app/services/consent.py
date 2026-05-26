"""User consent — 4 분리 동의 + 철회 부작용. `docs/api/users.md` §3."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_consent import UserConsent
from app.schemas.consent import ConsentItem


class ConsentError(Exception):
    code: str = "INTERNAL_ERROR"


class ConsentNotFoundError(ConsentError):
    code = "RESOURCE_NOT_FOUND"


async def record_consents(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    consents: list[ConsentItem],
) -> list[UserConsent]:
    """주어진 동의 항목을 추가. 동일 (user, type, version)이면 idempotent."""
    now = datetime.now(UTC)
    rows: list[UserConsent] = []
    for item in consents:
        existing = await db.scalar(
            select(UserConsent).where(
                UserConsent.user_id == user_id,
                UserConsent.consent_type == item.consent_type,
                UserConsent.version == item.version,
            )
        )
        if existing is not None:
            existing.withdrawn_at = None
            existing.agreed_at = now
            rows.append(existing)
            continue
        row = UserConsent(
            user_id=user_id,
            consent_type=item.consent_type,
            version=item.version,
            agreed_at=now,
        )
        db.add(row)
        rows.append(row)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return rows


async def list_user_consents(
    db: AsyncSession, *, user_id: uuid.UUID
) -> list[UserConsent]:
    result = await db.execute(
        select(UserConsent).where(UserConsent.user_id == user_id).order_by(UserConsent.agreed_at)
    )
    return list(result.scalars())


async def withdraw_consent(
    db: AsyncSession, *, user_id: uuid.UUID, consent_type: str
) -> list[UserConsent]:
    """동의 철회 + 부작용 (demographic 컬럼 NULL 등)."""
    result = await db.execute(
        select(UserConsent).where(
            UserConsent.user_id == user_id,
            UserConsent.consent_type == consent_type,
            UserConsent.withdrawn_at.is_(None),
        )
    )
    rows = list(result.scalars())
    if not rows:
        raise ConsentNotFoundError(f"동의 항목이 없습니다: {consent_type}")
    now = datetime.now(UTC)
    for row in rows:
        row.withdrawn_at = now

    if consent_type == "demographic_use":
        user = await db.scalar(select(User).where(User.user_id == user_id))
        if user is not None:
            user.gender = None
            user.birth_year_month = None
            user.residence_sigungu_code = None

    await db.commit()
    return rows
