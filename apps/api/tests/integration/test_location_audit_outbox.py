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
            email=f"outbox_{uuid.uuid4().hex[:8]}@pinvi.test",
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


async def test_search_purpose_is_accepted_by_chain_contract(session_factory) -> None:  # type: ignore[no-untyped-def]
    """`/search` 제3자 제공 purpose가 **체인 테이블까지** 적재된다 (T-328).

    기존 테스트는 outbox만 확인해서, DB CHECK 제약이 `third_party_place_search`를 거부해도
    green이었다. 감사 의무를 지키는 것은 outbox가 아니라 `location_access_log`다.
    """
    user_id = await _make_user(session_factory)
    async with session_factory() as db:
        await enqueue_location_audit_outbox(
            db,
            user_id=user_id,
            endpoint="/search",
            purpose="third_party_place_search",
            lat=Decimal("37.5665"),
            lng=Decimal("126.9780"),
            request_id=uuid.uuid4(),
            ip_hash="cd" * 32,
        )
    async with session_factory() as db:
        assert await drain_location_audit_outbox(db) == 1
    async with session_factory() as db:
        purposes = list(
            (await db.execute(select(LocationAccessLog.purpose))).scalars()
        )
    assert purposes == ["third_party_place_search"]


async def test_one_bad_row_does_not_block_the_queue(session_factory) -> None:  # type: ignore[no-untyped-def]
    """계약을 벗어난 행 하나가 큐 전체를 막지 않는다 (T-328).

    drain이 배치를 단일 트랜잭션으로 커밋하던 때는 CHECK 위반 1건이 배치 전체를 abort시키고,
    같은 head 행을 무한 재시도하며 이후 모든 감사 기록이 멈췄다.
    """
    user_id = await _make_user(session_factory)
    async with session_factory() as db:
        # 허용 목록에 없는 purpose — outbox에는 CHECK가 없어 enqueue는 성공한다.
        await enqueue_location_audit_outbox(
            db,
            user_id=user_id,
            endpoint="/unknown",
            purpose="not_a_contracted_purpose",
            lat=Decimal("37.0"),
            lng=Decimal("127.0"),
            request_id=uuid.uuid4(),
            ip_hash="ef" * 32,
        )
    await _enqueue(session_factory, user_id, 1)

    async with session_factory() as db:
        processed = await drain_location_audit_outbox(db)
    # 뒤 행은 정상 처리되고, 실패 행만 미처리로 남는다.
    assert processed == 1
    async with session_factory() as db:
        logs = list((await db.execute(select(LocationAccessLog.purpose))).scalars())
        pending = list(
            (
                await db.execute(
                    select(LocationAuditOutbox.purpose).where(
                        LocationAuditOutbox.processed_at.is_(None)
                    )
                )
            ).scalars()
        )
    assert logs == ["nearby_attractions"]
    assert pending == ["not_a_contracted_purpose"]
