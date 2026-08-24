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
from typing import Any

from fastapi import FastAPI
from sqlalchemy import func, select, text, update
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


_PREV_CONTENT_HASH_SQL = text(
    """
    SELECT content_hash
    FROM (
      SELECT log_id, content_hash FROM app.location_access_log
      UNION ALL
      SELECT log_id, content_hash FROM app.location_access_log_archive
    ) chain
    -- 캐스트를 명시한다. asyncpg는 파라미터를 그대로 IS NULL과 비교하면 타입을 정하지 못해
    -- AmbiguousParameterError를 낸다.
    -- (주석에 콜론 파라미터 표기를 쓰지 마라 — text()는 주석 안의 것도 바인드로 읽는다.)
    WHERE CAST(:before_log_id AS bigint) IS NULL OR log_id < CAST(:before_log_id AS bigint)
    ORDER BY log_id DESC
    LIMIT 1
    """
)


async def previous_content_hash(session: AsyncSession, *, before_log_id: int | None = None) -> str:
    """체인에서 직전 행의 `content_hash`. 없으면 `GENESIS_HASH`.

    **아카이브를 함께 본다.** retention이 실행되면 원본 행은 삭제되고 아카이브로 옮겨지는데,
    active 테이블만 보면 그 링크가 끊긴 것처럼 보인다(T-335). 결과는 두 방향 모두 나쁘다.

    - 쓰기 측(`append_location_log`): 전량 배수 후 `prev_hash`가 `GENESIS_HASH`로 돌아가 체인이
      조용히 재시작된다. 끊긴 자리가 영구히 남는다.
    - 검증 측(admin 확인자료 열람): 살아남은 최고참 행의 `prev_hash`가 아카이브된 해시를 가리키는데
      앵커는 `None`이라 `GENESIS_HASH`와 비교돼 **상시 불일치**한다. 위변조 탐지가 항상 켜지면
      실제 변조와 구분할 수 없다.

    `before_log_id`가 `None`이면 체인 전체의 마지막 행을 본다(append 시). 값이 있으면 그보다 앞선
    마지막 행을 본다(윈도우 앵커 검증 시).

    아카이브 INSERT와 원본 DELETE 사이에는 같은 `log_id`가 양쪽에 잠깐 존재하지만, 같은 행의 같은
    해시이므로 무해하다.
    """
    found = await session.scalar(_PREV_CONTENT_HASH_SQL, {"before_log_id": before_log_id})
    return str(found) if found is not None else GENESIS_HASH


def location_log_payload(
    *,
    user_id: uuid.UUID,
    occurred_at: datetime,
    endpoint: str,
    purpose: str,
    lat: Decimal | None,
    lng: Decimal | None,
    request_id: uuid.UUID,
    ip_hash: str,
    coord_source: str | None,
) -> dict[str, Any]:
    """`content_hash`가 덮는 필드의 **정본**. 쓰기와 검증이 반드시 같은 것을 써야 한다.

    이 함수가 존재하는 이유는 하나다. 예전에는 payload 구성이 두 곳에 복제돼 있었고
    (`append_location_log`와 admin 체인 검증기), T-329가 `coord_source`를 쓰기 측에만 추가하는
    바람에 **정상 행이 전부 변조로 판정되는** 결함이 생겼다. 위변조 탐지 신호가 상시 켜지면
    실제 변조와 구분할 수 없으므로 확인자료의 무결성 증명 수단이 죽는다.

    출처가 `None`이면 **키 자체를 넣지 않는다.** payload는 `sort_keys=True` canonical JSON이라,
    키를 생략해야 이 컬럼이 없던 시절 행의 재계산 결과가 바이트 단위로 유지된다
    (`"coord_source": null`을 넣으면 과거 행 전체의 content_hash가 어긋난다).
    """
    payload: dict[str, Any] = {
        "user_id": str(user_id),
        "occurred_at": occurred_at.isoformat(),
        "endpoint": endpoint,
        "purpose": purpose,
        "lat": _coord_str(lat),
        "lng": _coord_str(lng),
        "request_id": str(request_id),
        "ip_hash": ip_hash,
    }
    if coord_source is not None:
        payload["coord_source"] = coord_source
    return payload


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
    coord_source: str | None = None,
    occurred_at: datetime | None = None,
    commit: bool = True,
) -> LocationAccessLog:
    """체인 1건 append. 호출 측이 직렬화(동일 session 순차 또는 advisory lock)를 보장해야 한다."""
    moment = occurred_at or datetime.now(UTC)
    prev_hash = await previous_content_hash(session)
    payload = location_log_payload(
        user_id=user_id,
        occurred_at=moment,
        endpoint=endpoint,
        purpose=purpose,
        lat=lat,
        lng=lng,
        request_id=request_id,
        ip_hash=ip_hash,
        coord_source=coord_source,
    )
    row = LocationAccessLog(
        user_id=user_id,
        occurred_at=moment,
        endpoint=endpoint,
        purpose=purpose,
        lat=lat,
        lng=lng,
        request_id=request_id,
        ip_hash=ip_hash,
        coord_source=coord_source,
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
    coord_source: str | None = None,
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
            coord_source=coord_source,
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
    # 행마다 SAVEPOINT로 격리한다. 한 행이 실패해도(예: purpose CHECK 드리프트) 배치 전체가
    # abort되지 않게 하기 위해서다 — 그렇지 않으면 실패한 head 행을 영원히 재시도하며
    # 이후 모든 감사 기록이 멈춘다(위치정보법 제16조 확인자료 기록 중단, T-328).
    appended: list[int] = []
    for event in pending:
        try:
            async with session.begin_nested():
                await append_location_log(
                    session,
                    user_id=event.user_id,
                    endpoint=event.endpoint,
                    purpose=event.purpose,
                    lat=event.lat,
                    lng=event.lng,
                    request_id=event.request_id,
                    ip_hash=event.ip_hash,
                    coord_source=event.coord_source,
                    occurred_at=event.occurred_at,
                    commit=False,
                )
        except Exception:
            # `SQLAlchemyError`만 잡으면 부족하다 — 이미 적재된 비유한 좌표(NaN/Infinity)는
            # `_coord_str`의 quantize에서 `InvalidOperation`을 던지는데 그것은 `ArithmeticError`
            # 계열이라 DB 예외가 아니다. 그 한 행이 배치를 탈출시키면 T-328이 고친 "감사 전면 정지"가
            # 그대로 재현된다. 새 행은 미들웨어가 막지만(T-330), 이미 outbox에 있는 행은 여기서만
            # 막을 수 있다.
            #
            # 실패 행은 `processed_at`을 채우지 않아 다음 drain에서 다시 시도된다. 다만 뒤 행을
            # 막지는 않는다. 원인은 로그로 드러내야 조용히 유실되지 않는다.
            logger.warning(
                "location_audit.drain_row_failed outbox_id=%s purpose=%s endpoint=%s",
                event.outbox_id,
                event.purpose,
                event.endpoint,
                exc_info=True,
            )
            continue
        appended.append(event.outbox_id)

    if appended:
        await session.execute(
            update(LocationAuditOutbox)
            .where(LocationAuditOutbox.outbox_id.in_(appended))
            .values(processed_at=now)
        )
    await session.commit()
    return len(appended)


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
    if not settings.pinvi_location_audit_outbox_worker_enabled:
        yield
        return
    task = asyncio.create_task(
        _drain_loop(
            settings.pinvi_location_audit_outbox_drain_interval_seconds,
            settings.pinvi_location_audit_outbox_batch_size,
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
