"""최초 0→N backfill의 writer fence·begin·drain·seal·completion 상태기계."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.clients.kor_travel_map_cache_target import (
    CacheTargetMutationResult,
    CacheTargetPreparingReconciliation,
    CacheTargetRecoveryOperation,
    CacheTargetRecoveryResult,
    CacheTargetRunningReconciliation,
    CacheTargetStateResult,
    CacheTargetStreamState,
)
from app.core.cache_target_contract import CacheTargetMerkleRow, cache_target_snapshot_merkle_root
from app.models.cache_target_sync import (
    KtmCacheTargetCommand,
    KtmCacheTargetConsumer,
    KtmCacheTargetEvent,
    KtmCacheTargetHead,
    KtmCacheTargetReconciliationExpectation,
)
from app.services.cache_target_event_consumer import (
    CacheTargetClaim,
    CacheTargetEventRecord,
    CacheTargetSnapshot,
    apply_cache_target_claim,
    mark_cache_target_acknowledged,
)
from app.services.cache_target_initial_cutover import (
    CacheTargetSourceIdentity,
    _finish_remote_completed_cutover,
    run_initial_cache_target_cutover,
)

pytestmark = pytest.mark.asyncio


class _CutoverStub:
    def __init__(
        self,
        *,
        target_key: str,
        merkle_root: str,
        preserve_completed_begin_replay: bool = False,
    ) -> None:
        self.phase = "initial"
        self.request_id = uuid.uuid4()
        self.snapshot_id = uuid.uuid4()
        self.target_id = uuid.uuid4()
        self.target_key = target_key
        self.merkle_root = merkle_root
        self.puts = 0
        self.preserve_completed_begin_replay = preserve_completed_begin_replay

    async def get_stream(self) -> CacheTargetStreamState:
        active: CacheTargetPreparingReconciliation | CacheTargetRunningReconciliation | None
        if self.phase == "preparing":
            active = CacheTargetPreparingReconciliation(
                request_id=self.request_id,
                status="preparing",
                restore_epoch=7,
                entity_tag=f'"{self.request_id}:1"',
                stream_entity_tag='"pinvi:2"',
                created_at=datetime.now(UTC),
            )
            state = "fenced"
            etag = '"pinvi:2"'
        elif self.phase == "running":
            active = CacheTargetRunningReconciliation(
                request_id=self.request_id,
                status="running",
                snapshot_id=self.snapshot_id,
                restore_epoch=7,
                count=1,
                merkle_root=self.merkle_root,
                high_watermark_cursor="cursor-1",
                entity_tag=f'"{self.request_id}:2"',
                stream_entity_tag='"pinvi:3"',
                created_at=datetime.now(UTC),
            )
            state = "fenced"
            etag = '"pinvi:3"'
        else:
            active = None
            state = "ready"
            etag = '"pinvi:4"' if self.phase == "completed" else '"pinvi:1"'
        return CacheTargetStreamState(
            external_system="pinvi",
            restore_epoch=7,
            control_version=int(etag[-2]),
            entity_tag=etag,
            state=state,
            consumer_id="pinvi-cache-target-consumer",
            active_reconciliation=active,
        )

    async def begin_initial_reconciliation(self, **kwargs: object) -> CacheTargetRecoveryResult:
        assert kwargs["stream_etag"] == '"pinvi:1"'
        if not (self.preserve_completed_begin_replay and self.phase == "completed"):
            self.phase = "preparing"
        return CacheTargetRecoveryResult(
            operation=CacheTargetRecoveryOperation(
                operation_id=self.request_id,
                status="preparing",
                status_url=None,
                entity_tag=f'"{self.request_id}:1"',
                stream_entity_tag='"pinvi:2"',
            ),
            etag=f'"{self.request_id}:1"',
        )

    async def put_target(self, **kwargs: object) -> CacheTargetMutationResult:
        self.puts += 1
        return CacheTargetMutationResult(
            status_code=201,
            data=CacheTargetStateResult(
                external_system="pinvi",
                target_key=self.target_key,
                state="active",
                restore_epoch=7,
                source_generation=1,
                source_payload_fingerprint="73" * 32,
                entity_tag=f'"{self.target_id}:1"',
                target_id=self.target_id,
                target_sequence=1,
            ),
            etag=f'"{self.target_id}:1"',
        )

    async def seal_initial_reconciliation(self, **kwargs: object) -> CacheTargetRecoveryResult:
        assert kwargs["expected_item_count"] == 1
        assert kwargs["expected_merkle_root"] == self.merkle_root
        assert kwargs["stream_etag"] == f'"{self.request_id}:1"'
        self.phase = "running"
        return CacheTargetRecoveryResult(
            operation=CacheTargetRecoveryOperation(
                operation_id=self.request_id,
                status="running",
                snapshot_id=self.snapshot_id,
                status_url=None,
                entity_tag=f'"{self.request_id}:2"',
                stream_entity_tag='"pinvi:3"',
            ),
            etag=f'"{self.request_id}:2"',
        )

    async def get_reconciliation_snapshot(self, request_id: uuid.UUID) -> CacheTargetSnapshot:
        assert request_id == self.request_id
        return CacheTargetSnapshot(
            snapshot_id=str(self.snapshot_id),
            restore_epoch=7,
            high_watermark_cursor="cursor-1",
            count=1,
            merkle_root=self.merkle_root,
            created_at=datetime(2026, 8, 1, tzinfo=UTC),
            expires_at=datetime(2026, 8, 1, tzinfo=UTC) + timedelta(hours=2),
            items=[
                {
                    "external_system": "pinvi",
                    "target_key": self.target_key,
                    "state": "active",
                    "source_generation": 1,
                    "source_payload_fingerprint": "73" * 32,
                }
            ],
        )

    async def complete_reconciliation(self, **kwargs: object) -> CacheTargetRecoveryOperation:
        self.phase = "completed"
        return CacheTargetRecoveryOperation(
            operation_id=self.request_id,
            status="succeeded",
            snapshot_id=self.snapshot_id,
            status_url=None,
        )


def _one_target_source_identity(poi_id: uuid.UUID) -> tuple[bytes, str]:
    fingerprint = bytes.fromhex("73" * 32)
    merkle_root = cache_target_snapshot_merkle_root(
        [
            CacheTargetMerkleRow(
                external_system="pinvi",
                target_key=str(poi_id),
                state="active",
                source_generation=1,
                source_payload_fingerprint=fingerprint,
            )
        ]
    ).hex()
    return fingerprint, merkle_root


async def _seed_remote_completed_local_state(
    session_factory,
    *,
    cutover_id: uuid.UUID,
    request_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    merkle_root: str,
    poi_id: uuid.UUID | None = None,
    fingerprint: bytes | None = None,
    ready: bool = False,
) -> None:  # type: ignore[no-untyped-def]
    if (poi_id is None) != (fingerprint is None):
        raise ValueError("source head identity는 poi_id와 fingerprint를 함께 지정해야 합니다.")
    async with session_factory() as db:
        if poi_id is not None and fingerprint is not None:
            db.add(
                KtmCacheTargetHead(
                    poi_id=poi_id,
                    external_system="pinvi",
                    target_key=str(poi_id),
                    desired_state="active",
                    source_generation=1,
                    source_payload_fingerprint=fingerprint,
                    lon="126",
                    lat="37",
                    radius_km="5",
                    update_enabled=True,
                )
            )
        db.add(
            KtmCacheTargetConsumer(
                consumer_id="pinvi-cache-target-consumer",
                external_system="pinvi",
                active_restore_epoch=7,
                stream_control_etag='"pinvi:3"',
                snapshot_id=str(snapshot_id),
                snapshot_count=1,
                snapshot_merkle_root=bytes.fromhex(merkle_root),
                high_watermark_cursor="cursor-1",
                reconcile_status="matched",
                ready=ready,
                initial_cutover_id=cutover_id,
                initial_reconciliation_request_id=request_id,
                initial_begin_stream_etag='"pinvi:1"',
                initial_reconciliation_etag=f'"{request_id}:2"',
                initial_source_count=1,
                initial_source_merkle_root=bytes.fromhex(merkle_root),
            )
        )
        await db.commit()


async def _seed_reconciliation_expectation(
    session_factory,
    *,
    request_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    merkle_root: str,
    high_watermark_cursor: str = "cursor-1",
    received: bool = False,
    create_expectation: bool = True,
    relay_order: int = 1,
    applied: bool = True,
) -> CacheTargetEventRecord | None:  # type: ignore[no-untyped-def]
    resolved_at = datetime.now(UTC)
    event = (
        _reconciled_event(
            event_id=uuid.uuid4(),
            request_id=request_id,
            snapshot_id=snapshot_id,
            merkle_root=merkle_root,
            relay_order=relay_order,
            occurred_at=resolved_at,
        )
        if received or not create_expectation
        else None
    )
    async with session_factory() as db:
        if event is not None:
            db.add(
                KtmCacheTargetEvent(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    external_system=event.external_system,
                    restore_epoch=event.restore_epoch,
                    relay_order=event.relay_order,
                    source_payload_fingerprint=bytes.fromhex(event.source_payload_fingerprint),
                    payload_fingerprint=bytes.fromhex(event.payload_fingerprint),
                    occurred_at=event.occurred_at,
                    payload=event.payload,
                    applied_at=resolved_at if applied else None,
                )
            )
        if create_expectation:
            db.add(
                KtmCacheTargetReconciliationExpectation(
                    request_id=request_id,
                    external_system="pinvi",
                    snapshot_id=snapshot_id,
                    restore_epoch=7,
                    snapshot_count=1,
                    snapshot_merkle_root=bytes.fromhex(merkle_root),
                    high_watermark_cursor=high_watermark_cursor,
                    status="received" if received else "pending",
                    receipt_event_id=event.event_id if received and event is not None else None,
                    resolved_at=resolved_at if received else None,
                )
            )
        await db.commit()
    return event


def _reconciled_event(
    *,
    event_id: uuid.UUID,
    request_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    merkle_root: str,
    relay_order: int,
    occurred_at: datetime,
) -> CacheTargetEventRecord:
    return CacheTargetEventRecord.model_validate(
        {
            "event_id": str(event_id),
            "event_type": "cache_target.reconciled",
            "event_scope": "stream",
            "external_system": "pinvi",
            "target_key": None,
            "target_id": None,
            "restore_epoch": 7,
            "source_generation": None,
            "target_sequence": None,
            "relay_order": relay_order,
            "cursor": f"cursor-{relay_order}",
            "source_payload_fingerprint": merkle_root,
            "payload_fingerprint": "74" * 32,
            "payload": {
                "actual_merkle_root": merkle_root,
                "expected_merkle_root": merkle_root,
                "request_id": str(request_id),
                "snapshot_id": str(snapshot_id),
                "status": "succeeded",
                "version": "cache-target-reconciliation-v1",
            },
            "occurred_at": occurred_at.isoformat(),
        }
    )


def _claim(event: CacheTargetEventRecord, *, cursor: str | None = None) -> CacheTargetClaim:
    material = event.model_dump(mode="json")
    material["cursor"] = cursor or event.cursor
    return CacheTargetClaim.model_validate(
        {
            "claim_id": str(uuid.uuid4()),
            "external_system": "pinvi",
            "consumer_id": "pinvi-cache-target-consumer",
            "lease_token": str(uuid.uuid4()),
            "status": "active",
            "first_relay_order": event.relay_order,
            "last_relay_order": event.relay_order,
            "acked_through": None,
            "lease_expires_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
            "events": [material],
            "idempotent_replay": False,
        }
    )


async def _seed_remote_completion_case(
    session_factory,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, str]:  # type: ignore[no-untyped-def]
    request_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    cutover_id = uuid.uuid4()
    root = "73" * 32
    await _seed_remote_completed_local_state(
        session_factory,
        cutover_id=cutover_id,
        request_id=request_id,
        snapshot_id=snapshot_id,
        merkle_root=root,
    )
    return request_id, snapshot_id, cutover_id, root


async def _finish_remote_completion_case(
    session_factory,
    *,
    request_id: uuid.UUID,
    cutover_id: uuid.UUID,
    root: str,
) -> None:  # type: ignore[no-untyped-def]
    await _finish_remote_completed_cutover(
        session_factory,
        consumer_id="pinvi-cache-target-consumer",
        cutover_id=cutover_id,
        request_id=request_id,
        expected_restore_epoch=7,
        source=CacheTargetSourceIdentity(count=1, merkle_root=root),
        stream_entity_tag='"pinvi:4"',
    )


async def test_initial_cutover_closes_zero_to_nonempty_bootstrap_and_is_durable(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    poi_id = uuid.uuid4()
    fingerprint = bytes.fromhex("73" * 32)
    async with session_factory() as db:
        db.add(
            KtmCacheTargetHead(
                poi_id=poi_id,
                external_system="pinvi",
                target_key=str(poi_id),
                desired_state="active",
                source_generation=1,
                source_payload_fingerprint=fingerprint,
                lon="126",
                lat="37",
                radius_km="5",
                update_enabled=True,
            )
        )
        await db.flush()
        db.add(
            KtmCacheTargetCommand(
                command_id=uuid.uuid4(),
                poi_id=poi_id,
                operation="put",
                source_generation=1,
                payload={
                    "version": "cache-target-source-v1",
                    "state": "active",
                    "coord": {"lon_e6": 126000000, "lat_e6": 37000000},
                    "radius_m": 5000,
                    "update_enabled": True,
                },
                payload_fingerprint=fingerprint,
                status="pending",
            )
        )
        await db.commit()
    merkle_root = cache_target_snapshot_merkle_root(
        [
            CacheTargetMerkleRow(
                external_system="pinvi",
                target_key=str(poi_id),
                state="active",
                source_generation=1,
                source_payload_fingerprint=fingerprint,
            )
        ]
    ).hex()
    stub = _CutoverStub(target_key=str(poi_id), merkle_root=merkle_root)
    cutover_id = uuid.uuid4()
    result = await run_initial_cache_target_cutover(
        session_factory,
        session_factory.kw["bind"],
        command_client=stub,  # type: ignore[arg-type]
        consumer_client=stub,  # type: ignore[arg-type]
        recovery_client=stub,  # type: ignore[arg-type]
        consumer_id="pinvi-cache-target-consumer",
        cutover_id=cutover_id,
        expected_restore_epoch=7,
        reason="initial backfill",
        batch_size=100,
        lease_seconds=60,
        max_attempts=5,
    )

    assert result.source.count == 1
    assert result.published == 1
    assert stub.puts == 1
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        command = await db.scalar(select(KtmCacheTargetCommand))
        assert consumer is not None
        assert consumer.ready is True
        assert consumer.initial_cutover_id == cutover_id
        assert consumer.initial_reconciliation_request_id == stub.request_id
        assert consumer.initial_cutover_completed_at is not None
        assert command is not None and command.status == "succeeded"

    resumed = await run_initial_cache_target_cutover(
        session_factory,
        session_factory.kw["bind"],
        command_client=stub,  # type: ignore[arg-type]
        consumer_client=stub,  # type: ignore[arg-type]
        recovery_client=stub,  # type: ignore[arg-type]
        consumer_id="pinvi-cache-target-consumer",
        cutover_id=cutover_id,
        expected_restore_epoch=7,
        reason="initial backfill",
        batch_size=100,
        lease_seconds=60,
        max_attempts=5,
    )
    assert resumed.published == 0
    assert stub.puts == 1


async def test_initial_cutover_recovers_ready_commit_after_remote_completion(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    poi_id = uuid.uuid4()
    fingerprint, merkle_root = _one_target_source_identity(poi_id)
    cutover_id = uuid.uuid4()
    stub = _CutoverStub(
        target_key=str(poi_id),
        merkle_root=merkle_root,
        preserve_completed_begin_replay=True,
    )
    stub.phase = "completed"
    await _seed_remote_completed_local_state(
        session_factory,
        cutover_id=cutover_id,
        request_id=stub.request_id,
        snapshot_id=stub.snapshot_id,
        merkle_root=merkle_root,
        poi_id=poi_id,
        fingerprint=fingerprint,
    )
    await _seed_reconciliation_expectation(
        session_factory,
        request_id=stub.request_id,
        snapshot_id=stub.snapshot_id,
        merkle_root=merkle_root,
    )

    result = await run_initial_cache_target_cutover(
        session_factory,
        session_factory.kw["bind"],
        command_client=stub,  # type: ignore[arg-type]
        consumer_client=stub,  # type: ignore[arg-type]
        recovery_client=stub,  # type: ignore[arg-type]
        consumer_id="pinvi-cache-target-consumer",
        cutover_id=cutover_id,
        expected_restore_epoch=7,
        reason="initial backfill",
        batch_size=100,
        lease_seconds=60,
        max_attempts=5,
    )

    assert result.published == 0
    assert stub.puts == 0
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        assert consumer.ready is True
        assert consumer.stream_control_etag == '"pinvi:4"'
        assert consumer.initial_cutover_completed_at is not None


@pytest.mark.parametrize(
    ("received", "high_watermark_cursor", "succeeds"),
    [
        pytest.param(True, "cursor-1", True, id="received-exact-inbox"),
        pytest.param(False, "other-cursor", False, id="pending-mismatch"),
    ],
)
async def test_remote_completed_cutover_validates_existing_expectation(
    session_factory,
    received: bool,
    high_watermark_cursor: str,
    succeeds: bool,
) -> None:  # type: ignore[no-untyped-def]
    request_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    cutover_id = uuid.uuid4()
    root = "73" * 32
    await _seed_remote_completed_local_state(
        session_factory,
        cutover_id=cutover_id,
        request_id=request_id,
        snapshot_id=snapshot_id,
        merkle_root=root,
        ready=received,
    )
    await _seed_reconciliation_expectation(
        session_factory,
        request_id=request_id,
        snapshot_id=snapshot_id,
        merkle_root=root,
        high_watermark_cursor=high_watermark_cursor,
        received=received,
    )

    if succeeds:
        await _finish_remote_completed_cutover(
            session_factory,
            consumer_id="pinvi-cache-target-consumer",
            cutover_id=cutover_id,
            request_id=request_id,
            expected_restore_epoch=7,
            source=CacheTargetSourceIdentity(count=1, merkle_root=root),
            stream_entity_tag='"pinvi:4"',
        )
    else:
        with pytest.raises(RuntimeError, match="durable expectation"):
            await _finish_remote_completed_cutover(
                session_factory,
                consumer_id="pinvi-cache-target-consumer",
                cutover_id=cutover_id,
                request_id=request_id,
                expected_restore_epoch=7,
                source=CacheTargetSourceIdentity(count=1, merkle_root=root),
                stream_entity_tag='"pinvi:4"',
            )

    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        assert consumer.ready is succeeds
        assert consumer.stream_control_etag == ('"pinvi:4"' if succeeds else '"pinvi:3"')
        assert (consumer.initial_cutover_completed_at is not None) is succeeds


async def test_initial_cutover_remote_completion_reconstructs_missing_expectation(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    poi_id = uuid.uuid4()
    fingerprint, merkle_root = _one_target_source_identity(poi_id)
    cutover_id = uuid.uuid4()
    stub = _CutoverStub(
        target_key=str(poi_id),
        merkle_root=merkle_root,
        preserve_completed_begin_replay=True,
    )
    stub.phase = "completed"
    await _seed_remote_completed_local_state(
        session_factory,
        cutover_id=cutover_id,
        request_id=stub.request_id,
        snapshot_id=stub.snapshot_id,
        merkle_root=merkle_root,
        poi_id=poi_id,
        fingerprint=fingerprint,
    )

    result = await run_initial_cache_target_cutover(
        session_factory,
        session_factory.kw["bind"],
        command_client=stub,  # type: ignore[arg-type]
        consumer_client=stub,  # type: ignore[arg-type]
        recovery_client=stub,  # type: ignore[arg-type]
        consumer_id="pinvi-cache-target-consumer",
        cutover_id=cutover_id,
        expected_restore_epoch=7,
        reason="initial backfill",
        batch_size=100,
        lease_seconds=60,
        max_attempts=5,
    )

    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        expectation = await db.get(
            KtmCacheTargetReconciliationExpectation,
            stub.request_id,
        )
        assert consumer is not None
        assert consumer.ready is True
        assert consumer.stream_control_etag == '"pinvi:4"'
        assert consumer.initial_cutover_completed_at is not None
        assert expectation is not None
        assert expectation.snapshot_id == stub.snapshot_id
        assert expectation.restore_epoch == 7
        assert expectation.snapshot_count == 1
        assert expectation.snapshot_merkle_root == bytes.fromhex(merkle_root)
        assert expectation.high_watermark_cursor == "cursor-1"
        assert expectation.status == "pending"
    assert result.published == 0


async def test_remote_completion_recovers_applied_inbox_as_received_and_redelivery_is_noop(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    request_id, snapshot_id, cutover_id, root = await _seed_remote_completion_case(session_factory)
    event = await _seed_reconciliation_expectation(
        session_factory,
        request_id=request_id,
        snapshot_id=snapshot_id,
        merkle_root=root,
        create_expectation=False,
    )
    assert event is not None

    await _finish_remote_completion_case(
        session_factory,
        cutover_id=cutover_id,
        request_id=request_id,
        root=root,
    )

    async with session_factory() as db:
        expectation = await db.get(KtmCacheTargetReconciliationExpectation, request_id)
        assert expectation is not None
        assert expectation.status == "received"
        assert expectation.receipt_event_id == event.event_id
        assert expectation.resolved_at is not None

    redelivery = _claim(event, cursor="cursor-redelivery")
    async with session_factory() as db:
        ack = await apply_cache_target_claim(db, redelivery)
        await db.commit()
    async with session_factory() as db:
        await mark_cache_target_acknowledged(db, ack)
        await db.commit()

    async with session_factory() as db:
        expectation = await db.get(KtmCacheTargetReconciliationExpectation, request_id)
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert expectation is not None
        assert expectation.status == "received"
        assert expectation.receipt_event_id == event.event_id
        assert consumer is not None
        assert consumer.ready is True
        assert await db.scalar(select(func.count()).select_from(KtmCacheTargetEvent)) == 1


@pytest.mark.parametrize(
    "candidate_state",
    [
        pytest.param("snapshot_mismatch", id="snapshot-mismatch"),
        pytest.param("unapplied", id="unapplied-partial"),
        pytest.param("multiple", id="multiple"),
    ],
)
async def test_remote_completion_rejects_non_exact_applied_inbox_candidates(
    session_factory,
    candidate_state: str,
) -> None:  # type: ignore[no-untyped-def]
    request_id, snapshot_id, cutover_id, root = await _seed_remote_completion_case(session_factory)
    candidate_count = 2 if candidate_state == "multiple" else 1
    for relay_order in range(1, candidate_count + 1):
        event = await _seed_reconciliation_expectation(
            session_factory,
            request_id=request_id,
            snapshot_id=(uuid.uuid4() if candidate_state == "snapshot_mismatch" else snapshot_id),
            merkle_root=root,
            create_expectation=False,
            relay_order=relay_order,
            applied=candidate_state != "unapplied",
        )
        assert event is not None

    with pytest.raises(RuntimeError, match="applied inbox receipt"):
        await _finish_remote_completion_case(
            session_factory,
            cutover_id=cutover_id,
            request_id=request_id,
            root=root,
        )

    async with session_factory() as db:
        expectation = await db.get(KtmCacheTargetReconciliationExpectation, request_id)
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert expectation is None
        assert consumer is not None
        assert consumer.ready is False
        assert consumer.stream_control_etag == '"pinvi:3"'
