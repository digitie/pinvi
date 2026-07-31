"""최초 0→N backfill의 writer fence·begin·drain·seal·completion 상태기계."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

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
    KtmCacheTargetHead,
)
from app.services.cache_target_event_consumer import CacheTargetSnapshot
from app.services.cache_target_initial_cutover import run_initial_cache_target_cutover

pytestmark = pytest.mark.asyncio


class _CutoverStub:
    def __init__(self, *, target_key: str, merkle_root: str) -> None:
        self.phase = "initial"
        self.request_id = uuid.uuid4()
        self.snapshot_id = uuid.uuid4()
        self.target_id = uuid.uuid4()
        self.target_key = target_key
        self.merkle_root = merkle_root
        self.puts = 0

    async def get_stream(self) -> CacheTargetStreamState:
        active: CacheTargetPreparingReconciliation | CacheTargetRunningReconciliation | None
        if self.phase == "preparing":
            active = CacheTargetPreparingReconciliation(
                request_id=self.request_id,
                status="preparing",
                restore_epoch=7,
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
        self.phase = "preparing"
        return CacheTargetRecoveryResult(
            operation=CacheTargetRecoveryOperation(
                operation_id=self.request_id,
                status="preparing",
                status_url=None,
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
                status_url=None,
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
            status_url=None,
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
