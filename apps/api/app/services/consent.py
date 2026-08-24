"""User consent — 4 분리 동의 + 철회 부작용. `docs/api/users.md` §3."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_consent import UserConsent
from app.models.user_consent_event import UserConsentEvent
from app.schemas.consent import ConsentItem

# 동의 이벤트를 남긴 화면. 현재 상태 테이블에는 없는 "어디서 받았는가"를 이력에만 담는다.
ConsentSource = Literal["register", "profile_complete", "settings", "backfill"]


class ConsentError(Exception):
    code: str = "INTERNAL_ERROR"


class ConsentNotFoundError(ConsentError):
    code = "RESOURCE_NOT_FOUND"


async def record_consents(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    consents: list[ConsentItem],
    source: ConsentSource = "settings",
) -> list[UserConsent]:
    """주어진 동의 항목을 추가. 동일 (user, type, version)이면 idempotent.

    현재 상태 row는 type+version당 하나이므로 재동의가 그 row를 되살린다. 그 과정에서 사라지는
    "언제 동의/철회했는가"는 `user_consent_events`에 append로 남긴다(T-326) — 같은 트랜잭션이라
    이벤트만 유실되는 경우가 없다.

    이미 유효한 동의는 **아무것도 바꾸지 않는다**. 예전에는 매 PUT마다 `agreed_at`을 현재 시각으로
    덮어써서, 실제로는 가입 때 받은 동의가 방금 받은 것처럼 보였다.
    """
    now = datetime.now(UTC)
    rows: list[UserConsent] = []
    for item in consents:
        # 같은 사용자의 동시 PUT이 둘 다 "철회됨"을 보고 각각 부활 이벤트를 남기지 않도록 잠근다.
        existing = await db.scalar(
            select(UserConsent)
            .where(
                UserConsent.user_id == user_id,
                UserConsent.consent_type == item.consent_type,
                UserConsent.version == item.version,
            )
            .with_for_update()
        )
        if existing is not None:
            if existing.withdrawn_at is None:
                # 이미 유효 — 재기록도 이벤트도 없다.
                rows.append(existing)
                continue
            # 철회했다가 다시 동의한 경우다. row는 되살아나지만 이력에는 두 사건이 모두 남는다.
            existing.withdrawn_at = None
            existing.agreed_at = now
            rows.append(existing)
        else:
            row = UserConsent(
                user_id=user_id,
                consent_type=item.consent_type,
                version=item.version,
                agreed_at=now,
            )
            db.add(row)
            rows.append(row)
        db.add(
            UserConsentEvent(
                user_id=user_id,
                consent_type=item.consent_type,
                version=item.version,
                event="agreed",
                source=source,
                occurred_at=now,
            )
        )
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return rows


async def has_valid_consents(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    consent_types: tuple[str, ...],
    accepted_versions: tuple[str, ...] | None = None,
) -> bool:
    """요구된 동의가 **전부** 유효한지. 서버측 게이트의 단일 읽기 지점이다.

    유효 = 철회되지 않았고(`withdrawn_at IS NULL`), 허용 버전 목록을 주면 그 안에 든 버전이다.
    판정을 여기 한 곳에 모아 두는 이유는, 저장 모델이 바뀌어도 게이트 호출부가 흔들리지 않게
    하기 위해서다(T-327이 이 함수만 호출한다).
    """
    if not consent_types:
        return True
    stmt = select(UserConsent.consent_type).where(
        UserConsent.user_id == user_id,
        UserConsent.consent_type.in_(consent_types),
        UserConsent.withdrawn_at.is_(None),
    )
    if accepted_versions is not None:
        stmt = stmt.where(UserConsent.version.in_(accepted_versions))
    found = {row for row in (await db.execute(stmt)).scalars()}
    return found.issuperset(consent_types)


async def list_user_consents(db: AsyncSession, *, user_id: uuid.UUID) -> list[UserConsent]:
    # 최신 동의가 먼저 오게 한다. 소비자(웹·모바일 설정 화면)가 type당 첫 행을 고르는데,
    # 버전 상수가 올라가 type당 2행이 되는 순간 오름차순은 **옛 행**을 표시한다.
    result = await db.execute(
        select(UserConsent)
        .where(UserConsent.user_id == user_id)
        .order_by(UserConsent.consent_type, UserConsent.agreed_at.desc())
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
        db.add(
            UserConsentEvent(
                user_id=user_id,
                consent_type=row.consent_type,
                version=row.version,
                event="withdrawn",
                source="settings",
                occurred_at=now,
            )
        )

    if consent_type == "demographic_use":
        user = await db.scalar(select(User).where(User.user_id == user_id))
        if user is not None:
            user.gender = None
            user.birth_year_month = None
            user.residence_sigungu_code = None

    await db.commit()
    return rows
