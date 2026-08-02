"""production causal canary의 crash resume와 fail-close 경계."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.cache_target_contract import CacheTargetMerkleRow, cache_target_snapshot_merkle_root
from app.models.cache_target_sync import (
    KtmCacheTargetCanaryRun,
    KtmCacheTargetCommand,
    KtmCacheTargetConsumer,
    KtmCacheTargetEvent,
    KtmCacheTargetEventClaim,
    KtmCacheTargetEventClaimItem,
    KtmCacheTargetHead,
)
from app.services.cache_target_causal_canary import (
    STABLE_TARGET_ID,
    CacheTargetCanaryFailure,
    _canary_lock,
    run_cache_target_causal_canary,
)
from app.services.cache_target_event_consumer import CacheTargetSnapshot, CacheTargetSnapshotItem

pytestmark = pytest.mark.asyncio

CONSUMER_ID = "pinvi-cache-target-consumer"


class _SnapshotClient:
    def __init__(self, session_factory, *, corrupt_root: bool = False) -> None:  # type: ignore[no-untyped-def]
        self._session_factory = session_factory
        self._corrupt_root = corrupt_root

    async def get_snapshot(self) -> CacheTargetSnapshot:
        async with self._session_factory() as db:
            heads = list(
                await db.scalars(
                    select(KtmCacheTargetHead).order_by(
                        KtmCacheTargetHead.external_system,
                        KtmCacheTargetHead.target_key,
                    )
                )
            )
            consumer = await db.get(KtmCacheTargetConsumer, CONSUMER_ID)
        assert consumer is not None
        assert consumer.active_restore_epoch is not None
        assert consumer.remote_acked_cursor is not None
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
        root = cache_target_snapshot_merkle_root(rows).hex()
        now = datetime.now(UTC)
        return CacheTargetSnapshot(
            snapshot_id=str(uuid.uuid4()),
            restore_epoch=consumer.active_restore_epoch,
            high_watermark_cursor=consumer.remote_acked_cursor,
            count=len(heads),
            merkle_root="00" * 32 if self._corrupt_root else root,
            created_at=now,
            expires_at=now + timedelta(hours=2),
            items=[
                CacheTargetSnapshotItem(
                    external_system=head.external_system,
                    target_key=head.target_key,
                    state=head.desired_state,
                    source_generation=head.source_generation,
                    source_payload_fingerprint=head.source_payload_fingerprint.hex(),
                )
                for head in heads
            ],
        )


async def _seed_consumer(session_factory) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        db.add(
            KtmCacheTargetConsumer(
                consumer_id=CONSUMER_ID,
                external_system="pinvi",
                active_restore_epoch=7,
                local_applied_cursor="cursor-0",
                remote_acked_cursor="cursor-0",
                reconcile_status="matched",
                feature_cache_generation=0,
                ready=True,
            )
        )
        await db.commit()


async def _wait_for_command(session_factory, operation: str) -> KtmCacheTargetCommand:  # type: ignore[no-untyped-def]
    for _ in range(500):
        async with session_factory() as db:
            command = await db.scalar(
                select(KtmCacheTargetCommand).where(
                    KtmCacheTargetCommand.poi_id == STABLE_TARGET_ID,
                    KtmCacheTargetCommand.operation == operation,
                )
            )
            if command is not None:
                return command
        await asyncio.sleep(0.01)
    raise AssertionError(f"{operation} command가 enqueue되지 않았습니다.")


async def _apply_command(
    session_factory,
    operation: str,
    relay_order: int,
    *,
    acked: bool = True,
) -> tuple[uuid.UUID, uuid.UUID]:  # type: ignore[no-untyped-def]
    command = await _wait_for_command(session_factory, operation)
    event_id = uuid.uuid4()
    claim_id = uuid.uuid4()
    target_id = uuid.uuid4()
    now = datetime.now(UTC)
    cursor = f"cursor-{relay_order}"
    async with session_factory() as db:
        command = await db.scalar(
            select(KtmCacheTargetCommand)
            .where(KtmCacheTargetCommand.command_id == command.command_id)
            .with_for_update()
        )
        head = await db.scalar(
            select(KtmCacheTargetHead)
            .where(KtmCacheTargetHead.poi_id == STABLE_TARGET_ID)
            .with_for_update()
        )
        consumer = await db.scalar(
            select(KtmCacheTargetConsumer)
            .where(KtmCacheTargetConsumer.consumer_id == CONSUMER_ID)
            .with_for_update()
        )
        assert command is not None
        assert head is not None
        assert consumer is not None
        state = "active" if operation == "put" else "deleted"
        entity_tag = f'"{target_id}:{relay_order}"'
        payload_target = (
            {
                "target_id": str(target_id),
                "entity_tag": entity_tag,
                "coord": {"lon_e6": 127000000, "lat_e6": 37000000},
                "radius_m": 5000,
                "update_enabled": True,
            }
            if operation == "put"
            else None
        )
        command.status = "succeeded"
        command.completed_at = now
        command.response_etag = entity_tag if operation == "put" else None
        head.remote_target_id = target_id if operation == "put" else None
        head.remote_etag = entity_tag if operation == "put" else None
        head.remote_restore_epoch = 7
        head.remote_source_generation = command.source_generation
        head.remote_target_sequence = relay_order
        head.remote_status = state
        db.add(
            KtmCacheTargetEvent(
                event_id=event_id,
                event_type="cache_target.state_applied",
                external_system="pinvi",
                target_key=str(STABLE_TARGET_ID),
                target_id=target_id,
                restore_epoch=7,
                source_generation=command.source_generation,
                target_sequence=relay_order,
                relay_order=relay_order,
                source_payload_fingerprint=command.payload_fingerprint,
                payload_fingerprint=bytes([relay_order]) * 32,
                occurred_at=now,
                payload={
                    "version": "cache-target-event-v1",
                    "state": state,
                    "source_event_id": str(command.command_id),
                    "target": payload_target,
                },
                applied_at=now,
            )
        )
        db.add(
            KtmCacheTargetEventClaim(
                claim_id=claim_id,
                consumer_id=CONSUMER_ID,
                lease_token=uuid.uuid4(),
                lease_expires_at=now + timedelta(minutes=1),
                status="acked" if acked else "active",
                acked_through_cursor=cursor if acked else None,
                completed_at=now if acked else None,
            )
        )
        await db.flush()
        db.add(
            KtmCacheTargetEventClaimItem(
                claim_id=claim_id,
                event_id=event_id,
                position=1,
                delivery_cursor=cursor,
                payload_fingerprint=bytes([relay_order]) * 32,
                acked_at=now if acked else None,
            )
        )
        consumer.local_applied_cursor = cursor
        if acked:
            consumer.remote_acked_cursor = cursor
        consumer.feature_cache_generation += 1
        await db.commit()
    return event_id, claim_id


async def _ack_claim(session_factory, claim_id: uuid.UUID, relay_order: int) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    async with session_factory() as db:
        claim = await db.scalar(
            select(KtmCacheTargetEventClaim)
            .where(KtmCacheTargetEventClaim.claim_id == claim_id)
            .with_for_update()
        )
        item = await db.scalar(
            select(KtmCacheTargetEventClaimItem)
            .where(KtmCacheTargetEventClaimItem.claim_id == claim_id)
            .with_for_update()
        )
        consumer = await db.scalar(
            select(KtmCacheTargetConsumer)
            .where(KtmCacheTargetConsumer.consumer_id == CONSUMER_ID)
            .with_for_update()
        )
        assert claim is not None
        assert item is not None
        assert consumer is not None
        cursor = f"cursor-{relay_order}"
        claim.status = "acked"
        claim.acked_through_cursor = cursor
        claim.completed_at = now
        item.acked_at = now
        consumer.remote_acked_cursor = cursor
        await db.commit()


async def test_put_timeout_keeps_running_and_same_run_resumes_through_delete(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    run_id = uuid.uuid4()
    engine = session_factory.kw["bind"]
    client = _SnapshotClient(session_factory)
    first = asyncio.create_task(
        run_cache_target_causal_canary(
            session_factory,
            engine,
            consumer_client=client,  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            run_id=run_id,
            timeout_seconds=1,
            poll_seconds=0.01,
        )
    )
    await _apply_command(session_factory, "put", 1)
    with pytest.raises(CacheTargetCanaryFailure, match="causal_wait_timeout"):
        await first
    async with session_factory() as db:
        run = await db.get(KtmCacheTargetCanaryRun, run_id)
        assert run is not None
        assert run.status == "running"
        assert run.phase == "delete_enqueued"

    second = asyncio.create_task(
        run_cache_target_causal_canary(
            session_factory,
            engine,
            consumer_client=client,  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            run_id=run_id,
            timeout_seconds=5,
            poll_seconds=0.01,
        )
    )
    delete_event_id, _ = await _apply_command(session_factory, "delete", 2)
    receipt = await second
    assert receipt.delete_event_id == delete_event_id
    assert receipt.put_generation + 1 == receipt.delete_generation


async def test_unacked_event_does_not_advance_phase_and_can_resume(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    run_id = uuid.uuid4()
    engine = session_factory.kw["bind"]
    client = _SnapshotClient(session_factory)
    first = asyncio.create_task(
        run_cache_target_causal_canary(
            session_factory,
            engine,
            consumer_client=client,  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            run_id=run_id,
            timeout_seconds=1,
            poll_seconds=0.01,
        )
    )
    _, claim_id = await _apply_command(session_factory, "put", 1, acked=False)
    with pytest.raises(CacheTargetCanaryFailure, match="causal_wait_timeout"):
        await first
    async with session_factory() as db:
        run = await db.get(KtmCacheTargetCanaryRun, run_id)
        assert run is not None
        assert run.status == "running"
        assert run.phase == "put_enqueued"

    await _ack_claim(session_factory, claim_id, 1)
    second = asyncio.create_task(
        run_cache_target_causal_canary(
            session_factory,
            engine,
            consumer_client=client,  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            run_id=run_id,
            timeout_seconds=5,
            poll_seconds=0.01,
        )
    )
    await _apply_command(session_factory, "delete", 2)
    assert (await second).run_id == run_id


async def test_corrupt_remote_snapshot_is_terminal_fail_close(session_factory) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    run_id = uuid.uuid4()
    engine = session_factory.kw["bind"]
    client = _SnapshotClient(session_factory, corrupt_root=True)
    task = asyncio.create_task(
        run_cache_target_causal_canary(
            session_factory,
            engine,
            consumer_client=client,  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            run_id=run_id,
            timeout_seconds=5,
            poll_seconds=0.01,
        )
    )
    await _apply_command(session_factory, "put", 1)
    await _apply_command(session_factory, "delete", 2)
    with pytest.raises(CacheTargetCanaryFailure, match="remote_snapshot_merkle_mismatch"):
        await task
    async with session_factory() as db:
        run = await db.get(KtmCacheTargetCanaryRun, run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.terminal_error_code == "remote_snapshot_merkle_mismatch"


async def test_global_canary_lock_rejects_concurrent_runner_without_creating_run(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    run_id = uuid.uuid4()
    engine = session_factory.kw["bind"]
    async with _canary_lock(engine):
        with pytest.raises(CacheTargetCanaryFailure, match="canary_lock_busy"):
            await run_cache_target_causal_canary(
                session_factory,
                engine,
                consumer_client=_SnapshotClient(session_factory),  # type: ignore[arg-type]
                consumer_id=CONSUMER_ID,
                run_id=run_id,
                timeout_seconds=0.1,
                poll_seconds=0.01,
            )
    async with session_factory() as db:
        assert await db.get(KtmCacheTargetCanaryRun, run_id) is None
