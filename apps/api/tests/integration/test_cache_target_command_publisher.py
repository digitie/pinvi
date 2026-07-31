"""cache target command lease/retry/DLQ transaction 경계."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.clients.kor_travel_map_cache_target import CacheTargetServiceProblem
from app.models.cache_target_sync import (
    KtmCacheTargetCommand,
    KtmCacheTargetConsumer,
    KtmCacheTargetHead,
)
from app.services.cache_target_command_publisher import (
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
