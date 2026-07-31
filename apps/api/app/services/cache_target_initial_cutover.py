"""ordinary lifespan과 분리된 cache-target 최초 backfill cutover 도구."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from app.clients.kor_travel_map_cache_target import (
    CacheTargetPreparingReconciliation,
    CacheTargetRunningReconciliation,
    CacheTargetServiceClient,
    CacheTargetServiceProblem,
)
from app.core.cache_target_contract import CacheTargetMerkleRow, cache_target_snapshot_merkle_root
from app.models.cache_target_sync import (
    KtmCacheTargetCommand,
    KtmCacheTargetConsumer,
    KtmCacheTargetHead,
)
from app.services.cache_target_command_publisher import publish_cache_target_batch
from app.services.cache_target_sync_worker import _adopt_stream_epoch, bootstrap_cache_target_sync

_SOURCE_FENCE_NAMESPACE = 1263816009
_SOURCE_FENCE_RESOURCE = 41
_BEGIN_KEY_NAMESPACE = uuid.UUID("25610851-1644-4b3e-823a-782771ecf433")
_SEAL_KEY_NAMESPACE = uuid.UUID("72e2d74e-267c-446f-9e14-9586225da863")


@dataclass(frozen=True, slots=True)
class CacheTargetSourceIdentity:
    count: int
    merkle_root: str


@dataclass(frozen=True, slots=True)
class InitialBackfillDrainResult:
    source: CacheTargetSourceIdentity
    succeeded: int
    batches: int


@dataclass(frozen=True, slots=True)
class InitialCutoverResult:
    cutover_id: uuid.UUID
    reconciliation_request_id: uuid.UUID
    source: CacheTargetSourceIdentity
    published: int


async def read_cache_target_source_identity(db: AsyncSession) -> CacheTargetSourceIdentity:
    heads = list(
        await db.scalars(
            select(KtmCacheTargetHead).order_by(
                KtmCacheTargetHead.external_system,
                KtmCacheTargetHead.target_key,
            )
        )
    )
    rows = [
        CacheTargetMerkleRow(
            external_system=head.external_system,
            target_key=head.target_key,
            state=head.desired_state,  # type: ignore[arg-type]
            source_generation=head.source_generation,
            source_payload_fingerprint=head.source_payload_fingerprint,
        )
        for head in heads
    ]
    return CacheTargetSourceIdentity(
        count=len(rows),
        merkle_root=cache_target_snapshot_merkle_root(rows).hex(),
    )


@asynccontextmanager
async def cache_target_source_writer_fence(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """DB trigger의 shared xact lock과 짝인 session-level exclusive cutover lock."""
    async with engine.connect() as connection:
        acquired = await connection.scalar(
            text("SELECT pg_try_advisory_lock(:namespace, :resource)"),
            {"namespace": _SOURCE_FENCE_NAMESPACE, "resource": _SOURCE_FENCE_RESOURCE},
        )
        if acquired is not True:
            raise RuntimeError(
                "cache target source writer가 active이거나 cutover가 이미 실행 중입니다."
            )
        try:
            yield connection
        finally:
            released = await connection.scalar(
                text("SELECT pg_advisory_unlock(:namespace, :resource)"),
                {"namespace": _SOURCE_FENCE_NAMESPACE, "resource": _SOURCE_FENCE_RESOURCE},
            )
            if released is not True:
                raise RuntimeError("cache target source writer fence 해제에 실패했습니다.")


async def drain_initial_cache_target_puts(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    command_client: CacheTargetServiceClient,
    consumer_id: str,
    cutover_id: uuid.UUID,
    batch_size: int,
    lease_seconds: int,
    max_attempts: int,
    max_batches: int = 10_000,
) -> InitialBackfillDrainResult:
    """source fence 안에서 generation 순서의 pending PUT을 idempotent하게 drain한다."""
    async with session_factory() as db:
        source = await read_cache_target_source_identity(db)
    succeeded = 0
    for batch_number in range(1, max_batches + 1):
        result = await publish_cache_target_batch(
            session_factory,
            client=command_client,
            lease_owner=f"initial-cutover:{cutover_id}",
            consumer_id=consumer_id,
            limit=batch_size,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
            initial_cutover=True,
        )
        if result.halted or result.dead_lettered:
            raise RuntimeError("initial cutover PUT이 terminal failure로 중단됐습니다.")
        succeeded += result.succeeded
        async with session_factory() as db:
            current = await read_cache_target_source_identity(db)
            if current != source:
                raise RuntimeError("writer fence 중 cache target source identity가 바뀌었습니다.")
            active_commands = int(
                await db.scalar(
                    select(func.count())
                    .select_from(KtmCacheTargetCommand)
                    .where(KtmCacheTargetCommand.status.in_(("pending", "leased", "dead_letter")))
                )
                or 0
            )
            non_put_commands = int(
                await db.scalar(
                    select(func.count())
                    .select_from(KtmCacheTargetCommand)
                    .where(
                        KtmCacheTargetCommand.status.in_(("pending", "leased", "dead_letter")),
                        KtmCacheTargetCommand.operation != "put",
                    )
                )
                or 0
            )
        if non_put_commands:
            raise RuntimeError("initial cutover에 PUT 이외의 미완료 command가 있습니다.")
        if active_commands == 0:
            return InitialBackfillDrainResult(
                source=source,
                succeeded=succeeded,
                batches=batch_number,
            )
        if result.claimed == 0:
            raise RuntimeError(
                "initial cutover PUT이 retry lease 대기 상태입니다. 같은 cutover ID로 재개하세요."
            )
    raise RuntimeError("initial cutover PUT batch 한도를 초과했습니다.")


async def run_initial_cache_target_cutover(
    session_factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    *,
    command_client: CacheTargetServiceClient,
    consumer_client: CacheTargetServiceClient,
    recovery_client: CacheTargetServiceClient,
    consumer_id: str,
    cutover_id: uuid.UUID,
    expected_restore_epoch: int,
    reason: str,
    batch_size: int,
    lease_seconds: int,
    max_attempts: int,
) -> InitialCutoverResult:
    """begin→PUT drain→seal→bound snapshot completion을 동일 cutover ID로 재개한다."""
    if not reason or reason != reason.strip():
        raise ValueError("initial cutover reason은 trim된 non-empty 문자열이어야 합니다.")
    async with cache_target_source_writer_fence(engine):
        try:
            stream = await consumer_client.get_stream()
        except CacheTargetServiceProblem as exc:
            if exc.status_code != 404:
                raise
            stream = None
        if stream is not None:
            if stream.consumer_id not in {None, consumer_id} or stream.blocked_event_id is not None:
                raise RuntimeError("Map initial cutover stream binding/block 상태가 다릅니다.")
            if stream.restore_epoch != expected_restore_epoch:
                raise RuntimeError("Map initial cutover restore epoch이 expected 값과 다릅니다.")

        async with session_factory() as db:
            source = await read_cache_target_source_identity(db)
            consumer = await db.scalar(
                select(KtmCacheTargetConsumer)
                .where(KtmCacheTargetConsumer.consumer_id == consumer_id)
                .with_for_update()
            )
            if consumer is None:
                consumer = KtmCacheTargetConsumer(
                    consumer_id=consumer_id,
                    external_system="pinvi",
                    active_restore_epoch=expected_restore_epoch,
                    reconcile_status="checking",
                    ready=False,
                )
                db.add(consumer)
                await db.flush()
            if consumer.initial_cutover_id is None:
                consumer.initial_cutover_id = cutover_id
                consumer.initial_begin_stream_etag = (
                    stream.entity_tag if stream is not None else None
                )
                consumer.initial_source_count = source.count
                consumer.initial_source_merkle_root = bytes.fromhex(source.merkle_root)
            elif consumer.initial_cutover_id != cutover_id:
                raise RuntimeError("다른 initial cutover ID가 이미 durable state를 소유합니다.")
            elif (
                consumer.initial_source_count != source.count
                or consumer.initial_source_merkle_root != bytes.fromhex(source.merkle_root)
            ):
                raise RuntimeError("재개한 initial cutover의 source identity가 바뀌었습니다.")
            if consumer.initial_cutover_completed_at is not None:
                request_id = consumer.initial_reconciliation_request_id
                if request_id is None or not consumer.ready:
                    raise RuntimeError("완료된 initial cutover durable state가 모순됩니다.")
                await db.commit()
                return InitialCutoverResult(cutover_id, request_id, source, 0)
            begin_stream_etag = consumer.initial_begin_stream_etag
            await db.commit()

        begin = await recovery_client.begin_initial_reconciliation(
            consumer_id=consumer_id,
            expected_restore_epoch=expected_restore_epoch,
            reason=reason,
            idempotency_key=uuid.uuid5(_BEGIN_KEY_NAMESPACE, str(cutover_id)),
            stream_etag=begin_stream_etag,
        )
        request_id = begin.operation.operation_id
        async with session_factory() as db:
            consumer = await db.scalar(
                select(KtmCacheTargetConsumer)
                .where(KtmCacheTargetConsumer.consumer_id == consumer_id)
                .with_for_update()
            )
            if consumer is None or consumer.initial_cutover_id != cutover_id:
                raise RuntimeError("initial cutover durable owner가 사라졌습니다.")
            if consumer.initial_reconciliation_request_id not in {None, request_id}:
                raise RuntimeError("initial reconciliation request ID가 바뀌었습니다.")
            consumer.initial_reconciliation_request_id = request_id
            consumer.initial_reconciliation_etag = begin.etag
            await db.commit()

        preparing_stream = await consumer_client.get_stream()
        active = preparing_stream.active_reconciliation
        if preparing_stream.restore_epoch != expected_restore_epoch:
            raise RuntimeError("begin 뒤 reconciliation restore epoch이 다릅니다.")
        if active is None:
            async with session_factory() as db:
                consumer = await db.get(KtmCacheTargetConsumer, consumer_id)
                if (
                    preparing_stream.state != "ready"
                    or consumer is None
                    or consumer.initial_reconciliation_request_id != request_id
                    or not consumer.ready
                ):
                    raise RuntimeError(
                        "active descriptor 없는 initial cutover resume state가 다릅니다."
                    )
                consumer.initial_cutover_completed_at = (
                    consumer.initial_cutover_completed_at or datetime.now(UTC)
                )
                await db.commit()
            return InitialCutoverResult(cutover_id, request_id, source, 0)
        if active.request_id != request_id or not isinstance(
            active,
            (CacheTargetPreparingReconciliation, CacheTargetRunningReconciliation),
        ):
            raise RuntimeError("begin 뒤 reconciliation discovery가 다릅니다.")
        async with session_factory() as db:
            await _adopt_stream_epoch(db, stream=preparing_stream, consumer_id=consumer_id)
            await db.commit()

        drained = await drain_initial_cache_target_puts(
            session_factory,
            command_client=command_client,
            consumer_id=consumer_id,
            cutover_id=cutover_id,
            batch_size=batch_size,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        )
        if drained.source != source:
            raise RuntimeError("initial cutover drain source identity가 바뀌었습니다.")

        seal = await recovery_client.seal_initial_reconciliation(
            request_id=request_id,
            consumer_id=consumer_id,
            expected_restore_epoch=expected_restore_epoch,
            expected_item_count=source.count,
            expected_merkle_root=source.merkle_root,
            idempotency_key=uuid.uuid5(_SEAL_KEY_NAMESPACE, str(cutover_id)),
            stream_etag=begin.etag,
        )
        async with session_factory() as db:
            consumer = await db.get(KtmCacheTargetConsumer, consumer_id)
            if consumer is None or consumer.initial_cutover_id != cutover_id:
                raise RuntimeError("seal 뒤 initial cutover durable owner가 사라졌습니다.")
            consumer.initial_reconciliation_etag = seal.etag
            await db.commit()

        running_stream = await consumer_client.get_stream()
        running = running_stream.active_reconciliation
        if running is None and running_stream.state == "ready":
            async with session_factory() as db:
                consumer = await db.get(KtmCacheTargetConsumer, consumer_id)
                if consumer is None or not consumer.ready:
                    raise RuntimeError("completion replay 뒤 local ready state가 없습니다.")
                consumer.initial_cutover_completed_at = (
                    consumer.initial_cutover_completed_at or datetime.now(UTC)
                )
                await db.commit()
            return InitialCutoverResult(cutover_id, request_id, source, drained.succeeded)
        if (
            not isinstance(running, CacheTargetRunningReconciliation)
            or running.request_id != request_id
            or running.restore_epoch != expected_restore_epoch
            or running.count != source.count
            or running.merkle_root != source.merkle_root
        ):
            raise RuntimeError("seal 뒤 running fixed snapshot descriptor가 다릅니다.")
        await bootstrap_cache_target_sync(
            session_factory,
            consumer_client=consumer_client,
            consumer_id=consumer_id,
        )
        async with session_factory() as db:
            consumer = await db.scalar(
                select(KtmCacheTargetConsumer)
                .where(KtmCacheTargetConsumer.consumer_id == consumer_id)
                .with_for_update()
            )
            if (
                consumer is None
                or consumer.initial_cutover_id != cutover_id
                or consumer.initial_reconciliation_request_id != request_id
                or not consumer.ready
            ):
                raise RuntimeError("initial cutover completion durable state가 다릅니다.")
            consumer.initial_cutover_completed_at = datetime.now(UTC)
            await db.commit()
        return InitialCutoverResult(cutover_id, request_id, source, drained.succeeded)
