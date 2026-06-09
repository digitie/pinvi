"""위치 감사 async outbox + drain (T-146 / D-20) 통합 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.audit import LocationAccessLog, LocationAuditOutbox
from app.services.hash_chain import GENESIS_HASH
from app.services.location_audit import (
    drain_location_audit_outbox,
    enqueue_location_audit_outbox,
)

pytestmark = pytest.mark.asyncio


async def _make_user(session_factory) -> uuid.UUID:  # type: ignore[no-untyped-def]
    from app.models.user import User

    async with session_factory() as db:
        user = User(
            email=f"outbox_{uuid.uuid4().hex[:8]}@tripmate.test",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def _enqueue(session_factory, user_id: uuid.UUID, n: int) -> None:  # type: ignore[no-untyped-def]
    for _ in range(n):
        async with session_factory() as db:
            await enqueue_location_audit_outbox(
                db,
                user_id=user_id,
                endpoint="/features/nearby",
                purpose="nearby_attractions",
                lat=Decimal("37.5665"),
                lng=Decimal("126.9780"),
                request_id=uuid.uuid4(),
                ip_hash="ab" * 32,
            )


async def test_enqueue_then_drain_builds_chain(session_factory) -> None:  # type: ignore[no-untyped-def]
    user_id = await _make_user(session_factory)
    await _enqueue(session_factory, user_id, 3)

    # 적재 직후: outbox 3건 pending, location_access_log 0 (요청 경로에서 체인 미계산).
    async with session_factory() as db:
        pending = await db.scalar(
            select(func.count(LocationAuditOutbox.outbox_id)).where(
                LocationAuditOutbox.processed_at.is_(None)
            )
        )
        logs = await db.scalar(select(func.count(LocationAccessLog.log_id)))
    assert pending == 3
    assert logs == 0

    # drain → 체인 3건 + outbox 모두 processed.
    async with session_factory() as db:
        processed = await drain_location_audit_outbox(db, batch_size=200)
    assert processed == 3

    async with session_factory() as db:
        rows = list(
            (
                await db.execute(select(LocationAccessLog).order_by(LocationAccessLog.log_id))
            ).scalars()
        )
        still_pending = await db.scalar(
            select(func.count(LocationAuditOutbox.outbox_id)).where(
                LocationAuditOutbox.processed_at.is_(None)
            )
        )
    assert len(rows) == 3
    assert rows[0].prev_hash == GENESIS_HASH
    assert rows[1].prev_hash == rows[0].content_hash
    assert rows[2].prev_hash == rows[1].content_hash
    assert len({r.content_hash for r in rows}) == 3
    assert still_pending == 0


async def test_drain_empty_and_idempotent(session_factory) -> None:  # type: ignore[no-untyped-def]
    user_id = await _make_user(session_factory)
    await _enqueue(session_factory, user_id, 1)

    async with session_factory() as db:
        assert await drain_location_audit_outbox(db) == 1
    # 두 번째 drain은 처리할 게 없으므로 0 (이미 처리된 outbox 재처리 안 함).
    async with session_factory() as db:
        assert await drain_location_audit_outbox(db) == 0
    async with session_factory() as db:
        assert await db.scalar(select(func.count(LocationAccessLog.log_id))) == 1
