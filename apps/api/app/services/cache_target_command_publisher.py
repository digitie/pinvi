"""cache target desired command의 short lease, retry budget, durable outcome."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from app.clients.kor_travel_map_cache_target import (
    CacheTargetContractError,
    CacheTargetMutationResult,
    CacheTargetNetworkError,
    CacheTargetServiceClient,
    CacheTargetServiceProblem,
)
from app.models.cache_target_sync import (
    KtmCacheTargetCommand,
    KtmCacheTargetConsumer,
    KtmCacheTargetHead,
)

CommandOperation = Literal["put", "delete"]


@dataclass(frozen=True, slots=True)
class LeasedCacheTargetCommand:
    command_id: uuid.UUID
    poi_id: uuid.UUID
    operation: CommandOperation
    external_system: Literal["pinvi"]
    target_key: str
    restore_epoch: int
    source_generation: int
    payload: dict[str, object]
    expected_etag: str | None
    occurred_at: datetime
    lease_owner: str


@dataclass(frozen=True, slots=True)
class CacheTargetPublishBatchResult:
    claimed: int
    succeeded: int
    retried: int
    dead_lettered: int
    halted: bool


def _retry_delay(command_id: uuid.UUID, attempts: int) -> timedelta:
    base = min(300.0, float(2 ** min(attempts, 8)))
    jitter = (command_id.int % 1000) / 1000 * base * 0.2
    return timedelta(seconds=base + jitter)


async def lease_cache_target_commands(
    db: AsyncSession,
    *,
    lease_owner: str,
    consumer_id: str,
    limit: int,
    lease_seconds: int,
    max_attempts: int,
    initial_cutover: bool = False,
    now: datetime | None = None,
) -> list[LeasedCacheTargetCommand]:
    """network 밖의 짧은 transaction에서 target별 가장 이른 command만 lease한다."""
    current = now or datetime.now(UTC)
    consumer = await db.scalar(
        select(KtmCacheTargetConsumer)
        .where(KtmCacheTargetConsumer.consumer_id == consumer_id)
        .with_for_update()
    )
    ordinary_ready = (
        consumer is not None
        and consumer.ready
        and consumer.reconcile_status == "matched"
        and consumer.active_restore_epoch is not None
    )
    initial_ready = (
        consumer is not None
        and not consumer.ready
        and consumer.reconcile_status == "checking"
        and consumer.active_restore_epoch is not None
    )
    if not (initial_ready if initial_cutover else ordinary_ready):
        return []
    assert consumer is not None
    assert consumer.active_restore_epoch is not None

    earlier = aliased(KtmCacheTargetCommand)
    blocked_by_earlier = (
        select(earlier.command_id)
        .where(
            earlier.poi_id == KtmCacheTargetCommand.poi_id,
            earlier.source_generation < KtmCacheTargetCommand.source_generation,
            earlier.status.in_(("pending", "leased", "dead_letter")),
        )
        .exists()
    )
    rows = list(
        await db.scalars(
            select(KtmCacheTargetCommand)
            .where(
                (
                    KtmCacheTargetCommand.operation == "put"
                    if initial_cutover
                    else KtmCacheTargetCommand.operation.in_(("put", "delete"))
                ),
                or_(
                    (KtmCacheTargetCommand.status == "pending")
                    & (KtmCacheTargetCommand.available_at <= current),
                    (KtmCacheTargetCommand.status == "leased")
                    & (KtmCacheTargetCommand.lease_until <= current),
                ),
                ~blocked_by_earlier,
            )
            .order_by(
                KtmCacheTargetCommand.available_at,
                KtmCacheTargetCommand.source_generation,
                KtmCacheTargetCommand.command_id,
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    leased: list[LeasedCacheTargetCommand] = []
    for row in rows:
        head = await db.get(KtmCacheTargetHead, row.poi_id)
        if head is None:
            row.status = "dead_letter"
            row.error_code = "MISSING_TARGET_HEAD"
            row.completed_at = current
            continue
        if row.attempts >= max_attempts:
            row.status = "dead_letter"
            row.error_code = "RETRY_BUDGET_EXHAUSTED"
            row.completed_at = current
            continue
        if row.operation == "delete" and head.remote_etag is None:
            row.status = "dead_letter"
            row.error_code = "DELETE_ETAG_MISSING"
            row.completed_at = current
            continue
        row.status = "leased"
        row.attempts += 1
        row.lease_owner = lease_owner
        row.lease_until = current + timedelta(seconds=lease_seconds)
        row.expected_etag = head.remote_etag
        leased.append(
            LeasedCacheTargetCommand(
                command_id=row.command_id,
                poi_id=row.poi_id,
                operation=row.operation,  # type: ignore[arg-type]
                external_system="pinvi",
                target_key=head.target_key,
                restore_epoch=consumer.active_restore_epoch,
                source_generation=row.source_generation,
                payload=row.payload,
                expected_etag=row.expected_etag,
                occurred_at=row.created_at,
                lease_owner=lease_owner,
            )
        )
    await db.flush()
    return leased


async def complete_cache_target_command(
    db: AsyncSession,
    *,
    leased: LeasedCacheTargetCommand,
    result: CacheTargetMutationResult,
    now: datetime | None = None,
) -> None:
    current = now or datetime.now(UTC)
    row = await db.scalar(
        select(KtmCacheTargetCommand)
        .where(KtmCacheTargetCommand.command_id == leased.command_id)
        .with_for_update()
    )
    if row is None or row.status != "leased" or row.lease_owner != leased.lease_owner:
        raise RuntimeError("command lease ownership이 바뀌었습니다.")
    row.status = "succeeded"
    row.response_status = result.status_code
    row.response_body = result.data.model_dump(mode="json")
    row.response_etag = result.etag
    row.error_code = None
    row.error_detail = None
    row.completed_at = current
    row.lease_owner = None
    row.lease_until = None
    head = await db.get(KtmCacheTargetHead, leased.poi_id)
    if head is None:
        raise RuntimeError("command target head가 사라졌습니다.")
    head.remote_target_id = result.data.target_id
    head.remote_etag = result.etag
    head.remote_restore_epoch = result.data.restore_epoch
    head.remote_source_generation = result.data.source_generation
    head.remote_target_sequence = result.data.target_sequence
    head.remote_status = result.data.state
    await db.flush()


async def fail_cache_target_command(
    db: AsyncSession,
    *,
    leased: LeasedCacheTargetCommand,
    error: CacheTargetNetworkError | CacheTargetContractError | CacheTargetServiceProblem,
    max_attempts: int,
    consumer_id: str,
    now: datetime | None = None,
) -> Literal["retry", "dead_letter", "halt", "reconcile"]:
    current = now or datetime.now(UTC)
    row = await db.scalar(
        select(KtmCacheTargetCommand)
        .where(KtmCacheTargetCommand.command_id == leased.command_id)
        .with_for_update()
    )
    if row is None or row.status != "leased" or row.lease_owner != leased.lease_owner:
        raise RuntimeError("command lease ownership이 바뀌었습니다.")
    if isinstance(error, CacheTargetServiceProblem):
        disposition = error.disposition
        code = error.code
        response_status = error.status_code
        retry_after = error.retry_after
    elif isinstance(error, CacheTargetNetworkError):
        disposition = "retry"
        code = "NETWORK_OUTCOME_UNCERTAIN"
        response_status = None
        retry_after = None
    else:
        disposition = "dead_letter"
        code = "RESPONSE_CONTRACT_MISMATCH"
        response_status = None
        retry_after = None
    row.response_status = response_status
    row.error_code = code
    row.error_detail = {"disposition": disposition}
    row.lease_owner = None
    row.lease_until = None
    if disposition == "retry" and row.attempts < max_attempts:
        row.status = "pending"
        delay = (
            timedelta(seconds=retry_after)
            if retry_after is not None
            else _retry_delay(row.command_id, row.attempts)
        )
        row.available_at = current + delay
        await db.flush()
        return "retry"
    row.status = "dead_letter"
    row.completed_at = current
    consumer = await db.scalar(
        select(KtmCacheTargetConsumer)
        .where(KtmCacheTargetConsumer.consumer_id == consumer_id)
        .with_for_update()
    )
    if consumer is not None and disposition in {"halt", "reconcile"}:
        consumer.ready = False
        consumer.reconcile_status = "blocked" if disposition == "halt" else "mismatched"
    await db.flush()
    return "dead_letter" if disposition == "retry" else disposition


async def publish_cache_target_batch(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    client: CacheTargetServiceClient,
    lease_owner: str,
    consumer_id: str,
    limit: int,
    lease_seconds: int,
    max_attempts: int,
    initial_cutover: bool = False,
) -> CacheTargetPublishBatchResult:
    """lease commit → HTTP → CAS outcome commit 순서로 한 batch를 보낸다."""
    async with session_factory() as db:
        leased_rows = await lease_cache_target_commands(
            db,
            lease_owner=lease_owner,
            consumer_id=consumer_id,
            limit=limit,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
            initial_cutover=initial_cutover,
        )
        await db.commit()
    succeeded = retried = dead_lettered = 0
    halted = False
    for leased in leased_rows:
        try:
            if leased.operation == "put":
                result = await client.put_target(
                    external_system=leased.external_system,
                    target_key=leased.target_key,
                    command_id=leased.command_id,
                    restore_epoch=leased.restore_epoch,
                    source_generation=leased.source_generation,
                    occurred_at=leased.occurred_at,
                    source_payload=leased.payload,
                    expected_etag=leased.expected_etag,
                )
            else:
                if leased.expected_etag is None:
                    raise CacheTargetContractError("DELETE lease에 ETag가 없습니다.")
                result = await client.delete_target(
                    external_system=leased.external_system,
                    target_key=leased.target_key,
                    command_id=leased.command_id,
                    restore_epoch=leased.restore_epoch,
                    source_generation=leased.source_generation,
                    occurred_at=leased.occurred_at,
                    source_payload=leased.payload,
                    expected_etag=leased.expected_etag,
                )
        except (
            CacheTargetNetworkError,
            CacheTargetContractError,
            CacheTargetServiceProblem,
        ) as exc:
            async with session_factory() as db:
                outcome = await fail_cache_target_command(
                    db,
                    leased=leased,
                    error=exc,
                    max_attempts=max_attempts,
                    consumer_id=consumer_id,
                )
                await db.commit()
            if outcome == "retry":
                retried += 1
            else:
                dead_lettered += 1
            if outcome in {"halt", "reconcile"}:
                halted = True
                break
        else:
            async with session_factory() as db:
                await complete_cache_target_command(db, leased=leased, result=result)
                await db.commit()
            succeeded += 1
    return CacheTargetPublishBatchResult(
        claimed=len(leased_rows),
        succeeded=succeeded,
        retried=retried,
        dead_lettered=dead_lettered,
        halted=halted,
    )
