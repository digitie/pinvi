"""production causal canary의 crash resume와 fail-close 경계."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

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
        self.calls = 0

    async def get_snapshot(self) -> CacheTargetSnapshot:
        self.calls += 1
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


class _MalformedSnapshotClient:
    def __init__(self, marker: str) -> None:
        self._marker = marker

    async def get_snapshot(self) -> CacheTargetSnapshot:
        return CacheTargetSnapshot.model_validate(
            {
                "snapshot_id": self._marker,
                "restore_epoch": "not-an-integer",
                "raw_url": f"https://user:{self._marker}@invalid.test",
                "items": [],
            }
        )


class _IdentityDriftSnapshotClient(_SnapshotClient):
    async def get_snapshot(self) -> CacheTargetSnapshot:
        snapshot = await super().get_snapshot()
        extra = CacheTargetSnapshotItem(
            external_system="pinvi",
            target_key=str(uuid.uuid4()),
            state="deleted",
            source_generation=1,
            source_payload_fingerprint=("11" * 32),
        )
        items = [*snapshot.items, extra]
        root = cache_target_snapshot_merkle_root(
            [
                CacheTargetMerkleRow(
                    external_system=item.external_system,
                    target_key=item.target_key,
                    state=item.state,
                    source_generation=item.source_generation,
                    source_payload_fingerprint=bytes.fromhex(item.source_payload_fingerprint),
                )
                for item in items
            ]
        ).hex()
        return snapshot.model_copy(
            update={"items": items, "count": len(items), "merkle_root": root}
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


async def _complete_run(session_factory) -> tuple[uuid.UUID, _SnapshotClient]:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    run_id = uuid.uuid4()
    client = _SnapshotClient(session_factory)
    task = asyncio.create_task(
        run_cache_target_causal_canary(
            session_factory,
            session_factory.kw["bind"],
            consumer_client=client,  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            run_id=run_id,
            timeout_seconds=5,
            poll_seconds=0.01,
        )
    )
    await _apply_command(session_factory, "put", 1)
    await _apply_command(session_factory, "delete", 2)
    await task
    return run_id, client


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


async def test_crash_after_success_replay_fetches_fresh_snapshot_before_receipt(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    run_id, client = await _complete_run(session_factory)
    calls_after_commit = client.calls

    receipt = await run_cache_target_causal_canary(
        session_factory,
        session_factory.kw["bind"],
        consumer_client=client,  # type: ignore[arg-type]
        consumer_id=CONSUMER_ID,
        run_id=run_id,
        timeout_seconds=1,
        poll_seconds=0.01,
    )

    assert receipt.run_id == run_id
    assert client.calls == calls_after_commit + 1
    async with session_factory() as db:
        run = await db.get(KtmCacheTargetCanaryRun, run_id)
        assert run is not None
        assert run.final_local_cursor == run.final_remote_cursor
        assert run.final_local_count == run.final_remote_count
        assert run.final_local_merkle_root == run.final_remote_merkle_root
        assert (
            run.final_pending_commands,
            run.final_leased_commands,
            run.final_dead_letter_commands,
        ) == (0, 0, 0)


async def test_database_rejects_success_evidence_divergence(session_factory) -> None:  # type: ignore[no-untyped-def]
    run_id, _ = await _complete_run(session_factory)
    async with session_factory() as db:
        run = await db.get(KtmCacheTargetCanaryRun, run_id)
        assert run is not None
        assert run.final_remote_count is not None
        run.final_remote_count += 1
        with pytest.raises(IntegrityError, match="ck_ktm_ct_canary_final_material"):
            await db.commit()


@pytest.mark.parametrize(
    "drift",
    (
        "head",
        "ready",
        "epoch",
        "cursor",
        "cache-generation",
        "backlog",
        "snapshot-identity",
        "snapshot-self-root",
    ),
)
async def test_crash_after_success_replay_rejects_current_state_drift(
    session_factory,
    drift: str,
) -> None:  # type: ignore[no-untyped-def]
    run_id, client = await _complete_run(session_factory)
    replay_client: object = client
    async with session_factory() as db:
        head = await db.get(KtmCacheTargetHead, STABLE_TARGET_ID)
        consumer = await db.get(KtmCacheTargetConsumer, CONSUMER_ID)
        run = await db.get(KtmCacheTargetCanaryRun, run_id)
        assert head is not None
        assert consumer is not None
        assert run is not None
        if drift == "head":
            head.remote_status = "active"
        elif drift == "ready":
            consumer.ready = False
        elif drift == "epoch":
            consumer.active_restore_epoch += 1
        elif drift == "cursor":
            consumer.local_applied_cursor = "cursor-drift"
            consumer.remote_acked_cursor = "cursor-drift"
        elif drift == "cache-generation":
            consumer.feature_cache_generation += 1
        elif drift == "backlog":
            db.add(
                KtmCacheTargetCommand(
                    command_id=uuid.uuid4(),
                    poi_id=STABLE_TARGET_ID,
                    operation="refresh",
                    source_generation=run.delete_generation,
                    payload={"version": "cache-target-refresh-v1"},
                    payload_fingerprint=b"b" * 32,
                    status="pending",
                )
            )
        elif drift == "snapshot-identity":
            replay_client = _IdentityDriftSnapshotClient(session_factory)
        elif drift == "snapshot-self-root":
            replay_client = _SnapshotClient(session_factory, corrupt_root=True)
        else:
            raise AssertionError(f"unknown drift: {drift}")
        await db.commit()

    with pytest.raises(
        CacheTargetCanaryFailure,
        match=(r"completed_run_drift|event_provenance_mismatch|remote_snapshot_merkle_mismatch"),
    ):
        await run_cache_target_causal_canary(
            session_factory,
            session_factory.kw["bind"],
            consumer_client=replay_client,  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            run_id=run_id,
            timeout_seconds=1,
            poll_seconds=0.01,
        )


async def test_malformed_remote_snapshot_is_terminal_without_raw_input(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    run_id = uuid.uuid4()
    marker = "DO-NOT-LEAK-TOKEN-OR-URL"
    task = asyncio.create_task(
        run_cache_target_causal_canary(
            session_factory,
            session_factory.kw["bind"],
            consumer_client=_MalformedSnapshotClient(marker),  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            run_id=run_id,
            timeout_seconds=5,
            poll_seconds=0.01,
        )
    )
    await _apply_command(session_factory, "put", 1)
    await _apply_command(session_factory, "delete", 2)

    with pytest.raises(CacheTargetCanaryFailure, match="final_snapshot_invalid") as raised:
        await task
    assert marker not in str(raised.value)
    assert raised.value.__suppress_context__ is True
    async with session_factory() as db:
        run = await db.get(KtmCacheTargetCanaryRun, run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.terminal_error_code == "final_snapshot_invalid"


@pytest.mark.parametrize(
    ("corruption", "expected_code"),
    (
        ("command", "command_identity_mismatch"),
        ("event", "event_provenance_mismatch"),
        ("ack", "ack_provenance_mismatch"),
    ),
)
async def test_resume_revalidates_stored_command_event_and_ack_provenance(
    session_factory,
    corruption: str,
    expected_code: str,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    run_id = uuid.uuid4()
    first = asyncio.create_task(
        run_cache_target_causal_canary(
            session_factory,
            session_factory.kw["bind"],
            consumer_client=_SnapshotClient(session_factory),  # type: ignore[arg-type]
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
        assert run.put_event_id is not None
        assert run.put_claim_id is not None
        if corruption == "command":
            command = await db.get(KtmCacheTargetCommand, run.put_command_id)
            assert command is not None
            command.payload = {"version": "corrupted"}
        elif corruption == "event":
            event = await db.get(KtmCacheTargetEvent, run.put_event_id)
            assert event is not None
            event.payload = {**event.payload, "source_event_id": str(uuid.uuid4())}
        elif corruption == "ack":
            item = await db.scalar(
                select(KtmCacheTargetEventClaimItem).where(
                    KtmCacheTargetEventClaimItem.claim_id == run.put_claim_id,
                    KtmCacheTargetEventClaimItem.event_id == run.put_event_id,
                )
            )
            assert item is not None
            item.acked_at = None
        await db.commit()

    with pytest.raises(CacheTargetCanaryFailure, match=expected_code):
        await run_cache_target_causal_canary(
            session_factory,
            session_factory.kw["bind"],
            consumer_client=_SnapshotClient(session_factory),  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            run_id=run_id,
            timeout_seconds=1,
            poll_seconds=0.01,
        )
