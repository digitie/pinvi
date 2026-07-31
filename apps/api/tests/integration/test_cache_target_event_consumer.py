"""Map cache-target claim의 commit-before-ACK와 epoch/checksum 격리."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.cache_target_contract import (
    CacheTargetMerkleRow,
    cache_target_snapshot_merkle_root,
)
from app.models.cache_target_sync import (
    KtmCacheTargetConsumer,
    KtmCacheTargetEvent,
    KtmCacheTargetEventClaim,
    KtmCacheTargetEventClaimItem,
)
from app.services.cache_target_event_consumer import (
    CacheTargetClaim,
    CacheTargetEventGapError,
    CacheTargetEventRecord,
    CacheTargetSnapshot,
    CacheTargetSnapshotItem,
    CacheTargetStaleEpochError,
    apply_cache_target_claim,
    load_pending_cache_target_ack,
    mark_cache_target_acknowledged,
    reconcile_cache_target_snapshot,
)

pytestmark = pytest.mark.asyncio


def _event(*, relay_order: int, restore_epoch: int = 7) -> CacheTargetEventRecord:
    event_id = uuid.uuid4()
    return CacheTargetEventRecord.model_validate(
        {
            "event_id": str(event_id),
            "event_type": "cache_target.state_applied",
            "event_scope": "target",
            "external_system": "pinvi",
            "target_key": str(uuid.uuid4()),
            "target_id": str(uuid.uuid4()),
            "restore_epoch": restore_epoch,
            "source_generation": 1,
            "target_sequence": 1,
            "relay_order": relay_order,
            "cursor": f"cursor-{relay_order}",
            "source_payload_fingerprint": "73" * 32,
            "payload_fingerprint": "70" * 32,
            "payload": {"status": "applied"},
            "occurred_at": datetime.now(UTC).isoformat(),
        }
    )


def _claim(*events: CacheTargetEventRecord) -> CacheTargetClaim:
    return CacheTargetClaim.model_validate(
        {
            "claim_id": str(uuid.uuid4()),
            "external_system": "pinvi",
            "consumer_id": "pinvi-cache-target-consumer",
            "lease_token": str(uuid.uuid4()),
            "status": "active",
            "first_relay_order": events[0].relay_order,
            "last_relay_order": events[-1].relay_order,
            "acked_through": None,
            "lease_expires_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
            "events": [event.model_dump(mode="json") for event in events],
            "idempotent_replay": False,
        }
    )


async def _seed_consumer(session_factory, *, epoch: int = 7) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        db.add(
            KtmCacheTargetConsumer(
                consumer_id="pinvi-cache-target-consumer",
                external_system="pinvi",
                active_restore_epoch=epoch,
            )
        )
        await db.commit()


async def test_local_commit_precedes_ack_and_duplicate_reclaim_is_noop(session_factory) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    event = _event(relay_order=1)
    first_claim = _claim(event)

    async with session_factory() as db:
        ack = await apply_cache_target_claim(db, first_claim)
        await db.commit()  # 원격 ACK 전에 process crash가 난 경계.

    assert ack.through_cursor == "cursor-1"
    assert ack.applied[0].event_id == event.event_id
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        claim = await db.get(KtmCacheTargetEventClaim, first_claim.claim_id)
        assert consumer is not None
        assert claim is not None
        assert consumer.local_applied_cursor == "cursor-1"
        assert consumer.remote_acked_cursor is None
        assert consumer.feature_cache_generation == 1
        assert claim.status == "active"

    reclaimed = _claim(event)
    async with session_factory() as db:
        duplicate_ack = await apply_cache_target_claim(db, reclaimed)
        await db.commit()

    assert duplicate_ack.through_cursor == ack.through_cursor
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(KtmCacheTargetEvent)) == 1
        assert await db.scalar(select(func.count()).select_from(KtmCacheTargetEventClaim)) == 2
        assert await db.scalar(select(func.count()).select_from(KtmCacheTargetEventClaimItem)) == 2
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        assert consumer.feature_cache_generation == 1


async def test_relay_gap_rolls_back_whole_claim(session_factory) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    claim = _claim(_event(relay_order=1), _event(relay_order=3))

    async with session_factory() as db:
        with pytest.raises(CacheTargetEventGapError):
            await apply_cache_target_claim(db, claim)
        await db.rollback()

    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(KtmCacheTargetEvent)) == 0
        assert await db.scalar(select(func.count()).select_from(KtmCacheTargetEventClaim)) == 0


async def test_stale_epoch_rolls_back_whole_claim(session_factory) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory, epoch=8)
    claim = _claim(_event(relay_order=1, restore_epoch=7))

    async with session_factory() as db:
        with pytest.raises(CacheTargetStaleEpochError):
            await apply_cache_target_claim(db, claim)
        await db.rollback()

    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(KtmCacheTargetEvent)) == 0
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        assert consumer.local_applied_cursor is None


async def test_snapshot_checksum_mismatch_keeps_consumer_fail_closed(session_factory) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    item = CacheTargetSnapshotItem(
        external_system="pinvi",
        target_key=str(uuid.uuid4()),
        state="deleted",
        source_generation=1,
        source_payload_fingerprint="73" * 32,
    )
    actual_root = cache_target_snapshot_merkle_root(
        [
            CacheTargetMerkleRow(
                external_system=item.external_system,
                target_key=item.target_key,
                state=item.state,
                source_generation=item.source_generation,
                source_payload_fingerprint=bytes.fromhex(item.source_payload_fingerprint),
            )
        ]
    )
    snapshot = CacheTargetSnapshot(
        snapshot_id="snapshot-1",
        restore_epoch=7,
        high_watermark_cursor="cursor-0",
        count=1,
        merkle_root=(b"x" * 32).hex(),
        items=[item],
    )
    assert actual_root.hex() != snapshot.merkle_root

    async with session_factory() as db:
        matched = await reconcile_cache_target_snapshot(db, snapshot)
        await db.commit()

    assert matched is False
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        assert consumer.ready is False
        assert consumer.reconcile_status == "mismatched"
        assert consumer.snapshot_id == "snapshot-1"
        assert consumer.snapshot_merkle_root == b"x" * 32


async def test_restart_reuses_durable_applied_receipts_for_exact_ack(session_factory) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    event = _event(relay_order=1)
    claim = _claim(event)
    async with session_factory() as db:
        expected = await apply_cache_target_claim(db, claim)
        await db.commit()

    async with session_factory() as db:
        restarted_ack = await load_pending_cache_target_ack(db)

    assert restarted_ack == expected
    assert restarted_ack is not None
    async with session_factory() as db:
        await mark_cache_target_acknowledged(db, restarted_ack)
        await db.commit()

    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        persisted_claim = await db.get(KtmCacheTargetEventClaim, claim.claim_id)
        item = await db.scalar(
            select(KtmCacheTargetEventClaimItem).where(
                KtmCacheTargetEventClaimItem.claim_id == claim.claim_id
            )
        )
        assert consumer is not None
        assert persisted_claim is not None
        assert item is not None
        assert consumer.remote_acked_cursor == "cursor-1"
        assert persisted_claim.status == "acked"
        assert item.acked_at is not None


async def test_stream_reconciled_has_no_fake_target_and_does_not_bump_cache_generation(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    root = b"r" * 32
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        consumer.snapshot_id = "snapshot-7"
        consumer.snapshot_count = 0
        consumer.snapshot_merkle_root = root
        await db.commit()
    event = CacheTargetEventRecord.model_validate(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "cache_target.reconciled",
            "event_scope": "stream",
            "external_system": "pinvi",
            "target_key": None,
            "target_id": None,
            "restore_epoch": 7,
            "source_generation": None,
            "target_sequence": None,
            "relay_order": 1,
            "cursor": "cursor-1",
            "source_payload_fingerprint": root.hex(),
            "payload_fingerprint": "70" * 32,
            "payload": {
                "actual_merkle_root": root.hex(),
                "expected_merkle_root": root.hex(),
                "snapshot_id": "snapshot-7",
                "status": "succeeded",
                "version": "cache-target-reconciliation-v1",
            },
            "occurred_at": datetime.now(UTC).isoformat(),
        }
    )
    claim = _claim(event)
    async with session_factory() as db:
        await apply_cache_target_claim(db, claim)
        await db.commit()
    async with session_factory() as db:
        stored = await db.get(KtmCacheTargetEvent, event.event_id)
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert stored is not None and stored.target_key is None
        assert stored.source_payload_fingerprint == root
        assert consumer is not None
        assert consumer.feature_cache_generation == 0
        assert consumer.high_watermark_cursor is None
