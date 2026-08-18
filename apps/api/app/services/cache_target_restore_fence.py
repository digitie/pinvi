"""restore 전용 principal이 writer 재개 전 Map stream epoch를 봉인한다."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.kor_travel_map_cache_target import (
    CacheTargetContractError,
    CacheTargetRestoreFenceRecord,
    CacheTargetRestoreFenceResult,
    CacheTargetServiceClient,
)
from app.models.cache_target_sync import KtmCacheTargetRestoreFenceAttempt


@dataclass(frozen=True, slots=True)
class CacheTargetRestoreFenceRunResult:
    """원격 restore receipt와 재조회한 stream tuple."""

    receipt: CacheTargetRestoreFenceResult


def _validate_attempt_request(
    attempt: KtmCacheTargetRestoreFenceAttempt,
    *,
    consumer_id: str,
    expected_restore_epoch: int,
    reason: str,
) -> None:
    if (
        attempt.consumer_id != consumer_id
        or attempt.external_system != "pinvi"
        or attempt.expected_restore_epoch != expected_restore_epoch
        or attempt.reason != reason
    ):
        raise CacheTargetContractError(
            "Idempotency-Key가 다른 restore fence 입력에 이미 결박됐습니다."
        )
    if attempt.status not in {"pending", "completed"}:
        raise CacheTargetContractError("restore fence 영수증 상태가 허용되지 않습니다.")


def _receipt_from_attempt(
    attempt: KtmCacheTargetRestoreFenceAttempt,
) -> CacheTargetRestoreFenceResult:
    if (
        attempt.status != "completed"
        or attempt.response_status not in {200, 201}
        or attempt.response_etag is None
        or attempt.response_body is None
    ):
        raise CacheTargetContractError("완료된 restore fence 영수증이 없습니다.")
    return CacheTargetRestoreFenceResult(
        status_code=attempt.response_status,
        data=CacheTargetRestoreFenceRecord.model_validate(attempt.response_body),
        etag=attempt.response_etag,
    )


async def _locked_attempt(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    idempotency_key: uuid.UUID,
) -> KtmCacheTargetRestoreFenceAttempt | None:
    async with session_factory() as db:
        async with db.begin():
            return cast(
                KtmCacheTargetRestoreFenceAttempt | None,
                await db.scalar(
                    select(KtmCacheTargetRestoreFenceAttempt)
                    .where(KtmCacheTargetRestoreFenceAttempt.idempotency_key == idempotency_key)
                    .with_for_update()
                ),
            )


async def _persist_or_load_pre_cas_attempt(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    idempotency_key: uuid.UUID,
    consumer_id: str,
    expected_restore_epoch: int,
    expected_control_version: int,
    stream_etag: str,
    reason: str,
) -> KtmCacheTargetRestoreFenceAttempt:
    """최초 GET tuple을 한 번만 기록하고, 동시 같은 key는 그 행을 재사용한다."""
    async with session_factory() as db:
        async with db.begin():
            inserted = await db.scalar(
                pg_insert(KtmCacheTargetRestoreFenceAttempt)
                .values(
                    idempotency_key=idempotency_key,
                    consumer_id=consumer_id,
                    external_system="pinvi",
                    expected_restore_epoch=expected_restore_epoch,
                    expected_control_version=expected_control_version,
                    stream_etag=stream_etag,
                    reason=reason,
                    status="pending",
                )
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
                .returning(KtmCacheTargetRestoreFenceAttempt)
            )
            if inserted is not None:
                return inserted
            existing = await db.scalar(
                select(KtmCacheTargetRestoreFenceAttempt)
                .where(KtmCacheTargetRestoreFenceAttempt.idempotency_key == idempotency_key)
                .with_for_update()
            )
            if existing is None:  # pragma: no cover - PostgreSQL ON CONFLICT serializes this path.
                raise CacheTargetContractError("restore fence 영수증을 다시 읽지 못했습니다.")
            return existing


async def _complete_attempt(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    idempotency_key: uuid.UUID,
    receipt: CacheTargetRestoreFenceResult,
) -> CacheTargetRestoreFenceResult:
    """동시 재시도 중 처음 받은 Map receipt만 durable terminal로 고정한다."""
    async with session_factory() as db:
        async with db.begin():
            attempt = await db.scalar(
                select(KtmCacheTargetRestoreFenceAttempt)
                .where(KtmCacheTargetRestoreFenceAttempt.idempotency_key == idempotency_key)
                .with_for_update()
            )
            if attempt is None:  # pragma: no cover - pre-CAS write is committed before HTTP.
                raise CacheTargetContractError("restore fence 영수증이 사라졌습니다.")
            if attempt.status == "completed":
                stored = _receipt_from_attempt(attempt)
                # Map은 정확히 같은 Idempotency-Key의 최초 응답을 201, 재전송을
                # 200으로 구분한다. 병렬 runner는 이 두 응답을 모두 받을 수 있으므로
                # transport 상태가 아니라 immutable fence payload와 ETag만 비교한다.
                if stored.data != receipt.data or stored.etag != receipt.etag:
                    raise CacheTargetContractError(
                        "같은 Idempotency-Key의 Map receipt가 달라졌습니다."
                    )
                return stored
            attempt.status = "completed"
            attempt.response_status = receipt.status_code
            attempt.response_etag = receipt.etag
            attempt.response_body = receipt.data.model_dump(mode="json")
            attempt.completed_at = datetime.now(UTC)
            await db.flush()
            return receipt


async def _validate_post_fence_tuple(
    *,
    consumer_client: CacheTargetServiceClient,
    consumer_id: str,
    receipt: CacheTargetRestoreFenceResult,
) -> None:
    after = await consumer_client.get_stream()
    if (
        after.consumer_id not in {None, consumer_id}
        or after.restore_epoch != receipt.data.restore_epoch
        or after.control_version != receipt.data.control_version
        or after.entity_tag != receipt.etag
        or after.state != "fenced"
        or after.blocked_event_id is not None
        or after.active_reconciliation is not None
    ):
        raise CacheTargetContractError("restore fence 뒤 Map stream tuple이 receipt와 다릅니다.")


async def run_cache_target_restore_fence(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    consumer_client: CacheTargetServiceClient,
    restore_client: CacheTargetServiceClient,
    consumer_id: str,
    expected_restore_epoch: int,
    idempotency_key: uuid.UUID,
    reason: str,
) -> CacheTargetRestoreFenceRunResult:
    """GET의 raw ETag를 durable receipt에 먼저 봉인하고 Map CAS를 전진시킨다.

    최초 POST가 Map에서 commit된 뒤 응답이 유실되어도 pending receipt는 같은 ETag와
    control tuple을 남긴다. 다음 실행은 새 stream GET로 epoch를 거부하지 않고 정확한
    Idempotency-Key/If-Match를 재사용해 Map의 200 exact replay를 받는다.
    """
    attempt = await _locked_attempt(session_factory, idempotency_key=idempotency_key)
    if attempt is not None:
        _validate_attempt_request(
            attempt,
            consumer_id=consumer_id,
            expected_restore_epoch=expected_restore_epoch,
            reason=reason,
        )
        if attempt.status == "completed":
            receipt = _receipt_from_attempt(attempt)
            await _validate_post_fence_tuple(
                consumer_client=consumer_client,
                consumer_id=consumer_id,
                receipt=receipt,
            )
            return CacheTargetRestoreFenceRunResult(receipt=receipt)
    else:
        before = await consumer_client.get_stream()
        if before.consumer_id not in {None, consumer_id}:
            raise CacheTargetContractError("restore 전 Map stream consumer binding이 다릅니다.")
        if before.restore_epoch != expected_restore_epoch:
            raise CacheTargetContractError("restore 전 Map stream epoch이 expected 값과 다릅니다.")
        attempt = await _persist_or_load_pre_cas_attempt(
            session_factory,
            idempotency_key=idempotency_key,
            consumer_id=consumer_id,
            expected_restore_epoch=expected_restore_epoch,
            expected_control_version=before.control_version,
            stream_etag=before.entity_tag,
            reason=reason,
        )
        _validate_attempt_request(
            attempt,
            consumer_id=consumer_id,
            expected_restore_epoch=expected_restore_epoch,
            reason=reason,
        )
        if attempt.status == "completed":
            receipt = _receipt_from_attempt(attempt)
            await _validate_post_fence_tuple(
                consumer_client=consumer_client,
                consumer_id=consumer_id,
                receipt=receipt,
            )
            return CacheTargetRestoreFenceRunResult(receipt=receipt)

    receipt = await restore_client.advance_restore_fence(
        consumer_id=consumer_id,
        expected_restore_epoch=attempt.expected_restore_epoch,
        reason=attempt.reason,
        idempotency_key=idempotency_key,
        stream_etag=attempt.stream_etag,
    )
    if (
        receipt.data.previous_control_version != attempt.expected_control_version
        or receipt.data.previous_restore_epoch != attempt.expected_restore_epoch
    ):
        raise CacheTargetContractError("restore fence receipt가 durable pre-CAS tuple과 다릅니다.")
    receipt = await _complete_attempt(
        session_factory,
        idempotency_key=idempotency_key,
        receipt=receipt,
    )
    await _validate_post_fence_tuple(
        consumer_client=consumer_client,
        consumer_id=consumer_id,
        receipt=receipt,
    )
    return CacheTargetRestoreFenceRunResult(receipt=receipt)
