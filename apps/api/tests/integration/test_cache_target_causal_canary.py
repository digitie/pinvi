"""production causal canary의 crash resume와 fail-close 경계."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.clients.kor_travel_map_cache_target import (
    CacheTargetContractError,
    CacheTargetNetworkError,
    CacheTargetServiceProblem,
    CacheTargetStreamState,
)
from app.core.cache_target_contract import CacheTargetMerkleRow, cache_target_snapshot_merkle_root
from app.models.cache_target_sync import (
    KtmCacheTargetBoundaryAudit,
    KtmCacheTargetCanaryRun,
    KtmCacheTargetCommand,
    KtmCacheTargetConsumer,
    KtmCacheTargetEvent,
    KtmCacheTargetEventClaim,
    KtmCacheTargetEventClaimItem,
    KtmCacheTargetHead,
    KtmCacheTargetReconciliationExpectation,
)
from app.services import cache_target_causal_canary as canary_service
from app.services import cache_target_final_boundary as boundary_service
from app.services.cache_target_boundary_evidence import canonical_sha256
from app.services.cache_target_causal_canary import (
    STABLE_TARGET_ID,
    CacheTargetCanaryFailure,
    _canary_lock,
    run_cache_target_causal_canary,
)
from app.services.cache_target_event_consumer import CacheTargetSnapshot, CacheTargetSnapshotItem
from app.services.cache_target_final_boundary import (
    CONTRACT_VERSION,
    WRITER_REGISTRY_SHA256,
    CacheTargetBoundaryFailure,
    CacheTargetBoundaryRequest,
    _database_identity_v1,
    run_cache_target_boundary_finalize,
    run_cache_target_boundary_preflight,
)

pytestmark = pytest.mark.asyncio

CONSUMER_ID = "pinvi-cache-target-consumer"


class _SnapshotClient:
    def __init__(
        self,
        session_factory,
        *,
        corrupt_root: bool = False,
        remote_cursor: str | None = None,
    ) -> None:  # type: ignore[no-untyped-def]
        self._session_factory = session_factory
        self._corrupt_root = corrupt_root
        self._remote_cursor = remote_cursor
        self.calls = 0
        self.stream_calls = 0

    async def get_stream(self) -> CacheTargetStreamState:
        self.stream_calls += 1
        async with self._session_factory() as db:
            consumer = await db.get(KtmCacheTargetConsumer, CONSUMER_ID)
        assert consumer is not None
        assert consumer.active_restore_epoch is not None
        assert consumer.stream_control_etag is not None
        return CacheTargetStreamState(
            external_system="pinvi",
            restore_epoch=consumer.active_restore_epoch,
            control_version=consumer.active_restore_epoch,
            entity_tag=consumer.stream_control_etag,
            state="ready",
            consumer_id=CONSUMER_ID,
        )

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
            high_watermark_cursor=self._remote_cursor or consumer.remote_acked_cursor,
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

    async def get_stream(self) -> CacheTargetStreamState:
        return CacheTargetStreamState(
            external_system="pinvi",
            restore_epoch=7,
            control_version=7,
            entity_tag='"stream:7"',
            state="ready",
            consumer_id=CONSUMER_ID,
        )

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


class _StreamControlDriftClient(_SnapshotClient):
    async def get_stream(self) -> CacheTargetStreamState:
        stream = await super().get_stream()
        if self.stream_calls % 2 == 0:
            return stream.model_copy(
                update={
                    "control_version": stream.control_version + 1,
                    "entity_tag": '"stream:changed"',
                }
            )
        return stream


class _RemoteFailureClient(_SnapshotClient):
    def __init__(self, session_factory, failure: Exception) -> None:  # type: ignore[no-untyped-def]
        super().__init__(session_factory)
        self._failure = failure

    async def get_snapshot(self) -> CacheTargetSnapshot:
        raise self._failure


class _SlowSnapshotClient(_SnapshotClient):
    def __init__(self, session_factory) -> None:  # type: ignore[no-untyped-def]
        super().__init__(session_factory)
        self.snapshot_started = asyncio.Event()

    async def get_snapshot(self) -> CacheTargetSnapshot:
        self.snapshot_started.set()
        await asyncio.sleep(60)
        raise AssertionError("deadline cancellation이 slow snapshot을 중단하지 않았습니다.")


async def _seed_consumer(session_factory) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        db.add(
            KtmCacheTargetConsumer(
                consumer_id=CONSUMER_ID,
                external_system="pinvi",
                active_restore_epoch=7,
                local_applied_cursor="cursor-0",
                remote_acked_cursor="cursor-0",
                high_watermark_cursor="cursor-0",
                stream_control_etag='"stream:7"',
                reconcile_status="matched",
                feature_cache_generation=0,
                ready=True,
            )
        )
        await db.commit()


async def _seed_zero_source_initial_receipt(session_factory) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    cutover_id = uuid.uuid4()
    request_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    event_id = uuid.uuid4()
    claim_id = uuid.uuid4()
    root = cache_target_snapshot_merkle_root([])
    reconciliation_payload = {
        "actual_merkle_root": root.hex(),
        "expected_merkle_root": root.hex(),
        "request_id": str(request_id),
        "snapshot_id": str(snapshot_id),
        "status": "succeeded",
        "version": "cache-target-reconciliation-v1",
    }
    async with session_factory() as db:
        db.add(
            KtmCacheTargetConsumer(
                consumer_id=CONSUMER_ID,
                external_system="pinvi",
                active_restore_epoch=7,
                local_applied_cursor="cursor-1",
                remote_acked_cursor="cursor-1",
                high_watermark_cursor="cursor-1",
                stream_control_etag='"stream:7"',
                snapshot_id=str(snapshot_id),
                snapshot_count=0,
                snapshot_merkle_root=root,
                reconcile_status="matched",
                feature_cache_generation=0,
                ready=True,
                initial_cutover_id=cutover_id,
                initial_reconciliation_request_id=request_id,
                initial_begin_stream_etag='"stream:7"',
                initial_reconciliation_etag='"reconciliation:7"',
                initial_source_count=0,
                initial_source_merkle_root=root,
                initial_cutover_completed_at=now,
            )
        )
        db.add(
            KtmCacheTargetEvent(
                event_id=event_id,
                event_type="cache_target.reconciled",
                external_system="pinvi",
                target_key=None,
                target_id=None,
                restore_epoch=7,
                source_generation=None,
                target_sequence=None,
                relay_order=1,
                source_payload_fingerprint=root,
                payload_fingerprint=canonical_sha256(reconciliation_payload),
                occurred_at=now,
                payload=reconciliation_payload,
                applied_at=now,
            )
        )
        await db.flush()
        db.add(
            KtmCacheTargetReconciliationExpectation(
                request_id=request_id,
                external_system="pinvi",
                snapshot_id=snapshot_id,
                restore_epoch=7,
                snapshot_count=0,
                snapshot_merkle_root=root,
                high_watermark_cursor="cursor-1",
                status="received",
                receipt_event_id=event_id,
                resolved_at=now,
            )
        )
        db.add(
            KtmCacheTargetEventClaim(
                claim_id=claim_id,
                consumer_id=CONSUMER_ID,
                lease_token=uuid.uuid4(),
                lease_expires_at=now + timedelta(minutes=1),
                status="acked",
                acked_through_cursor="cursor-1",
                completed_at=now,
            )
        )
        await db.flush()
        db.add(
            KtmCacheTargetEventClaimItem(
                claim_id=claim_id,
                event_id=event_id,
                position=1,
                delivery_cursor="cursor-1",
                payload_fingerprint=canonical_sha256(reconciliation_payload),
                acked_at=now,
            )
        )
        await db.commit()


async def _boundary_request(
    session_factory,
    *,
    operation: str,
    transaction_id: uuid.UUID,
    cutover_id: uuid.UUID,
    canary_run_id: uuid.UUID | None,
    initial_writer_fence_sha256: str = "b" * 64,
) -> CacheTargetBoundaryRequest:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        database_name, system_identifier = (
            await db.execute(
                text("SELECT current_database(), (pg_control_system()).system_identifier::text")
            )
        ).one()
        consumer = await db.get(KtmCacheTargetConsumer, CONSUMER_ID)
        heads = list(await db.scalars(select(KtmCacheTargetHead)))
    if operation == "finalize":
        assert consumer is not None
        assert consumer.active_restore_epoch is not None
        assert consumer.stream_control_etag is not None
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
        map_evidence: dict[str, object] | None = {
            "contract_version": "ktm-cache-target-final-evidence/v1",
            "external_system": "pinvi",
            "stream_state": "ready",
            "consumer_id": CONSUMER_ID,
            "restore_epoch": consumer.active_restore_epoch,
            "control_version": consumer.active_restore_epoch,
            "stream_control_etag": consumer.stream_control_etag,
            "high_watermark_cursor": consumer.remote_acked_cursor,
            "snapshot_count": len(rows),
            "snapshot_merkle_root": cache_target_snapshot_merkle_root(rows).hex(),
            "reconciliation_backlog_count": 0,
            "outbox_backlog_count": 0,
            "claim_backlog_count": 0,
            "delivery_backlog_count": 0,
        }
        map_evidence_sha256: str | None = canonical_sha256(map_evidence).hex()
    else:
        map_evidence = None
        map_evidence_sha256 = None
    return CacheTargetBoundaryRequest.parse(
        {
            "contract_version": CONTRACT_VERSION,
            "operation": operation,
            "transaction_id": str(transaction_id),
            "cutover_id": str(cutover_id),
            "source_revision": "a" * 40,
            "database_identity": _database_identity_v1(
                transaction_id=transaction_id,
                database_name=database_name,
                system_identifier=system_identifier,
            ),
            "writer_registry_sha256": WRITER_REGISTRY_SHA256,
            "initial_writer_fence_sha256": initial_writer_fence_sha256,
            "final_writer_fence_sha256": "e" * 64 if operation == "finalize" else None,
            "prior_receipt_sha256": "c" * 64 if operation == "finalize" else None,
            "canary_run_id": str(canary_run_id) if canary_run_id is not None else None,
            "map_final_evidence": map_evidence,
            "map_final_evidence_sha256": map_evidence_sha256,
        }
    )


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
    restore_epoch: int = 7,
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
        head.remote_restore_epoch = restore_epoch
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
                restore_epoch=restore_epoch,
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


async def test_remote_snapshot_cursor_ahead_of_local_mirror_never_succeeds(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    run_id = uuid.uuid4()
    task = asyncio.create_task(
        run_cache_target_causal_canary(
            session_factory,
            session_factory.kw["bind"],
            consumer_client=_SnapshotClient(
                session_factory,
                remote_cursor="cursor-unconsumed-net-zero-event",
            ),  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            run_id=run_id,
            timeout_seconds=3,
            poll_seconds=0.01,
        )
    )
    await _apply_command(session_factory, "put", 1)
    await _apply_command(session_factory, "delete", 2)

    with pytest.raises(CacheTargetCanaryFailure, match="final_convergence_timeout"):
        await task
    async with session_factory() as db:
        run = await db.get(KtmCacheTargetCanaryRun, run_id)
        assert run is not None
        assert run.status == "running"
        assert run.final_remote_snapshot_high_watermark_cursor is None


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
    stream_calls_after_commit = client.stream_calls

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
    assert client.stream_calls == stream_calls_after_commit + 2
    async with session_factory() as db:
        run = await db.get(KtmCacheTargetCanaryRun, run_id)
        assert run is not None
        assert run.final_local_applied_cursor == run.final_local_remote_acked_cursor
        assert (
            run.final_local_remote_acked_cursor == run.final_remote_snapshot_high_watermark_cursor
        )
        assert run.final_local_count == run.final_remote_count
        assert run.final_local_merkle_root == run.final_remote_merkle_root
        assert (
            run.final_pending_commands,
            run.final_leased_commands,
            run.final_dead_letter_commands,
        ) == (0, 0, 0)


async def test_remote_bracket_obeys_global_deadline_and_releases_writer_lock(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    run_id, _ = await _complete_run(session_factory)
    client = _SlowSnapshotClient(session_factory)
    loop = asyncio.get_running_loop()
    started_at = loop.time()
    replay = asyncio.create_task(
        run_cache_target_causal_canary(
            session_factory,
            session_factory.kw["bind"],
            consumer_client=client,  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            run_id=run_id,
            timeout_seconds=0.3,
            poll_seconds=0.01,
        )
    )
    await asyncio.wait_for(client.snapshot_started.wait(), timeout=1)

    async def mutate_consumer() -> None:
        async with session_factory() as db:
            consumer = await db.get(KtmCacheTargetConsumer, CONSUMER_ID)
            assert consumer is not None
            consumer.feature_cache_generation += 1
            await db.commit()

    writer = asyncio.create_task(mutate_consumer())
    await asyncio.sleep(0.02)
    assert not writer.done()
    with pytest.raises(CacheTargetCanaryFailure, match="final_snapshot_unavailable"):
        await replay
    await asyncio.wait_for(writer, timeout=1)
    assert loop.time() - started_at < 1


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    (
        (
            CacheTargetServiceProblem(
                status_code=403,
                code="CACHE_TARGET_SCOPE_FORBIDDEN",
                retry_after=None,
            ),
            "final_snapshot_authorization_failed",
        ),
        (
            CacheTargetServiceProblem(
                status_code=413,
                code="SNAPSHOT_ITEM_LIMIT_EXCEEDED",
                retry_after=None,
            ),
            "final_snapshot_ceiling_exceeded",
        ),
        (
            CacheTargetServiceProblem(
                status_code=422,
                code="CACHE_TARGET_CONTRACT_INVALID",
                retry_after=None,
            ),
            "final_snapshot_service_rejected",
        ),
        (
            CacheTargetContractError("RAW-CONTRACT-SECRET"),
            "final_snapshot_invalid",
        ),
    ),
)
async def test_non_retryable_remote_failure_is_terminal_and_secret_free(
    session_factory,
    failure: Exception,
    expected_code: str,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    run_id = uuid.uuid4()
    task = asyncio.create_task(
        run_cache_target_causal_canary(
            session_factory,
            session_factory.kw["bind"],
            consumer_client=_RemoteFailureClient(session_factory, failure),  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            run_id=run_id,
            timeout_seconds=5,
            poll_seconds=0.01,
        )
    )
    await _apply_command(session_factory, "put", 1)
    await _apply_command(session_factory, "delete", 2)

    with pytest.raises(CacheTargetCanaryFailure, match=expected_code) as raised:
        await task
    assert "SECRET" not in str(raised.value)
    assert raised.value.__suppress_context__ is True
    async with session_factory() as db:
        run = await db.get(KtmCacheTargetCanaryRun, run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.terminal_error_code == expected_code


@pytest.mark.parametrize(
    "failure",
    (
        CacheTargetServiceProblem(
            status_code=503,
            code="SNAPSHOT_BUSY",
            retry_after=1,
        ),
        CacheTargetNetworkError("RAW-NETWORK-SECRET"),
    ),
)
async def test_retryable_remote_failure_preserves_running_run_until_deadline(
    session_factory,
    failure: Exception,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    run_id = uuid.uuid4()
    task = asyncio.create_task(
        run_cache_target_causal_canary(
            session_factory,
            session_factory.kw["bind"],
            consumer_client=_RemoteFailureClient(session_factory, failure),  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            run_id=run_id,
            timeout_seconds=1,
            poll_seconds=0.01,
        )
    )
    await _apply_command(session_factory, "put", 1)
    await _apply_command(session_factory, "delete", 2)

    with pytest.raises(CacheTargetCanaryFailure, match="final_convergence_timeout") as raised:
        await task
    assert "SECRET" not in str(raised.value)
    async with session_factory() as db:
        run = await db.get(KtmCacheTargetCanaryRun, run_id)
        assert run is not None
        assert run.status == "running"
        assert run.terminal_error_code is None


async def test_final_boundary_appends_exact_audit_and_replays_only_exact_evidence(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_zero_source_initial_receipt(session_factory)
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
    await _apply_command(session_factory, "put", 2)
    await _apply_command(session_factory, "delete", 3)
    await task
    transaction_id = uuid.uuid4()
    cutover_id = uuid.uuid4()
    request = await _boundary_request(
        session_factory,
        operation="finalize",
        transaction_id=transaction_id,
        cutover_id=cutover_id,
        canary_run_id=run_id,
    )

    first, second = await asyncio.gather(
        run_cache_target_boundary_finalize(
            session_factory,
            request=request,
            runtime_source_revision="a" * 40,
            consumer_id=CONSUMER_ID,
        ),
        run_cache_target_boundary_finalize(
            session_factory,
            request=request,
            runtime_source_revision="a" * 40,
            consumer_id=CONSUMER_ID,
        ),
    )

    assert first == second
    assert first["operation"] == "finalize"
    assert first["expected_initial_command_count"] == 0
    assert first["expected_initial_event_count"] == 1
    assert first["expected_initial_claim_item_count"] == 1
    assert first["expected_synthetic_command_count"] == 2
    assert first["expected_synthetic_event_count"] == 2
    assert first["expected_synthetic_claim_count"] == 2
    assert first["unexpected_non_synthetic_event_count"] == 0
    assert first["database_in_flight_transaction_count"] == 0
    assert first["audit_id"] == str(transaction_id)
    assert first["audit_request_sha256"] == canonical_sha256(request.json_object()).hex()
    assert first["audit_row_count"] == 1
    async with session_factory() as db:
        audit = await db.get(KtmCacheTargetBoundaryAudit, transaction_id)
        assert audit is not None
        assert audit.audit_request_sha256.hex() == first["audit_request_sha256"]
        assert audit.evidence_sha256.hex() == first["evidence_sha256"]

    # 같은 application_name만으로는 외부 transaction을 replay 대기자로 취급할 수 없다.
    async with session_factory() as held:
        await held.execute(text("SET LOCAL application_name = 'pinvi-cache-target-final-boundary'"))
        await held.execute(text("SELECT 1"))
        with pytest.raises(CacheTargetBoundaryFailure, match="database_not_quiescent"):
            await run_cache_target_boundary_finalize(
                session_factory,
                request=request,
                runtime_source_revision="a" * 40,
                consumer_id=CONSUMER_ID,
            )

    mismatched = await _boundary_request(
        session_factory,
        operation="finalize",
        transaction_id=transaction_id,
        cutover_id=cutover_id,
        canary_run_id=run_id,
        initial_writer_fence_sha256="d" * 64,
    )
    with pytest.raises(CacheTargetBoundaryFailure, match="boundary_replay_conflict"):
        await run_cache_target_boundary_finalize(
            session_factory,
            request=mismatched,
            runtime_source_revision="a" * 40,
            consumer_id=CONSUMER_ID,
        )


async def test_boundary_preflight_is_read_only_and_requires_empty_0047_material(
    session_factory,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    request = await _boundary_request(
        session_factory,
        operation="preflight",
        transaction_id=uuid.uuid4(),
        cutover_id=uuid.uuid4(),
        canary_run_id=None,
    )

    async def schema_0047(_db) -> str:  # type: ignore[no-untyped-def]
        return "20260801_0047"

    monkeypatch.setattr(boundary_service, "_schema_revision", schema_0047)
    receipt = await run_cache_target_boundary_preflight(
        session_factory,
        request=request,
        runtime_source_revision="a" * 40,
    )
    assert receipt["operation"] == "preflight"
    assert receipt["audit_id"] is None
    assert receipt["audit_request_sha256"] is None
    assert receipt["audit_row_count"] == 0
    assert receipt["canary_run_id"] is None
    assert receipt["initial_evidence_sha256"] is None
    assert receipt["canary_provenance_sha256"] is None
    assert receipt["final_local_remote_evidence_sha256"] is None
    assert receipt["runtime_mutation_count"] == 0
    assert receipt["external_mutation_count"] == 0

    async with session_factory() as db:
        db.add(
            KtmCacheTargetConsumer(
                consumer_id=CONSUMER_ID,
                external_system="pinvi",
                reconcile_status="uninitialized",
                feature_cache_generation=0,
                ready=False,
            )
        )
        await db.commit()
    with pytest.raises(CacheTargetBoundaryFailure, match="preflight_material_not_empty"):
        await run_cache_target_boundary_preflight(
            session_factory,
            request=request,
            runtime_source_revision="a" * 40,
        )


async def test_boundary_preflight_rejects_another_boundary_named_transaction(
    session_factory,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    request = await _boundary_request(
        session_factory,
        operation="preflight",
        transaction_id=uuid.uuid4(),
        cutover_id=uuid.uuid4(),
        canary_run_id=None,
    )

    async def schema_0047(_db) -> str:  # type: ignore[no-untyped-def]
        return "20260801_0047"

    monkeypatch.setattr(boundary_service, "_schema_revision", schema_0047)
    async with session_factory() as held:
        await held.execute(text("SET LOCAL application_name = 'pinvi-cache-target-final-boundary'"))
        await held.execute(text("SELECT 1"))
        with pytest.raises(CacheTargetBoundaryFailure, match="database_not_quiescent"):
            await run_cache_target_boundary_preflight(
                session_factory,
                request=request,
                runtime_source_revision="a" * 40,
            )

    receipt = await run_cache_target_boundary_preflight(
        session_factory,
        request=request,
        runtime_source_revision="a" * 40,
    )
    assert receipt["database_in_flight_transaction_count"] == 0


@pytest.mark.parametrize("statement", ["UPDATE", "DELETE", "TRUNCATE"])
async def test_final_boundary_audit_rejects_all_mutation(
    session_factory,
    statement: str,
) -> None:  # type: ignore[no-untyped-def]
    await test_final_boundary_appends_exact_audit_and_replays_only_exact_evidence(session_factory)
    async with session_factory() as db:
        sql = {
            "UPDATE": (
                "UPDATE app.ktm_cache_target_boundary_audits "
                "SET initial_writer_fence_sha256 = decode(repeat('ee', 32), 'hex')"
            ),
            "DELETE": "DELETE FROM app.ktm_cache_target_boundary_audits",
            "TRUNCATE": "TRUNCATE app.ktm_cache_target_boundary_audits",
        }[statement]
        with pytest.raises(DBAPIError, match="append-only"):
            await db.execute(text(sql))


async def test_database_rejects_success_evidence_divergence(session_factory) -> None:  # type: ignore[no-untyped-def]
    run_id, _ = await _complete_run(session_factory)
    async with session_factory() as db:
        run = await db.get(KtmCacheTargetCanaryRun, run_id)
        assert run is not None
        assert run.final_remote_count is not None
        run.final_remote_count += 1
        with pytest.raises(IntegrityError, match="ck_ktm_ct_canary_final_material"):
            await db.commit()


async def test_raw_succeeded_row_rejects_every_single_null_material_mutation(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    run_id, _ = await _complete_run(session_factory)
    nullable_success_material = (
        "put_event_id",
        "put_claim_id",
        "put_relay_order",
        "put_cache_generation",
        "put_cursor",
        "put_event_payload_fingerprint",
        "put_claim_status",
        "put_acked_at",
        "put_claim_completed_at",
        "delete_command_id",
        "delete_event_id",
        "delete_claim_id",
        "delete_relay_order",
        "delete_cursor",
        "delete_event_payload_fingerprint",
        "delete_claim_status",
        "delete_acked_at",
        "delete_claim_completed_at",
        "final_cache_generation",
        "final_restore_epoch",
        "final_stream_control_version",
        "final_stream_control_etag",
        "final_local_applied_cursor",
        "final_local_remote_acked_cursor",
        "final_remote_snapshot_high_watermark_cursor",
        "final_local_count",
        "final_remote_count",
        "final_local_merkle_root",
        "final_remote_merkle_root",
        "final_pending_commands",
        "final_leased_commands",
        "final_dead_letter_commands",
        "completed_at",
    )
    async with session_factory() as db:
        await db.execute(
            text(
                "CREATE TEMP TABLE canary_null_probe "
                "(LIKE app.ktm_cache_target_canary_runs INCLUDING CONSTRAINTS) "
                "ON COMMIT DROP"
            )
        )
        await db.execute(
            text(
                "INSERT INTO canary_null_probe "
                "SELECT * FROM app.ktm_cache_target_canary_runs WHERE run_id = :run_id"
            ),
            {"run_id": run_id},
        )
        for column in nullable_success_material:
            savepoint = await db.begin_nested()
            with pytest.raises(IntegrityError):
                await db.execute(
                    text(
                        f"UPDATE canary_null_probe SET {column} = NULL"  # noqa: S608 - 고정 allowlist
                    )
                )
            await savepoint.rollback()


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
        "remote-cursor",
        "stream-control",
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
        elif drift == "remote-cursor":
            replay_client = _SnapshotClient(session_factory, remote_cursor="cursor-ahead")
        elif drift == "stream-control":
            replay_client = _StreamControlDriftClient(session_factory)
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
            event.payload = {
                **event.payload,
                "target": {**event.payload["target"], "radius_m": 9999},
            }
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


async def test_same_invocation_rejects_cross_epoch_put_delete_chain(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    run_id = uuid.uuid4()
    task = asyncio.create_task(
        run_cache_target_causal_canary(
            session_factory,
            session_factory.kw["bind"],
            consumer_client=_SnapshotClient(session_factory),  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            run_id=run_id,
            timeout_seconds=5,
            poll_seconds=0.01,
        )
    )
    await _apply_command(session_factory, "put", 1, restore_epoch=7)
    await _wait_for_command(session_factory, "delete")
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, CONSUMER_ID)
        assert consumer is not None
        consumer.active_restore_epoch = 8
        consumer.stream_control_etag = '"stream:8"'
        await db.commit()
    await _apply_command(session_factory, "delete", 2, restore_epoch=8)

    with pytest.raises(CacheTargetCanaryFailure, match="event_provenance_mismatch"):
        await task
    async with session_factory() as db:
        run = await db.get(KtmCacheTargetCanaryRun, run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.terminal_error_code == "event_provenance_mismatch"


@pytest.mark.parametrize("corruption", ("command", "event"))
async def test_same_invocation_fresh_finalization_rejects_post_observation_drift(
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    run_id = uuid.uuid4()
    original = canary_service._record_observation

    async def record_then_corrupt(*args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        await original(*args, **kwargs)
        if kwargs["operation"] != "delete":
            return
        async with session_factory() as db:
            run = await db.get(KtmCacheTargetCanaryRun, run_id)
            assert run is not None
            if corruption == "command":
                command = await db.get(KtmCacheTargetCommand, run.put_command_id)
                assert command is not None
                command.payload = {"version": "post-observation-drift"}
            else:
                assert run.put_event_id is not None
                event = await db.get(KtmCacheTargetEvent, run.put_event_id)
                assert event is not None
                event.payload = {
                    **event.payload,
                    "target": {
                        **event.payload["target"],
                        "radius_m": 9999,
                    },
                }
            await db.commit()

    monkeypatch.setattr(canary_service, "_record_observation", record_then_corrupt)
    task = asyncio.create_task(
        run_cache_target_causal_canary(
            session_factory,
            session_factory.kw["bind"],
            consumer_client=_SnapshotClient(session_factory),  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            run_id=run_id,
            timeout_seconds=5,
            poll_seconds=0.01,
        )
    )
    await _apply_command(session_factory, "put", 1)
    await _apply_command(session_factory, "delete", 2)

    expected = (
        "command_identity_mismatch" if corruption == "command" else "event_provenance_mismatch"
    )
    with pytest.raises(CacheTargetCanaryFailure, match=expected):
        await task


@pytest.mark.parametrize(
    "field",
    ("status", "acked_through_cursor", "completed_at"),
)
async def test_database_prevents_post_observation_claim_terminal_mutation(
    session_factory,
    field: str,
) -> None:  # type: ignore[no-untyped-def]
    run_id, _ = await _complete_run(session_factory)
    async with session_factory() as db:
        run = await db.get(KtmCacheTargetCanaryRun, run_id)
        assert run is not None
        assert run.put_claim_id is not None
        claim = await db.get(KtmCacheTargetEventClaim, run.put_claim_id)
        assert claim is not None
        if field == "status":
            claim.status = "invalidated"
        elif field == "acked_through_cursor":
            claim.acked_through_cursor = "cursor-drift"
        elif field == "completed_at":
            claim.completed_at = datetime.now(UTC) + timedelta(seconds=1)
        else:
            raise AssertionError(field)
        with pytest.raises(IntegrityError, match="fk_ktm_ct_canary_put_claim_terminal"):
            await db.commit()
