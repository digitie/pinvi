"""cache target command lease/retry/DLQ transaction 경계."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.clients.kor_travel_map_cache_target import (
    CacheTargetMutationResult,
    CacheTargetNetworkError,
    CacheTargetServiceProblem,
    CacheTargetStateResult,
)
from app.models.cache_target_sync import (
    KtmCacheTargetCommand,
    KtmCacheTargetConsumer,
    KtmCacheTargetHead,
)
from app.services.cache_target_command_publisher import (
    LeasedCacheTargetCommand,
    complete_cache_target_command,
    fail_cache_target_command,
    lease_cache_target_commands,
)

pytestmark = pytest.mark.asyncio


async def _seed(session_factory) -> uuid.UUID:  # type: ignore[no-untyped-def]
    poi_id = uuid.uuid4()
    async with session_factory() as db:
        db.add(
            KtmCacheTargetConsumer(
                consumer_id="pinvi-cache-target-consumer",
                external_system="pinvi",
                active_restore_epoch=7,
                reconcile_status="matched",
                ready=True,
            )
        )
        db.add(
            KtmCacheTargetHead(
                poi_id=poi_id,
                external_system="pinvi",
                target_key=str(poi_id),
                desired_state="active",
                source_generation=1,
                source_payload_fingerprint=b"s" * 32,
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
                payload_fingerprint=b"s" * 32,
                status="pending",
            )
        )
        await db.commit()
    return poi_id


async def test_short_lease_commits_before_network_and_transient_requeues(session_factory) -> None:  # type: ignore[no-untyped-def]
    poi_id = await _seed(session_factory)
    now = datetime.now(UTC)
    async with session_factory() as db:
        leased = await lease_cache_target_commands(
            db,
            lease_owner="worker-1",
            consumer_id="pinvi-cache-target-consumer",
            limit=10,
            lease_seconds=60,
            max_attempts=5,
            now=now,
        )
        await db.commit()
    assert len(leased) == 1

    async with session_factory() as db:
        row = await db.get(KtmCacheTargetCommand, leased[0].command_id)
        assert row is not None
        assert row.status == "leased"
        assert row.attempts == 1

        outcome = await fail_cache_target_command(
            db,
            leased=leased[0],
            error=CacheTargetServiceProblem(
                status_code=503,
                code="SERVICE_UNAVAILABLE",
                retry_after=30,
            ),
            max_attempts=5,
            consumer_id="pinvi-cache-target-consumer",
            now=now,
        )
        await db.commit()
    assert outcome == "retry"

    async with session_factory() as db:
        row = await db.get(KtmCacheTargetCommand, leased[0].command_id)
        head = await db.get(KtmCacheTargetHead, poi_id)
        assert row is not None
        assert head is not None
        assert row.status == "pending"
        assert row.available_at > now
        assert head.remote_etag is None


async def test_initial_cutover_leases_put_while_ordinary_unready_gate_stays_closed(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed(session_factory)
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        consumer.ready = False
        consumer.reconcile_status = "checking"
        await db.commit()

    async with session_factory() as db:
        ordinary = await lease_cache_target_commands(
            db,
            lease_owner="ordinary-worker",
            consumer_id="pinvi-cache-target-consumer",
            limit=10,
            lease_seconds=60,
            max_attempts=5,
        )
        await db.commit()
    assert ordinary == []

    async with session_factory() as db:
        initial = await lease_cache_target_commands(
            db,
            lease_owner="initial-cutover",
            consumer_id="pinvi-cache-target-consumer",
            limit=10,
            lease_seconds=60,
            max_attempts=5,
            initial_cutover=True,
        )
        await db.commit()
    assert len(initial) == 1
    assert initial[0].operation == "put"


async def test_delete_completion_clears_active_precondition_for_following_put(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    poi_id = uuid.uuid4()
    deleted_target_id = uuid.uuid4()
    delete_command_id = uuid.uuid4()
    put_command_id = uuid.uuid4()
    now = datetime.now(UTC)
    active_payload = {
        "version": "cache-target-source-v1",
        "state": "active",
        "coord": {"lon_e6": 126000000, "lat_e6": 37000000},
        "radius_m": 5000,
        "update_enabled": True,
    }
    async with session_factory() as db:
        db.add(
            KtmCacheTargetConsumer(
                consumer_id="pinvi-cache-target-consumer",
                external_system="pinvi",
                active_restore_epoch=7,
                reconcile_status="matched",
                ready=True,
            )
        )
        db.add(
            KtmCacheTargetHead(
                poi_id=poi_id,
                external_system="pinvi",
                target_key=str(poi_id),
                desired_state="active",
                source_generation=3,
                source_payload_fingerprint=b"a" * 32,
                lon="126",
                lat="37",
                radius_km="5",
                update_enabled=True,
                remote_target_id=deleted_target_id,
                remote_etag=f'"{deleted_target_id}:4"',
                remote_restore_epoch=7,
                remote_source_generation=2,
                remote_target_sequence=1,
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
                    payload_fingerprint=b"d" * 32,
                    status="leased",
                    attempts=1,
                    lease_owner="worker-delete",
                    lease_until=now + timedelta(minutes=1),
                    expected_etag=f'"{deleted_target_id}:4"',
                ),
                KtmCacheTargetCommand(
                    command_id=put_command_id,
                    poi_id=poi_id,
                    operation="put",
                    source_generation=3,
                    payload=active_payload,
                    payload_fingerprint=b"a" * 32,
                    status="pending",
                    available_at=now,
                ),
            ]
        )
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
        expected_etag=f'"{deleted_target_id}:4"',
        occurred_at=now,
        lease_owner="worker-delete",
    )
    delete_result = CacheTargetMutationResult(
        200,
        CacheTargetStateResult(
            external_system="pinvi",
            target_key=str(poi_id),
            state="deleted",
            restore_epoch=7,
            source_generation=2,
            source_payload_fingerprint=(b"d" * 32).hex(),
            entity_tag=f'"{deleted_target_id}:5"',
            target_id=deleted_target_id,
            target_sequence=1,
        ),
        f'"{deleted_target_id}:5"',
    )
    async with session_factory() as db:
        await complete_cache_target_command(
            db,
            leased=leased_delete,
            result=delete_result,
            consumer_id="pinvi-cache-target-consumer",
            now=now,
        )
        await db.commit()

    async with session_factory() as db:
        head = await db.get(KtmCacheTargetHead, poi_id)
        leased_put = await lease_cache_target_commands(
            db,
            lease_owner="worker-put",
            consumer_id="pinvi-cache-target-consumer",
            limit=1,
            lease_seconds=60,
            max_attempts=5,
            now=now,
        )
        await db.commit()

    assert head is not None
    assert head.remote_status == "deleted"
    assert head.remote_restore_epoch == 7
    assert head.remote_source_generation == 2
    assert head.remote_target_sequence == 1
    assert head.remote_target_id is None
    assert head.remote_etag is None
    assert len(leased_put) == 1
    assert leased_put[0].command_id == put_command_id
    assert leased_put[0].expected_etag is None


async def test_late_completion_from_previous_restore_epoch_is_superseded(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    poi_id = uuid.uuid4()
    historical_target_id = uuid.uuid4()
    command_id = uuid.uuid4()
    now = datetime.now(UTC)
    fingerprint = b"d" * 32
    async with session_factory() as db:
        db.add(
            KtmCacheTargetConsumer(
                consumer_id="pinvi-cache-target-consumer",
                external_system="pinvi",
                active_restore_epoch=8,
                reconcile_status="checking",
                ready=False,
            )
        )
        db.add(
            KtmCacheTargetHead(
                poi_id=poi_id,
                external_system="pinvi",
                target_key=str(poi_id),
                desired_state="deleted",
                source_generation=2,
                source_payload_fingerprint=fingerprint,
                radius_km="5",
                update_enabled=False,
            )
        )
        await db.flush()
        db.add(
            KtmCacheTargetCommand(
                command_id=command_id,
                poi_id=poi_id,
                operation="delete",
                source_generation=2,
                payload={"state": "deleted", "version": "cache-target-source-v1"},
                payload_fingerprint=fingerprint,
                status="leased",
                attempts=1,
                lease_owner="old-epoch-worker",
                lease_until=now + timedelta(minutes=1),
                expected_etag=f'"{historical_target_id}:4"',
            )
        )
        await db.commit()

    leased = LeasedCacheTargetCommand(
        command_id=command_id,
        poi_id=poi_id,
        operation="delete",
        external_system="pinvi",
        target_key=str(poi_id),
        restore_epoch=7,
        source_generation=2,
        payload={"state": "deleted", "version": "cache-target-source-v1"},
        expected_etag=f'"{historical_target_id}:4"',
        occurred_at=now,
        lease_owner="old-epoch-worker",
    )
    result = CacheTargetMutationResult(
        200,
        CacheTargetStateResult(
            external_system="pinvi",
            target_key=str(poi_id),
            state="deleted",
            restore_epoch=7,
            source_generation=2,
            source_payload_fingerprint=fingerprint.hex(),
            entity_tag=f'"{historical_target_id}:5"',
            target_id=historical_target_id,
            target_sequence=2,
        ),
        f'"{historical_target_id}:5"',
    )
    async with session_factory() as db:
        outcome = await complete_cache_target_command(
            db,
            leased=leased,
            result=result,
            consumer_id="pinvi-cache-target-consumer",
            now=now,
        )
        await db.commit()
    async with session_factory() as db:
        replay_outcome = await complete_cache_target_command(
            db,
            leased=leased,
            result=result,
            consumer_id="pinvi-cache-target-consumer",
            now=now,
        )
        await db.commit()

    async with session_factory() as db:
        command = await db.get(KtmCacheTargetCommand, command_id)
        head = await db.get(KtmCacheTargetHead, poi_id)
    assert outcome == "stale_epoch"
    assert replay_outcome == "stale_epoch"
    assert command is not None
    assert command.status == "superseded"
    assert command.error_code == "STALE_RESTORE_EPOCH"
    assert command.lease_owner is None
    assert command.completed_at == now
    assert head is not None
    assert head.remote_restore_epoch is None
    assert head.remote_source_generation is None
    assert head.remote_target_sequence is None
    assert head.remote_target_id is None
    assert head.remote_etag is None


async def test_late_failure_from_previous_restore_epoch_is_superseded(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    poi_id = await _seed(session_factory)
    now = datetime.now(UTC)
    async with session_factory() as db:
        leased_rows = await lease_cache_target_commands(
            db,
            lease_owner="old-epoch-worker",
            consumer_id="pinvi-cache-target-consumer",
            limit=1,
            lease_seconds=60,
            max_attempts=5,
            now=now,
        )
        await db.commit()
    assert len(leased_rows) == 1
    leased = leased_rows[0]

    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        head = await db.get(KtmCacheTargetHead, poi_id)
        assert consumer is not None
        assert head is not None
        consumer.active_restore_epoch = 8
        consumer.reconcile_status = "checking"
        consumer.ready = False
        head.remote_target_id = None
        head.remote_etag = None
        head.remote_restore_epoch = None
        head.remote_source_generation = None
        head.remote_target_sequence = None
        head.remote_status = None
        await db.commit()

    async with session_factory() as db:
        outcome = await fail_cache_target_command(
            db,
            leased=leased,
            error=CacheTargetNetworkError("old epoch response outcome uncertain"),
            max_attempts=5,
            consumer_id="pinvi-cache-target-consumer",
            now=now,
        )
        await db.commit()

    async with session_factory() as db:
        command = await db.get(KtmCacheTargetCommand, leased.command_id)
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        head = await db.get(KtmCacheTargetHead, poi_id)
    assert outcome == "superseded"
    assert command is not None
    assert command.status == "superseded"
    assert command.error_code == "STALE_RESTORE_EPOCH"
    assert command.lease_owner is None
    assert consumer is not None
    assert consumer.active_restore_epoch == 8
    assert consumer.reconcile_status == "checking"
    assert consumer.ready is False
    assert head is not None
    assert head.remote_restore_epoch is None
    assert head.remote_target_id is None
    assert head.remote_etag is None


async def test_initial_cutover_drain_order_is_target_generation_command_not_due_time(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    earlier_key = uuid.UUID(int=1)
    later_key = uuid.UUID(int=2)
    now = datetime.now(UTC)
    async with session_factory() as db:
        db.add(
            KtmCacheTargetConsumer(
                consumer_id="pinvi-cache-target-consumer",
                external_system="pinvi",
                active_restore_epoch=7,
                reconcile_status="checking",
                ready=False,
            )
        )
        for poi_id in (later_key, earlier_key):
            db.add(
                KtmCacheTargetHead(
                    poi_id=poi_id,
                    external_system="pinvi",
                    target_key=str(poi_id),
                    desired_state="active",
                    source_generation=1,
                    source_payload_fingerprint=b"s" * 32,
                    lon="126",
                    lat="37",
                    radius_km="5",
                    update_enabled=True,
                )
            )
        await db.flush()
        for poi_id, available_at in (
            (later_key, now - timedelta(minutes=2)),
            (earlier_key, now - timedelta(minutes=1)),
        ):
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
                    payload_fingerprint=b"s" * 32,
                    status="pending",
                    available_at=available_at,
                )
            )
        await db.commit()

    async with session_factory() as db:
        leased = await lease_cache_target_commands(
            db,
            lease_owner="initial-cutover",
            consumer_id="pinvi-cache-target-consumer",
            limit=10,
            lease_seconds=60,
            max_attempts=5,
            initial_cutover=True,
            now=now,
        )
        await db.commit()

    assert [row.target_key for row in leased] == [str(earlier_key), str(later_key)]


async def test_auth_failure_dead_letters_and_halts_consumer(session_factory) -> None:  # type: ignore[no-untyped-def]
    await _seed(session_factory)
    async with session_factory() as db:
        leased = await lease_cache_target_commands(
            db,
            lease_owner="worker-1",
            consumer_id="pinvi-cache-target-consumer",
            limit=10,
            lease_seconds=60,
            max_attempts=5,
        )
        await db.commit()
    async with session_factory() as db:
        outcome = await fail_cache_target_command(
            db,
            leased=leased[0],
            error=CacheTargetServiceProblem(
                status_code=401,
                code="CACHE_TARGET_SERVICE_TOKEN_INVALID",
                retry_after=None,
            ),
            max_attempts=5,
            consumer_id="pinvi-cache-target-consumer",
        )
        await db.commit()
    assert outcome == "halt"

    async with session_factory() as db:
        row = await db.get(KtmCacheTargetCommand, leased[0].command_id)
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert row is not None
        assert consumer is not None
        assert row.status == "dead_letter"
        assert consumer.ready is False
        assert consumer.reconcile_status == "blocked"


@pytest.mark.parametrize(
    ("status_code", "code", "expected_outcome", "expected_reconcile"),
    [
        (412, "PRECONDITION_FAILED", "reconcile", "mismatched"),
        (422, "VALIDATION_ERROR", "dead_letter", "matched"),
        (409, "IDEMPOTENCY_KEY_REUSED", "dead_letter", "matched"),
    ],
)
async def test_permanent_and_reconcile_failures_are_never_blind_retried(
    session_factory,
    status_code: int,
    code: str,
    expected_outcome: str,
    expected_reconcile: str,
) -> None:  # type: ignore[no-untyped-def]
    await _seed(session_factory)
    async with session_factory() as db:
        leased = await lease_cache_target_commands(
            db,
            lease_owner="worker-1",
            consumer_id="pinvi-cache-target-consumer",
            limit=1,
            lease_seconds=60,
            max_attempts=5,
        )
        await db.commit()
    async with session_factory() as db:
        outcome = await fail_cache_target_command(
            db,
            leased=leased[0],
            error=CacheTargetServiceProblem(
                status_code=status_code,
                code=code,
                retry_after=None,
            ),
            max_attempts=5,
            consumer_id="pinvi-cache-target-consumer",
        )
        await db.commit()
    assert outcome == expected_outcome
    async with session_factory() as db:
        row = await db.get(KtmCacheTargetCommand, leased[0].command_id)
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert row is not None and row.status == "dead_letter"
        assert consumer is not None and consumer.reconcile_status == expected_reconcile
