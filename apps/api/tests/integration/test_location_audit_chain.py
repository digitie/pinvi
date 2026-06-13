"""위치 감사 content_hash chain 통합 (SPRINT-2 DoD, ADR-012 / lbs-act §3.3).

HTTP 자동 적재(`/features/in-bounds`)는 kor_travel_map 라이브러리 client 주입(Sprint 4)에
의존하므로, 본 테스트는 미들웨어가 호출하는 `_append_log` chain 로직을 실제 DB 에
대해 검증한다 — prev_hash 링크 + content_hash 결정성 + 변조 탐지.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.middleware.location_audit import _append_log
from app.models.audit import LocationAccessLog
from app.services.hash_chain import GENESIS_HASH, compute_content_hash

pytestmark = pytest.mark.asyncio


async def _make_user(session_factory) -> uuid.UUID:
    from app.models.user import User

    async with session_factory() as db:
        u = User(
            email=f"loc_{uuid.uuid4().hex[:8]}@pinvi.test",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u.user_id


async def test_chain_links_prev_hash(session_factory) -> None:
    user_id = await _make_user(session_factory)

    async with session_factory() as db:
        for _i in range(3):
            await _append_log(
                db,
                user_id=user_id,
                endpoint="/features/in-bounds",
                purpose="viewport_query",
                lat=Decimal("37.5665"),
                lng=Decimal("126.9780"),
                request_id=uuid.uuid4(),
                ip_hash="deadbeef" * 8,
            )

    async with session_factory() as db:
        rows = list(
            (
                await db.execute(select(LocationAccessLog).order_by(LocationAccessLog.log_id))
            ).scalars()
        )

    assert len(rows) == 3
    # 첫 행은 GENESIS, 이후는 직전 content_hash 를 prev_hash 로
    assert rows[0].prev_hash == GENESIS_HASH
    assert rows[1].prev_hash == rows[0].content_hash
    assert rows[2].prev_hash == rows[1].content_hash
    # content_hash 는 모두 다름
    assert len({r.content_hash for r in rows}) == 3


async def test_content_hash_is_recomputable(session_factory) -> None:
    """저장된 payload 로 content_hash 를 재계산하면 일치 (변조 탐지 근거)."""
    user_id = await _make_user(session_factory)
    request_id = uuid.uuid4()

    async with session_factory() as db:
        await _append_log(
            db,
            user_id=user_id,
            endpoint="/features/nearby",
            purpose="nearby_attractions",
            lat=Decimal("35.1796"),
            lng=Decimal("129.0756"),
            request_id=request_id,
            ip_hash="cafe" * 16,
        )

    async with session_factory() as db:
        row = await db.scalar(select(LocationAccessLog))
        assert row is not None
        payload = {
            "user_id": str(row.user_id),
            "occurred_at": row.occurred_at.isoformat(),
            "endpoint": row.endpoint,
            "purpose": row.purpose,
            "lat": str(row.lat) if row.lat is not None else None,
            "lng": str(row.lng) if row.lng is not None else None,
            "request_id": str(row.request_id),
            "ip_hash": row.ip_hash,
        }
        expected = compute_content_hash(row.prev_hash, payload)
        assert row.content_hash == expected
