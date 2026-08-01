"""Map cache-target claim의 commit-before-ACK와 epoch/checksum 격리."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.clients.kor_travel_map_cache_target import (
    CacheTargetMutationResult,
    CacheTargetStateResult,
)
from app.core.cache_target_contract import (
    CacheTargetMerkleRow,
    cache_target_snapshot_merkle_root,
)
from app.models.cache_target_sync import (
    KtmCacheTargetCommand,
    KtmCacheTargetConsumer,
    KtmCacheTargetEvent,
    KtmCacheTargetEventClaim,
    KtmCacheTargetEventClaimItem,
    KtmCacheTargetHead,
    KtmCacheTargetReconciliationExpectation,
)
from app.services.cache_target_command_publisher import (
    LeasedCacheTargetCommand,
    complete_cache_target_command,
    lease_cache_target_commands,
)
from app.services.cache_target_event_consumer import (
    CacheTargetClaim,
    CacheTargetEventApplyError,
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
    target_id = uuid.uuid4()
    return CacheTargetEventRecord.model_validate(
        {
            "event_id": str(event_id),
            "event_type": "cache_target.links_reconciled",
            "event_scope": "target",
            "external_system": "pinvi",
            "target_key": str(uuid.uuid4()),
            "target_id": str(target_id),
            "restore_epoch": restore_epoch,
            "source_generation": 1,
            "target_sequence": 1,
            "relay_order": relay_order,
            "cursor": f"cursor-{relay_order}",
            "source_payload_fingerprint": "73" * 32,
            "payload_fingerprint": "70" * 32,
            "payload": {
                "version": "cache-target-event-v1",
                "request_id": str(uuid.uuid4()),
                "job_id": str(uuid.uuid4()),
                "status": "reconciled",
                "target_id": str(target_id),
                "active_link_count": 0,
            },
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


@pytest.mark.parametrize(
    ("event_kind", "field_name", "invalid_value"),
    [
        ("links", "restore_epoch", "7"),
        ("links", "target_id", "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"),
        ("deleted", "event_id", "BBBBBBBB-BBBB-4BBB-8BBB-BBBBBBBBBBBB"),
    ],
)
async def test_event_envelope_rejects_coerced_tuple_and_noncanonical_uuid(
    event_kind: str,
    field_name: str,
    invalid_value: object,
) -> None:
    event_data = _event(relay_order=1).model_dump(mode="json")
    if event_kind == "deleted":
        event_data["event_type"] = "cache_target.state_applied"
        event_data["payload"] = {
            "version": "cache-target-event-v1",
            "state": "deleted",
            "source_event_id": str(uuid.uuid4()),
            "target": None,
        }
    event_data[field_name] = invalid_value

    with pytest.raises(ValueError):
        CacheTargetEventRecord.model_validate(event_data)


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


async def test_deleted_event_causally_completes_command_before_late_http_result(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    poi_id = uuid.uuid4()
    historical_target_id = uuid.uuid4()
    delete_command_id = uuid.uuid4()
    put_command_id = uuid.uuid4()
    now = datetime.now(UTC)
    deleted_fingerprint = b"d" * 32
    active_fingerprint = b"a" * 32
    active_payload = {
        "version": "cache-target-source-v1",
        "state": "active",
        "coord": {"lon_e6": 126000000, "lat_e6": 37000000},
        "radius_m": 5000,
        "update_enabled": True,
    }
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        consumer.ready = True
        consumer.reconcile_status = "matched"
        db.add(
            KtmCacheTargetHead(
                poi_id=poi_id,
                external_system="pinvi",
                target_key=str(poi_id),
                desired_state="active",
                source_generation=3,
                source_payload_fingerprint=active_fingerprint,
                lon="126",
                lat="37",
                radius_km="5",
                update_enabled=True,
                remote_target_id=historical_target_id,
                remote_etag=f'"{historical_target_id}:4"',
                remote_restore_epoch=7,
                remote_source_generation=2,
                remote_target_sequence=2,
                remote_status="deleted",
            )
        )
        await db.flush()
        db.add_all(
            [
                KtmCacheTargetCommand(
                    command_id=delete_command_id,
                    poi_id=poi_id,
                    operation="delete",
                    source_generation=2,
                    payload={"state": "deleted", "version": "cache-target-source-v1"},
                    payload_fingerprint=deleted_fingerprint,
                    status="leased",
                    attempts=1,
                    lease_owner="publisher-before-crash",
                    lease_until=now + timedelta(minutes=1),
                    expected_etag=f'"{historical_target_id}:4"',
                ),
                KtmCacheTargetCommand(
                    command_id=put_command_id,
                    poi_id=poi_id,
                    operation="put",
                    source_generation=3,
                    payload=active_payload,
                    payload_fingerprint=active_fingerprint,
                    status="pending",
                    available_at=now,
                ),
            ]
        )
        await db.commit()

    deleted_event = CacheTargetEventRecord.model_validate(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "cache_target.state_applied",
            "event_scope": "target",
            "external_system": "pinvi",
            "target_key": str(poi_id),
            "target_id": str(historical_target_id),
            "restore_epoch": 7,
            "source_generation": 2,
            "target_sequence": 2,
            "relay_order": 1,
            "cursor": "cursor-1",
            "source_payload_fingerprint": deleted_fingerprint.hex(),
            "payload_fingerprint": "70" * 32,
            "payload": {
                "version": "cache-target-event-v1",
                "state": "deleted",
                "source_event_id": str(delete_command_id),
                "target": None,
            },
            "occurred_at": now.isoformat(),
        }
    )
    async with session_factory() as db:
        await apply_cache_target_claim(db, _claim(deleted_event), now=now)
        await db.commit()

    leased_delete = LeasedCacheTargetCommand(
        command_id=delete_command_id,
        poi_id=poi_id,
        operation="delete",
        external_system="pinvi",
        target_key=str(poi_id),
        restore_epoch=7,
        source_generation=2,
        payload={"state": "deleted", "version": "cache-target-source-v1"},
        expected_etag=f'"{historical_target_id}:4"',
        occurred_at=now,
        lease_owner="publisher-before-crash",
    )
    late_result = CacheTargetMutationResult(
        200,
        CacheTargetStateResult(
            external_system="pinvi",
            target_key=str(poi_id),
            state="deleted",
            restore_epoch=7,
            source_generation=2,
            source_payload_fingerprint=deleted_fingerprint.hex(),
            entity_tag=f'"{historical_target_id}:5"',
            target_id=historical_target_id,
            target_sequence=2,
        ),
        f'"{historical_target_id}:5"',
    )
    async with session_factory() as db:
        await complete_cache_target_command(
            db,
            leased=leased_delete,
            result=late_result,
            consumer_id="pinvi-cache-target-consumer",
            now=now,
        )
        leased_put = await lease_cache_target_commands(
            db,
            lease_owner="publisher-after-recovery",
            consumer_id="pinvi-cache-target-consumer",
            limit=1,
            lease_seconds=60,
            max_attempts=5,
            now=now,
        )
        await db.commit()

    async with session_factory() as db:
        head = await db.get(KtmCacheTargetHead, poi_id)
        command = await db.get(KtmCacheTargetCommand, delete_command_id)
    assert head is not None
    assert command is not None
    assert command.status == "succeeded"
    assert command.lease_owner is None
    assert command.error_code is None
    assert head.remote_status == "deleted"
    assert head.remote_target_id is None
    assert head.remote_etag is None
    assert head.remote_restore_epoch == 7
    assert head.remote_source_generation == 2
    assert head.remote_target_sequence == 2
    assert len(leased_put) == 1
    assert leased_put[0].command_id == put_command_id
    assert leased_put[0].expected_etag is None


async def test_unknown_state_applied_payload_is_validated_before_head_lookup(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    event_data = _event(relay_order=1).model_dump(mode="json")
    event_data["event_type"] = "cache_target.state_applied"
    event_data["payload"] = {"status": "applied"}
    event = CacheTargetEventRecord.model_validate(event_data)

    async with session_factory() as db:
        with pytest.raises(CacheTargetEventApplyError) as caught:
            await apply_cache_target_claim(db, _claim(event))
        await db.rollback()

    assert "exact v1 계약" in str(caught.value.cause)
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(KtmCacheTargetEvent)) == 0


@pytest.mark.parametrize("invalid_field", ["coerced_coordinate", "noncanonical_etag"])
async def test_state_applied_rejects_non_exact_target_material_before_head_lookup(
    session_factory,
    invalid_field: str,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    event_data = _event(relay_order=1).model_dump(mode="json")
    target_id = event_data["target_id"]
    target = {
        "target_id": target_id,
        "entity_tag": f'"{target_id}:1"',
        "coord": {"lon_e6": 126000000, "lat_e6": 37000000},
        "radius_m": 5000,
        "update_enabled": True,
    }
    if invalid_field == "coerced_coordinate":
        target["coord"] = {"lon_e6": True, "lat_e6": 37000000}
    else:
        target["entity_tag"] = f'"{target_id}:not-a-version"'
    event_data["event_type"] = "cache_target.state_applied"
    event_data["payload"] = {
        "version": "cache-target-event-v1",
        "state": "active",
        "source_event_id": str(uuid.uuid4()),
        "target": target,
    }
    event = CacheTargetEventRecord.model_validate(event_data)

    async with session_factory() as db:
        with pytest.raises(CacheTargetEventApplyError) as caught:
            await apply_cache_target_claim(db, _claim(event))
        await db.rollback()

    assert "exact v1 계약" in str(caught.value.cause)


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
    request_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        consumer.snapshot_id = "newer-generic-snapshot"
        consumer.snapshot_count = 0
        consumer.snapshot_merkle_root = root
        db.add(
            KtmCacheTargetReconciliationExpectation(
                request_id=request_id,
                external_system="pinvi",
                snapshot_id=snapshot_id,
                restore_epoch=7,
                snapshot_count=0,
                snapshot_merkle_root=root,
                high_watermark_cursor="cursor-0",
                status="pending",
            )
        )
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
                "request_id": str(request_id),
                "snapshot_id": str(snapshot_id),
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
        expectation = await db.get(KtmCacheTargetReconciliationExpectation, request_id)
        assert expectation is not None
        assert expectation.status == "received"
        assert expectation.receipt_event_id == event.event_id
