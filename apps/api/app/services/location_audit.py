"""위치 감사 체인 + async outbox (T-146 / D-20) — `docs/compliance/lbs-act.md` §3.

요청 경로에서는 outbox에 빠르게 append(체인 해시 동기계산 금지 → 단일 노드 hotspot 제거),
단일 writer worker가 `drain_location_audit_outbox`로 `location_access_log` 체인을 순차 구성한다.
advisory xact lock으로 동시 drain의 체인 fork를 막는다.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import async_session_factory
from app.models.audit import LocationAccessLog, LocationAuditOutbox
from app.services.hash_chain import GENESIS_HASH, compute_content_hash

logger = logging.getLogger("location_audit")

# 동시 drain 직렬화용 advisory lock 키(고정).
_DRAIN_LOCK_KEY = 471_146


def _coord_str(value: Decimal | None) -> str | None:
    """Numeric(9,6) 저장 표현과 일치하도록 6자리 quantize (chain 재검증 결정성)."""
    if value is None:
        return None
    return str(value.quantize(Decimal("0.000001")))


async def append_location_log(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    endpoint: str,
    purpose: str,
    lat: Decimal | None,
    lng: Decimal | None,
    request_id: uuid.UUID,
    ip_hash: str,
    occurred_at: datetime | None = None,
    commit: bool = True,
) -> LocationAccessLog:
    """체인 1건 append. 호출 측이 직렬화(동일 session 순차 또는 advisory lock)를 보장해야 한다."""
    moment = occurred_at or datetime.now(UTC)
    last = await session.scalar(
        select(LocationAccessLog).order_by(LocationAccessLog.log_id.desc()).limit(1)
    )
    prev_hash = last.content_hash if last else GENESIS_HASH
    payload = {
        "user_id": str(user_id),
        "occurred_at": moment.isoformat(),
        "endpoint": endpoint,
        "purpose": purpose,
        "lat": _coord_str(lat),
        "lng": _coord_str(lng),
        "request_id": str(request_id),
        "ip_hash": ip_hash,
    }
    row = LocationAccessLog(
        user_id=user_id,
        occurred_at=moment,
        endpoint=endpoint,
        purpose=purpose,
        lat=lat,
        lng=lng,
        request_id=request_id,
        ip_hash=ip_hash,
        prev_hash=prev_hash,
        content_hash=compute_content_hash(prev_hash, payload),
    )
    session.add(row)
    if commit:
        await session.commit()
    else:
        await session.flush()
    return row


async def enqueue_location_audit_outbox(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    endpoint: str,
    purpose: str,
    lat: Decimal | None,
    lng: Decimal | None,
    request_id: uuid.UUID,
    ip_hash: str,
) -> None:
    """요청 경로 — outbox에 빠르게 append(체인 계산 없음)."""
    session.add(
        LocationAuditOutbox(
            user_id=user_id,
            occurred_at=datetime.now(UTC),
            endpoint=endpoint,
            purpose=purpose,
            lat=lat,
            lng=lng,
            request_id=request_id,
            ip_hash=ip_hash,
        )
    )
    await session.commit()


async def drain_location_audit_outbox(session: AsyncSession, *, batch_size: int = 200) -> int:
    """미처리 outbox를 occurred 순서로 체인에 반영. 단일 writer(advisory lock). 처리 건수 반환."""
    locked = await session.scalar(select(func.pg_try_advisory_xact_lock(_DRAIN_LOCK_KEY)))
    if not locked:
        return 0
    pending = list(
        (
            await session.execute(
                select(LocationAuditOutbox)
                .where(LocationAuditOutbox.processed_at.is_(None))
                .order_by(LocationAuditOutbox.outbox_id)
                .limit(batch_size)
            )
        ).scalars()
    )
    if not pending:
        await session.commit()  # advisory xact lock 해제
        return 0
    now = datetime.now(UTC)
    for event in pending:
        await append_location_log(
            session,
            user_id=event.user_id,
            endpoint=event.endpoint,
            purpose=event.purpose,
            lat=event.lat,
            lng=event.lng,
            request_id=event.request_id,
            ip_hash=event.ip_hash,
            occurred_at=event.occurred_at,
            commit=False,
        )
    await session.execute(
        update(LocationAuditOutbox)
        .where(LocationAuditOutbox.outbox_id.in_([e.outbox_id for e in pending]))
        .values(processed_at=now)
    )
    await session.commit()
    return len(pending)


async def _drain_loop(interval: float, batch_size: int) -> None:
    while True:
        try:
            async with async_session_factory() as session:
                processed = await drain_location_audit_outbox(session, batch_size=batch_size)
            # 처리할 게 남아 있으면(배치 가득) 즉시 한 번 더, 아니면 interval 대기.
            if processed < batch_size:
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("location_audit.drain_failed", exc_info=True)
            await asyncio.sleep(interval)


@asynccontextmanager
async def location_audit_outbox_worker_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan — 백그라운드 outbox drain worker(단일 task) 시작/정리."""
    if not settings.tripmate_location_audit_outbox_worker_enabled:
        yield
        return
    task = asyncio.create_task(
        _drain_loop(
            settings.tripmate_location_audit_outbox_drain_interval_seconds,
            settings.tripmate_location_audit_outbox_batch_size,
        ),
        name="location-audit-outbox-drain",
    )
    app.state.location_audit_outbox_worker = task
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        app.state.location_audit_outbox_worker = None
