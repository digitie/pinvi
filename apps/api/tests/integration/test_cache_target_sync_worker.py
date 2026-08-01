"""cache target startup epoch/snapshot fail-closed bootstrap."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.clients.kor_travel_map_cache_target import (
    CacheTargetServiceClient,
    CacheTargetServiceProblem,
)
from app.core.config import settings
from app.models.cache_target_sync import (
    KtmCacheTargetConsumer,
    KtmCacheTargetEvent,
    KtmCacheTargetEventClaim,
    KtmCacheTargetReconciliationExpectation,
)
from app.services.cache_target_event_consumer import (
    CacheTargetClaim,
    CacheTargetConsumerError,
    CacheTargetEventRecord,
    apply_cache_target_claim,
)
from app.services.cache_target_sync_worker import (
    _consumer_loop,
    bootstrap_cache_target_sync,
    consume_cache_target_once,
)

pytestmark = pytest.mark.asyncio


def _links_reconciled_payload(target_id: uuid.UUID) -> dict[str, object]:
    return {
        "version": "cache-target-event-v1",
        "request_id": str(uuid.uuid4()),
        "job_id": str(uuid.uuid4()),
        "status": "reconciled",
        "target_id": str(target_id),
        "active_link_count": 0,
    }


def _claim_with_mid_stream_poison() -> CacheTargetClaim:
    occurred_at = datetime.now(UTC).isoformat()
    target_id = uuid.uuid4()
    first = CacheTargetEventRecord.model_validate(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "cache_target.links_reconciled",
            "event_scope": "target",
            "external_system": "pinvi",
            "target_key": str(uuid.uuid4()),
            "target_id": str(target_id),
            "restore_epoch": 7,
            "source_generation": 1,
            "target_sequence": 1,
            "relay_order": 1,
            "cursor": "cursor-1",
            "source_payload_fingerprint": "73" * 32,
            "payload_fingerprint": "70" * 32,
            "payload": _links_reconciled_payload(target_id),
            "occurred_at": occurred_at,
        }
    )
    poison = CacheTargetEventRecord.model_validate(
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
            "relay_order": 2,
            "cursor": "cursor-2",
            "source_payload_fingerprint": "72" * 32,
            "payload_fingerprint": "71" * 32,
            "payload": {
                "actual_merkle_root": "72" * 32,
                "expected_merkle_root": "72" * 32,
                "request_id": str(uuid.uuid4()),
                "snapshot_id": "wrong-snapshot",
                "status": "succeeded",
                "version": "cache-target-reconciliation-v1",
            },
            "occurred_at": occurred_at,
        }
    )
    return CacheTargetClaim.model_validate(
        {
            "claim_id": str(uuid.uuid4()),
            "external_system": "pinvi",
            "consumer_id": "pinvi-cache-target-consumer",
            "lease_token": str(uuid.uuid4()),
            "status": "active",
            "first_relay_order": 1,
            "last_relay_order": 2,
            "acked_through": None,
            "lease_expires_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
            "events": [first.model_dump(mode="json"), poison.model_dump(mode="json")],
            "idempotent_replay": False,
        }
    )


async def _seed_ready_consumer(session_factory) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        db.add(
            KtmCacheTargetConsumer(
                consumer_id="pinvi-cache-target-consumer",
                external_system="pinvi",
                active_restore_epoch=7,
                snapshot_id="expected-snapshot",
                snapshot_count=0,
                snapshot_merkle_root=b"r" * 32,
                reconcile_status="matched",
                ready=True,
            )
        )
        await db.commit()


async def test_unexpected_consumer_failure_marks_durable_readiness_blocked(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_ready_consumer(session_factory)

    class InvalidClaimClient:
        async def claim_events(self, **kwargs: object) -> None:
            del kwargs
            raise ValueError("producer contract validation failed")

    config = settings.model_copy(update={"pinvi_kor_travel_map_cache_target_poll_seconds": 0.1})
    task = asyncio.create_task(
        _consumer_loop(
            InvalidClaimClient(),  # type: ignore[arg-type]
            config,
            session_factory=session_factory,
        )
    )
    try:
        for _ in range(100):
            async with session_factory() as db:
                consumer = await db.get(
                    KtmCacheTargetConsumer,
                    "pinvi-cache-target-consumer",
                )
                if consumer is not None and not consumer.ready:
                    break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("consumer fatal failure가 durable readiness를 닫지 않았습니다.")
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        assert consumer.ready is False
        assert consumer.reconcile_status == "blocked"


async def test_actual_map_reconciled_wire_then_target_is_applied_and_acked(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_ready_consumer(session_factory)
    claim_id = uuid.uuid4()
    lease_token = uuid.uuid4()
    reconciled_event_id = uuid.uuid4()
    target_event_id = uuid.uuid4()
    target_key = uuid.uuid4()
    map_target_id = uuid.uuid4()
    request_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    root = (b"r" * 32).hex()
    occurred_at = datetime.now(UTC).isoformat()
    calls: list[tuple[str, dict[str, object]]] = []
    async with session_factory() as db:
        db.add(
            KtmCacheTargetReconciliationExpectation(
                request_id=request_id,
                external_system="pinvi",
                snapshot_id=snapshot_id,
                restore_epoch=7,
                snapshot_count=0,
                snapshot_merkle_root=bytes.fromhex(root),
                high_watermark_cursor="cursor-0",
                status="pending",
            )
        )
        await db.commit()
    claim = {
        "claim_id": str(claim_id),
        "external_system": "pinvi",
        "consumer_id": "pinvi-cache-target-consumer",
        "lease_token": str(lease_token),
        "status": "active",
        "first_relay_order": 1,
        "last_relay_order": 2,
        "acked_through": None,
        "lease_expires_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
        "events": [
            {
                "event_id": str(reconciled_event_id),
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
                "source_payload_fingerprint": root,
                "payload_fingerprint": "70" * 32,
                "payload": {
                    "actual_merkle_root": root,
                    "expected_merkle_root": root,
                    "request_id": str(request_id),
                    "snapshot_id": str(snapshot_id),
                    "status": "succeeded",
                    "version": "cache-target-reconciliation-v1",
                },
                "occurred_at": occurred_at,
            },
            {
                "event_id": str(target_event_id),
                "event_type": "cache_target.links_reconciled",
                "event_scope": "target",
                "external_system": "pinvi",
                "target_key": str(target_key),
                "target_id": str(map_target_id),
                "restore_epoch": 7,
                "source_generation": 1,
                "target_sequence": 1,
                "relay_order": 2,
                "cursor": "cursor-2",
                "source_payload_fingerprint": "73" * 32,
                "payload_fingerprint": "71" * 32,
                "payload": _links_reconciled_payload(map_target_id),
                "occurred_at": occurred_at,
            },
        ],
        "idempotent_replay": False,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append((request.url.path, body))
        if request.url.path.endswith("event-claims"):
            return httpx.Response(200, json={"data": claim, "meta": {}})
        assert request.url.path.endswith("event-acks")
        return httpx.Response(200, json={"data": {"status": "ok"}, "meta": {}})

    client = CacheTargetServiceClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler)),
        role="consumer",
        token="u" * 32,
    )
    try:
        assert await consume_cache_target_once(
            session_factory,
            client=client,
            consumer_id="pinvi-cache-target-consumer",
            batch_size=100,
            lease_seconds=60,
            max_attempts=5,
        )
    finally:
        await client.aclose()

    assert [path for path, _ in calls] == [
        "/v1/service/cache-target-event-claims",
        "/v1/service/cache-target-event-acks",
    ]
    assert calls[1][1]["through_cursor"] == "cursor-2"
    applied = calls[1][1]["applied"]
    assert isinstance(applied, list)
    assert len(applied) == 2
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        inbox = list(
            await db.scalars(select(KtmCacheTargetEvent).order_by(KtmCacheTargetEvent.relay_order))
        )
        assert consumer is not None
        assert consumer.local_applied_cursor == "cursor-2"
        assert consumer.remote_acked_cursor == "cursor-2"
        assert consumer.feature_cache_generation == 1
        assert [event.event_id for event in inbox] == [reconciled_event_id, target_event_id]
        expectation = await db.get(KtmCacheTargetReconciliationExpectation, request_id)
        assert expectation is not None
        assert expectation.status == "received"
        assert expectation.receipt_event_id == reconciled_event_id


async def test_expired_claim_reclaim_deduplicates_target_side_effect(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_ready_consumer(session_factory)
    event_id = uuid.uuid4()
    target_key = uuid.uuid4()
    map_target_id = uuid.uuid4()
    event = {
        "event_id": str(event_id),
        "event_type": "cache_target.links_reconciled",
        "event_scope": "target",
        "external_system": "pinvi",
        "target_key": str(target_key),
        "target_id": str(map_target_id),
        "restore_epoch": 7,
        "source_generation": 1,
        "target_sequence": 1,
        "relay_order": 1,
        "cursor": "cursor-1",
        "source_payload_fingerprint": "73" * 32,
        "payload_fingerprint": "70" * 32,
        "payload": _links_reconciled_payload(map_target_id),
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    now = datetime.now(UTC)
    first_claim = CacheTargetClaim.model_validate(
        {
            "claim_id": str(uuid.uuid4()),
            "external_system": "pinvi",
            "consumer_id": "pinvi-cache-target-consumer",
            "lease_token": str(uuid.uuid4()),
            "status": "active",
            "first_relay_order": 1,
            "last_relay_order": 1,
            "acked_through": None,
            "lease_expires_at": (now + timedelta(milliseconds=20)).isoformat(),
            "events": [event],
            "idempotent_replay": False,
        }
    )
    async with session_factory() as db:
        await apply_cache_target_claim(db, first_claim, now=now)
        await db.commit()
    await asyncio.sleep(0.03)

    second_claim = {
        **first_claim.model_dump(mode="json"),
        "claim_id": str(uuid.uuid4()),
        "lease_token": str(uuid.uuid4()),
        "lease_expires_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
    }
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("event-claims"):
            return httpx.Response(200, json={"data": second_claim, "meta": {}})
        assert request.url.path.endswith("event-acks")
        return httpx.Response(200, json={"data": {"status": "ok"}, "meta": {}})

    client = CacheTargetServiceClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler)),
        role="consumer",
        token="u" * 32,
    )
    try:
        assert await consume_cache_target_once(
            session_factory,
            client=client,
            consumer_id="pinvi-cache-target-consumer",
            batch_size=100,
            lease_seconds=60,
            max_attempts=5,
        )
    finally:
        await client.aclose()

    assert calls == [
        "/v1/service/cache-target-event-claims",
        "/v1/service/cache-target-event-acks",
    ]
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        event_count = len(list(await db.scalars(select(KtmCacheTargetEvent))))
        claims = list(
            await db.scalars(
                select(KtmCacheTargetEventClaim).order_by(KtmCacheTargetEventClaim.received_at)
            )
        )
        assert consumer is not None
        assert consumer.feature_cache_generation == 1
        assert consumer.remote_acked_cursor == "cursor-1"
        assert event_count == 1
        assert [claim.status for claim in claims] == ["expired", "acked"]


async def test_bootstrap_adopts_new_epoch_and_matching_empty_snapshot(session_factory) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        db.add(
            KtmCacheTargetConsumer(
                consumer_id="pinvi-cache-target-consumer",
                external_system="pinvi",
                active_restore_epoch=6,
                local_applied_cursor="old-local",
                remote_acked_cursor="old-acked",
                reconcile_status="matched",
                ready=True,
            )
        )
        await db.commit()

    empty_root = hashlib.sha256(b"KTMCTEMPTY\x00").hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/service/cache-target-streams/pinvi":
            etag = '"pinvi:7"'
            return httpx.Response(
                200,
                headers={"ETag": etag},
                json={
                    "data": {
                        "external_system": "pinvi",
                        "restore_epoch": 7,
                        "control_version": 7,
                        "entity_tag": etag,
                        "state": "active",
                        "consumer_id": "pinvi-cache-target-consumer",
                        "blocked_event_id": None,
                        "updated_at": "2026-07-31T00:00:00Z",
                    },
                    "meta": {},
                },
            )
        assert request.url.path == "/v1/service/cache-target-snapshots/pinvi"
        return httpx.Response(
            200,
            json={
                "data": {
                    "snapshot_id": "snapshot-7",
                    "restore_epoch": 7,
                    "high_watermark_cursor": "cursor-0",
                    "count": 0,
                    "merkle_root": empty_root,
                    "items": [],
                },
                "meta": {},
            },
        )

    client = CacheTargetServiceClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler)),
        role="consumer",
        token="u" * 32,
    )
    try:
        await bootstrap_cache_target_sync(
            session_factory,
            consumer_client=client,
            consumer_id="pinvi-cache-target-consumer",
            batch_size=100,
            lease_seconds=60,
            max_attempts=5,
        )
    finally:
        await client.aclose()

    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        assert consumer.active_restore_epoch == 7
        assert consumer.local_applied_cursor is None
        assert consumer.remote_acked_cursor is None
        assert consumer.snapshot_id == "snapshot-7"
        assert consumer.reconcile_status == "matched"
        assert consumer.ready is True


@pytest.mark.parametrize("claim_available", [True, False])
async def test_bootstrap_resumes_completed_reconciliation_drain_before_local_ready(
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
    claim_available: bool,
) -> None:  # type: ignore[no-untyped-def]
    request_id = uuid.uuid4()
    expected_snapshot_id = uuid.uuid4()
    replay_target_id = uuid.uuid4()
    replay_map_target_id = uuid.uuid4()
    empty_root = hashlib.sha256(b"KTMCTEMPTY\x00").hexdigest()
    occurred_at = datetime.now(UTC).isoformat()
    async with session_factory() as db:
        db.add(
            KtmCacheTargetConsumer(
                consumer_id="pinvi-cache-target-consumer",
                external_system="pinvi",
                active_restore_epoch=7,
                reconcile_status="matched",
                ready=False,
            )
        )
        db.add(
            KtmCacheTargetReconciliationExpectation(
                request_id=request_id,
                external_system="pinvi",
                snapshot_id=expected_snapshot_id,
                restore_epoch=7,
                snapshot_count=0,
                snapshot_merkle_root=bytes.fromhex(empty_root),
                high_watermark_cursor="cursor-0",
                status="pending",
            )
        )
        await db.commit()

    replay_claim = CacheTargetClaim.model_validate(
        {
            "claim_id": str(uuid.uuid4()),
            "external_system": "pinvi",
            "consumer_id": "pinvi-cache-target-consumer",
            "lease_token": str(uuid.uuid4()),
            "status": "active",
            "first_relay_order": 1,
            "last_relay_order": 2,
            "acked_through": None,
            "lease_expires_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
            "events": [
                {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "cache_target.links_reconciled",
                    "event_scope": "target",
                    "external_system": "pinvi",
                    "target_key": str(replay_target_id),
                    "target_id": str(replay_map_target_id),
                    "restore_epoch": 7,
                    "source_generation": 1,
                    "target_sequence": 1,
                    "relay_order": 1,
                    "cursor": "cursor-replayed",
                    "source_payload_fingerprint": "73" * 32,
                    "payload_fingerprint": "70" * 32,
                    "payload": _links_reconciled_payload(replay_map_target_id),
                    "occurred_at": occurred_at,
                },
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
                    "relay_order": 2,
                    "cursor": "cursor-reconciled",
                    "source_payload_fingerprint": empty_root,
                    "payload_fingerprint": "71" * 32,
                    "payload": {
                        "actual_merkle_root": empty_root,
                        "expected_merkle_root": empty_root,
                        "request_id": str(request_id),
                        "snapshot_id": str(expected_snapshot_id),
                        "status": "succeeded",
                        "version": "cache-target-reconciliation-v1",
                    },
                    "occurred_at": occurred_at,
                },
            ],
            "idempotent_replay": True,
        }
    )
    calls: list[str] = []
    claim_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal claim_count
        calls.append(request.url.path)
        if request.url.path == "/v1/service/cache-target-streams/pinvi":
            etag = '"pinvi:8"'
            return httpx.Response(
                200,
                headers={"ETag": etag},
                json={
                    "data": {
                        "external_system": "pinvi",
                        "restore_epoch": 7,
                        "control_version": 8,
                        "entity_tag": etag,
                        "state": "ready",
                        "consumer_id": "pinvi-cache-target-consumer",
                        "blocked_event_id": None,
                        "active_reconciliation": None,
                        "updated_at": "2026-07-31T00:00:00Z",
                    },
                    "meta": {},
                },
            )
        if request.url.path == "/v1/service/cache-target-snapshots/pinvi":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "snapshot_id": "snapshot-after-completion",
                        "restore_epoch": 7,
                        "high_watermark_cursor": "cursor-0",
                        "count": 0,
                        "merkle_root": empty_root,
                        "items": [],
                    },
                    "meta": {},
                },
            )
        if request.url.path == "/v1/service/cache-target-event-claims":
            claim_count += 1
            claim = (
                replay_claim.model_dump(mode="json")
                if claim_available and claim_count == 1
                else None
            )
            return httpx.Response(200, json={"data": claim, "meta": {}})
        assert request.url.path == "/v1/service/cache-target-event-acks"
        return httpx.Response(200, json={"data": {"status": "ok"}, "meta": {}})

    observed_ready_during_apply: list[bool] = []

    async def observe_apply(db, claim):  # type: ignore[no-untyped-def]
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        observed_ready_during_apply.append(consumer.ready)
        return await apply_cache_target_claim(db, claim)

    monkeypatch.setattr(
        "app.services.cache_target_sync_worker.apply_cache_target_claim",
        observe_apply,
    )
    client = CacheTargetServiceClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler)),
        role="consumer",
        token="u" * 32,
    )
    try:
        if claim_available:
            await bootstrap_cache_target_sync(
                session_factory,
                consumer_client=client,
                consumer_id="pinvi-cache-target-consumer",
                batch_size=100,
                lease_seconds=60,
                max_attempts=5,
            )
        else:
            with pytest.raises(RuntimeError, match="receipt가 미수신"):
                await bootstrap_cache_target_sync(
                    session_factory,
                    consumer_client=client,
                    consumer_id="pinvi-cache-target-consumer",
                    batch_size=100,
                    lease_seconds=60,
                    max_attempts=5,
                )
    finally:
        await client.aclose()

    expected_calls = [
        "/v1/service/cache-target-streams/pinvi",
        "/v1/service/cache-target-snapshots/pinvi",
        "/v1/service/cache-target-event-claims",
    ]
    if claim_available:
        expected_calls.extend(
            [
                "/v1/service/cache-target-event-acks",
                "/v1/service/cache-target-event-claims",
            ]
        )
    expected_calls.append("/v1/service/cache-target-streams/pinvi")
    assert calls == expected_calls
    assert observed_ready_during_apply == ([False] if claim_available else [])
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        expectation = await db.get(KtmCacheTargetReconciliationExpectation, request_id)
        assert consumer is not None
        assert expectation is not None
        assert consumer.ready is claim_available
        assert consumer.remote_acked_cursor == ("cursor-reconciled" if claim_available else None)
        assert expectation.status == ("received" if claim_available else "pending")


async def test_bootstrap_opens_after_local_receipt_apply_then_reacks_durably(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    request_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    empty_root = hashlib.sha256(b"KTMCTEMPTY\x00").hexdigest()
    claim = CacheTargetClaim.model_validate(
        {
            "claim_id": str(uuid.uuid4()),
            "external_system": "pinvi",
            "consumer_id": "pinvi-cache-target-consumer",
            "lease_token": str(uuid.uuid4()),
            "status": "active",
            "first_relay_order": 1,
            "last_relay_order": 1,
            "acked_through": None,
            "lease_expires_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
            "events": [
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
                    "cursor": "cursor-reconciled",
                    "source_payload_fingerprint": empty_root,
                    "payload_fingerprint": "71" * 32,
                    "payload": {
                        "actual_merkle_root": empty_root,
                        "expected_merkle_root": empty_root,
                        "request_id": str(request_id),
                        "snapshot_id": str(snapshot_id),
                        "status": "succeeded",
                        "version": "cache-target-reconciliation-v1",
                    },
                    "occurred_at": datetime.now(UTC).isoformat(),
                }
            ],
            "idempotent_replay": False,
        }
    )
    async with session_factory() as db:
        db.add(
            KtmCacheTargetConsumer(
                consumer_id="pinvi-cache-target-consumer",
                external_system="pinvi",
                active_restore_epoch=7,
                reconcile_status="matched",
                ready=False,
            )
        )
        db.add(
            KtmCacheTargetReconciliationExpectation(
                request_id=request_id,
                external_system="pinvi",
                snapshot_id=snapshot_id,
                restore_epoch=7,
                snapshot_count=0,
                snapshot_merkle_root=bytes.fromhex(empty_root),
                high_watermark_cursor="cursor-0",
                status="pending",
            )
        )
        await db.flush()
        await apply_cache_target_claim(db, claim)
        await db.commit()

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/v1/service/cache-target-streams/pinvi":
            etag = '"pinvi:8"'
            return httpx.Response(
                200,
                headers={"ETag": etag},
                json={
                    "data": {
                        "external_system": "pinvi",
                        "restore_epoch": 7,
                        "control_version": 8,
                        "entity_tag": etag,
                        "state": "ready",
                        "consumer_id": "pinvi-cache-target-consumer",
                        "blocked_event_id": None,
                        "active_reconciliation": None,
                        "updated_at": "2026-07-31T00:00:00Z",
                    },
                    "meta": {},
                },
            )
        if request.url.path == "/v1/service/cache-target-snapshots/pinvi":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "snapshot_id": "snapshot-after-local-apply",
                        "restore_epoch": 7,
                        "high_watermark_cursor": "cursor-0",
                        "count": 0,
                        "merkle_root": empty_root,
                        "items": [],
                    },
                    "meta": {},
                },
            )
        assert request.url.path == "/v1/service/cache-target-event-acks"
        return httpx.Response(200, json={"data": {"status": "ok"}, "meta": {}})

    client = CacheTargetServiceClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler)),
        role="consumer",
        token="u" * 32,
    )
    try:
        await bootstrap_cache_target_sync(
            session_factory,
            consumer_client=client,
            consumer_id="pinvi-cache-target-consumer",
            batch_size=100,
            lease_seconds=60,
            max_attempts=5,
        )
        assert calls == [
            "/v1/service/cache-target-streams/pinvi",
            "/v1/service/cache-target-snapshots/pinvi",
        ]
        async with session_factory() as db:
            consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
            expectation = await db.get(KtmCacheTargetReconciliationExpectation, request_id)
            assert consumer is not None
            assert expectation is not None
            assert consumer.ready is True
            assert consumer.remote_acked_cursor is None
            assert expectation.status == "received"

        assert await consume_cache_target_once(
            session_factory,
            client=client,
            consumer_id="pinvi-cache-target-consumer",
            batch_size=100,
            lease_seconds=60,
            max_attempts=5,
        )
    finally:
        await client.aclose()

    assert calls[-1] == "/v1/service/cache-target-event-acks"
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        assert consumer.ready is True
        assert consumer.remote_acked_cursor == "cursor-reconciled"


@pytest.mark.parametrize(
    ("initial_state", "blocked_event_id"),
    [
        ("fenced", None),
        ("blocked", uuid.uuid4()),
    ],
)
async def test_bootstrap_completes_request_bound_snapshot_before_local_ready(
    session_factory,
    initial_state: str,
    blocked_event_id: uuid.UUID | None,
) -> None:  # type: ignore[no-untyped-def]
    request_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    generic_snapshot_id = uuid.uuid4()
    empty_root = hashlib.sha256(b"KTMCTEMPTY\x00").hexdigest()
    calls: list[str] = []
    replay_target_key = uuid.uuid4()
    replay_map_target_id = uuid.uuid4()
    replay_claim = CacheTargetClaim.model_validate(
        {
            "claim_id": str(uuid.uuid4()),
            "external_system": "pinvi",
            "consumer_id": "pinvi-cache-target-consumer",
            "lease_token": str(uuid.uuid4()),
            "status": "active",
            "first_relay_order": 1,
            "last_relay_order": 2,
            "acked_through": None,
            "lease_expires_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
            "events": [
                {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "cache_target.links_reconciled",
                    "event_scope": "target",
                    "external_system": "pinvi",
                    "target_key": str(replay_target_key),
                    "target_id": str(replay_map_target_id),
                    "restore_epoch": 7,
                    "source_generation": 1,
                    "target_sequence": 1,
                    "relay_order": 1,
                    "cursor": "cursor-replayed",
                    "source_payload_fingerprint": "73" * 32,
                    "payload_fingerprint": "70" * 32,
                    "payload": _links_reconciled_payload(replay_map_target_id),
                    "occurred_at": datetime.now(UTC).isoformat(),
                },
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
                    "relay_order": 2,
                    "cursor": "cursor-reconciled",
                    "source_payload_fingerprint": empty_root,
                    "payload_fingerprint": "71" * 32,
                    "payload": {
                        "actual_merkle_root": empty_root,
                        "expected_merkle_root": empty_root,
                        "request_id": str(request_id),
                        "snapshot_id": str(snapshot_id),
                        "status": "succeeded",
                        "version": "cache-target-reconciliation-v1",
                    },
                    "occurred_at": datetime.now(UTC).isoformat(),
                },
            ],
            "idempotent_replay": False,
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/v1/service/cache-target-streams/pinvi":
            completed = calls.count(request.url.path) >= 2
            etag = '"pinvi:8"' if completed else '"pinvi:7"'
            return httpx.Response(
                200,
                headers={"ETag": etag},
                json={
                    "data": {
                        "external_system": "pinvi",
                        "restore_epoch": 7,
                        "control_version": 8 if completed else 7,
                        "entity_tag": etag,
                        "state": "ready" if completed else initial_state,
                        "consumer_id": "pinvi-cache-target-consumer",
                        "blocked_event_id": (
                            None if completed or blocked_event_id is None else str(blocked_event_id)
                        ),
                        "active_reconciliation": (
                            None
                            if completed
                            else {
                                "request_id": str(request_id),
                                "status": "running",
                                "snapshot_id": str(snapshot_id),
                                "restore_epoch": 7,
                                "count": 0,
                                "merkle_root": empty_root,
                                "high_watermark_cursor": "cursor-0",
                                "entity_tag": f'"{request_id}:2"',
                                "stream_entity_tag": etag,
                                "created_at": "2026-07-31T00:00:00Z",
                            }
                        ),
                        "updated_at": "2026-07-31T00:00:00Z",
                    },
                    "meta": {},
                },
            )
        if request.url.path.endswith(f"/{request_id}/snapshot"):
            assert dict(request.url.params) == {"page_size": "1000"}
            return httpx.Response(
                200,
                json={
                    "data": {
                        "snapshot_id": str(snapshot_id),
                        "restore_epoch": 7,
                        "high_watermark_cursor": "cursor-0",
                        "count": 0,
                        "merkle_root": empty_root,
                        "items": [],
                    },
                    "meta": {"page": {"next_cursor": None}},
                },
            )
        if request.url.path == "/v1/service/cache-target-snapshots/pinvi":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "snapshot_id": str(generic_snapshot_id),
                        "restore_epoch": 7,
                        "high_watermark_cursor": "cursor-1",
                        "count": 0,
                        "merkle_root": empty_root,
                        "items": [],
                    },
                    "meta": {},
                },
            )
        if request.url.path == "/v1/service/cache-target-event-claims":
            if blocked_event_id is not None and calls.count(request.url.path) == 1:
                return httpx.Response(
                    200,
                    json={"data": replay_claim.model_dump(mode="json"), "meta": {}},
                )
            return httpx.Response(200, json={"data": None, "meta": {}})
        if request.url.path == "/v1/service/cache-target-event-acks":
            return httpx.Response(200, json={"data": {"status": "ok"}, "meta": {}})
        assert request.url.path.endswith(f"/{request_id}/completions")
        completion = json.loads(request.content)
        assert completion == {
            "external_system": "pinvi",
            "consumer_id": "pinvi-cache-target-consumer",
            "snapshot_id": str(snapshot_id),
            "expected_restore_epoch": 7,
            "actual_merkle_root": empty_root,
        }
        return httpx.Response(
            200,
            json={
                "data": {
                    "operation_id": str(request_id),
                    "status": "succeeded",
                    "snapshot_id": str(snapshot_id),
                    "status_url": None,
                },
                "meta": {},
            },
        )

    client = CacheTargetServiceClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler)),
        role="consumer",
        token="u" * 32,
    )
    try:
        await bootstrap_cache_target_sync(
            session_factory,
            consumer_client=client,
            consumer_id="pinvi-cache-target-consumer",
            batch_size=100,
            lease_seconds=60,
            max_attempts=5,
        )
        await bootstrap_cache_target_sync(
            session_factory,
            consumer_client=client,
            consumer_id="pinvi-cache-target-consumer",
            batch_size=100,
            lease_seconds=60,
            max_attempts=5,
        )
    finally:
        await client.aclose()

    expected_calls = [
        "/v1/service/cache-target-streams/pinvi",
        f"/v1/service/cache-target-reconciliations/{request_id}/snapshot",
        f"/v1/service/cache-target-reconciliations/{request_id}/completions",
        "/v1/service/cache-target-streams/pinvi",
    ]
    if blocked_event_id is not None:
        expected_calls.extend(
            [
                "/v1/service/cache-target-event-claims",
                "/v1/service/cache-target-event-acks",
                "/v1/service/cache-target-event-claims",
                "/v1/service/cache-target-streams/pinvi",
            ]
        )
    expected_calls.extend(
        [
            "/v1/service/cache-target-streams/pinvi",
            "/v1/service/cache-target-snapshots/pinvi",
        ]
    )
    assert calls == expected_calls
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        assert consumer.snapshot_id == str(generic_snapshot_id)
        assert consumer.ready is True
        assert consumer.stream_control_etag == '"pinvi:8"'
        assert consumer.remote_acked_cursor == (
            "cursor-reconciled" if blocked_event_id is not None else None
        )
        expectation = await db.get(KtmCacheTargetReconciliationExpectation, request_id)
        assert expectation is not None
        assert expectation.snapshot_id == snapshot_id
        assert expectation.snapshot_merkle_root == bytes.fromhex(empty_root)
        assert expectation.status == ("received" if blocked_event_id is not None else "pending")


async def test_bootstrap_rejects_blocked_stream_without_active_reconciliation(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    blocked_event_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/service/cache-target-streams/pinvi"
        etag = '"pinvi:7"'
        return httpx.Response(
            200,
            headers={"ETag": etag},
            json={
                "data": {
                    "external_system": "pinvi",
                    "restore_epoch": 7,
                    "control_version": 7,
                    "entity_tag": etag,
                    "state": "blocked",
                    "consumer_id": "pinvi-cache-target-consumer",
                    "blocked_event_id": str(blocked_event_id),
                    "active_reconciliation": None,
                    "updated_at": "2026-07-31T00:00:00Z",
                },
                "meta": {},
            },
        )

    client = CacheTargetServiceClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler)),
        role="consumer",
        token="u" * 32,
    )
    try:
        with pytest.raises(RuntimeError, match="blocked"):
            await bootstrap_cache_target_sync(
                session_factory,
                consumer_client=client,
                consumer_id="pinvi-cache-target-consumer",
                batch_size=100,
                lease_seconds=60,
                max_attempts=5,
            )
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    ("state", "has_block", "active_status", "error_pattern"),
    [
        ("blocked", True, "preparing", "preparing reconciliation"),
        ("blocked", False, "running", "fenced 상태"),
        ("fenced", True, "running", "blocked 상태"),
        ("ready", False, "running", "fenced 상태"),
    ],
)
async def test_bootstrap_rejects_inconsistent_active_reconciliation_state(
    session_factory,
    state: str,
    has_block: bool,
    active_status: str,
    error_pattern: str,
) -> None:  # type: ignore[no-untyped-def]
    request_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    empty_root = hashlib.sha256(b"KTMCTEMPTY\x00").hexdigest()
    active: dict[str, object] = {
        "request_id": str(request_id),
        "status": active_status,
        "restore_epoch": 7,
        "entity_tag": f'"{request_id}:1"',
        "stream_entity_tag": '"pinvi:7"',
        "created_at": "2026-07-31T00:00:00Z",
    }
    if active_status == "running":
        active.update(
            {
                "snapshot_id": str(snapshot_id),
                "count": 0,
                "merkle_root": empty_root,
                "high_watermark_cursor": "cursor-0",
            }
        )
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.url.path == "/v1/service/cache-target-streams/pinvi"
        etag = '"pinvi:7"'
        return httpx.Response(
            200,
            headers={"ETag": etag},
            json={
                "data": {
                    "external_system": "pinvi",
                    "restore_epoch": 7,
                    "control_version": 7,
                    "entity_tag": etag,
                    "state": state,
                    "consumer_id": "pinvi-cache-target-consumer",
                    "blocked_event_id": str(uuid.uuid4()) if has_block else None,
                    "active_reconciliation": active,
                    "updated_at": "2026-07-31T00:00:00Z",
                },
                "meta": {},
            },
        )

    client = CacheTargetServiceClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler)),
        role="consumer",
        token="u" * 32,
    )
    try:
        with pytest.raises(RuntimeError, match=error_pattern):
            await bootstrap_cache_target_sync(
                session_factory,
                consumer_client=client,
                consumer_id="pinvi-cache-target-consumer",
                batch_size=100,
                lease_seconds=60,
                max_attempts=5,
            )
    finally:
        await client.aclose()

    assert calls == ["/v1/service/cache-target-streams/pinvi"]


@pytest.mark.parametrize("failure_mode", ["completion_error", "confirmation_stale"])
async def test_bootstrap_terminal_race_keeps_local_consumer_unready(
    session_factory,
    failure_mode: str,
) -> None:  # type: ignore[no-untyped-def]
    request_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    blocked_event_id = uuid.uuid4()
    empty_root = hashlib.sha256(b"KTMCTEMPTY\x00").hexdigest()

    def running_stream() -> httpx.Response:
        etag = '"pinvi:7"'
        return httpx.Response(
            200,
            headers={"ETag": etag},
            json={
                "data": {
                    "external_system": "pinvi",
                    "restore_epoch": 7,
                    "control_version": 7,
                    "entity_tag": etag,
                    "state": "blocked",
                    "consumer_id": "pinvi-cache-target-consumer",
                    "blocked_event_id": str(blocked_event_id),
                    "active_reconciliation": {
                        "request_id": str(request_id),
                        "status": "running",
                        "snapshot_id": str(snapshot_id),
                        "restore_epoch": 7,
                        "count": 0,
                        "merkle_root": empty_root,
                        "high_watermark_cursor": "cursor-0",
                        "entity_tag": f'"{request_id}:2"',
                        "stream_entity_tag": etag,
                        "created_at": "2026-07-31T00:00:00Z",
                    },
                    "updated_at": "2026-07-31T00:00:00Z",
                },
                "meta": {},
            },
        )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/service/cache-target-streams/pinvi":
            return running_stream()
        if request.url.path.endswith(f"/{request_id}/snapshot"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "snapshot_id": str(snapshot_id),
                        "restore_epoch": 7,
                        "high_watermark_cursor": "cursor-0",
                        "count": 0,
                        "merkle_root": empty_root,
                        "items": [],
                    },
                    "meta": {"page": {"next_cursor": None}},
                },
            )
        assert request.url.path.endswith(f"/{request_id}/completions")
        if failure_mode == "completion_error":
            return httpx.Response(
                409,
                json={
                    "type": "about:blank",
                    "title": "Conflict",
                    "status": 409,
                    "code": "reconciliation_dead_letters_remain",
                    "detail": "dead letters remain",
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "operation_id": str(request_id),
                    "status": "succeeded",
                    "snapshot_id": str(snapshot_id),
                    "status_url": None,
                },
                "meta": {},
            },
        )

    client = CacheTargetServiceClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler)),
        role="consumer",
        token="u" * 32,
    )
    try:
        if failure_mode == "completion_error":
            with pytest.raises(CacheTargetServiceProblem) as caught:
                await bootstrap_cache_target_sync(
                    session_factory,
                    consumer_client=client,
                    consumer_id="pinvi-cache-target-consumer",
                    batch_size=100,
                    lease_seconds=60,
                    max_attempts=5,
                )
            assert caught.value.code == "reconciliation_dead_letters_remain"
        else:
            with pytest.raises(RuntimeError, match="ready 전이"):
                await bootstrap_cache_target_sync(
                    session_factory,
                    consumer_client=client,
                    consumer_id="pinvi-cache-target-consumer",
                    batch_size=100,
                    lease_seconds=60,
                    max_attempts=5,
                )
    finally:
        await client.aclose()

    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        assert consumer.reconcile_status == "matched"
        assert consumer.ready is False


async def test_mid_claim_permanent_failure_acks_prefix_before_nack(session_factory) -> None:  # type: ignore[no-untyped-def]
    await _seed_ready_consumer(session_factory)
    claim = _claim_with_mid_stream_poison()
    calls: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append((request.url.path, body))
        if request.url.path.endswith("event-claims"):
            return httpx.Response(200, json={"data": claim.model_dump(mode="json"), "meta": {}})
        return httpx.Response(200, json={"data": {"status": "ok"}, "meta": {}})

    client = CacheTargetServiceClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler)),
        role="consumer",
        token="u" * 32,
    )
    try:
        assert await consume_cache_target_once(
            session_factory,
            client=client,
            consumer_id="pinvi-cache-target-consumer",
            batch_size=100,
            lease_seconds=60,
            max_attempts=5,
        )
    finally:
        await client.aclose()

    assert [path for path, _ in calls] == [
        "/v1/service/cache-target-event-claims",
        "/v1/service/cache-target-event-acks",
        "/v1/service/cache-target-event-nacks",
    ]
    assert calls[1][1]["through_cursor"] == "cursor-1"
    assert calls[2][1]["event_id"] == str(claim.events[1].event_id)
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        assert consumer.local_applied_cursor == "cursor-1"
        assert consumer.remote_acked_cursor == "cursor-1"
        assert consumer.ready is False
        assert consumer.reconcile_status == "blocked"


async def test_mid_claim_prefix_ack_guard_fails_consumer_closed(session_factory) -> None:  # type: ignore[no-untyped-def]
    await _seed_ready_consumer(session_factory)
    claim = _claim_with_mid_stream_poison()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("event-claims"):
            return httpx.Response(200, json={"data": claim.model_dump(mode="json"), "meta": {}})
        if request.url.path.endswith("event-nacks"):
            return httpx.Response(
                409,
                json={
                    "type": "about:blank",
                    "title": "Conflict",
                    "status": 409,
                    "code": "dead_letter_requires_prefix_ack",
                    "detail": "prefix ACK required",
                },
            )
        return httpx.Response(200, json={"data": {"status": "ok"}, "meta": {}})

    client = CacheTargetServiceClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler)),
        role="consumer",
        token="u" * 32,
    )
    try:
        with pytest.raises(CacheTargetServiceProblem) as caught:
            await consume_cache_target_once(
                session_factory,
                client=client,
                consumer_id="pinvi-cache-target-consumer",
                batch_size=100,
                lease_seconds=60,
                max_attempts=5,
            )
    finally:
        await client.aclose()

    assert caught.value.code == "dead_letter_requires_prefix_ack"
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        assert consumer.ready is False
        assert consumer.reconcile_status == "blocked"


async def test_recovery_drain_db_failure_nacks_then_blocks_local_readiness(
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_ready_consumer(session_factory)
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        consumer.ready = False
        await db.commit()

    claim = _claim_with_mid_stream_poison()
    calls: list[str] = []
    nack_bodies: list[dict[str, object]] = []

    async def fail_apply(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise DBAPIError("apply", {}, RuntimeError("transient database failure"), False)

    monkeypatch.setattr(
        "app.services.cache_target_sync_worker.apply_cache_target_claim",
        fail_apply,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("event-claims"):
            return httpx.Response(
                200,
                json={"data": claim.model_dump(mode="json"), "meta": {}},
            )
        assert request.url.path.endswith("event-nacks")
        nack_bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"data": {"status": "ok"}, "meta": {}})

    client = CacheTargetServiceClient(
        httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler)),
        role="consumer",
        token="u" * 32,
    )
    try:
        with pytest.raises(CacheTargetConsumerError, match="blocked replay drain"):
            await consume_cache_target_once(
                session_factory,
                client=client,
                consumer_id="pinvi-cache-target-consumer",
                batch_size=100,
                lease_seconds=60,
                max_attempts=5,
                recovery_drain=True,
            )
    finally:
        await client.aclose()

    assert calls == [
        "/v1/service/cache-target-event-claims",
        "/v1/service/cache-target-event-nacks",
    ]
    assert len(nack_bodies) == 1
    assert nack_bodies[0]["disposition"] == "transient"
    assert nack_bodies[0]["error_code"] == "PINVI_APPLY_TRANSIENT"
    assert nack_bodies[0]["max_attempts"] == 5
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        assert consumer.ready is False
        assert consumer.reconcile_status == "blocked"
