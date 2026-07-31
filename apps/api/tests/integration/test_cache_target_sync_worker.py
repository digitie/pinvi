"""cache target startup epoch/snapshot fail-closed bootstrap."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.clients.kor_travel_map_cache_target import (
    CacheTargetServiceClient,
    CacheTargetServiceProblem,
)
from app.models.cache_target_sync import KtmCacheTargetConsumer
from app.services.cache_target_event_consumer import CacheTargetClaim, CacheTargetEventRecord
from app.services.cache_target_sync_worker import (
    bootstrap_cache_target_sync,
    consume_cache_target_once,
)

pytestmark = pytest.mark.asyncio


def _claim_with_mid_stream_poison() -> CacheTargetClaim:
    occurred_at = datetime.now(UTC).isoformat()
    first = CacheTargetEventRecord.model_validate(
        {
            "event_id": str(uuid.uuid4()),
            "event_type": "cache_target.state_applied",
            "event_scope": "target",
            "external_system": "pinvi",
            "target_key": str(uuid.uuid4()),
            "target_id": str(uuid.uuid4()),
            "restore_epoch": 7,
            "source_generation": 1,
            "target_sequence": 1,
            "relay_order": 1,
            "cursor": "cursor-1",
            "source_payload_fingerprint": "73" * 32,
            "payload_fingerprint": "70" * 32,
            "payload": {"status": "applied"},
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
            "source_payload_fingerprint": None,
            "payload_fingerprint": "71" * 32,
            "payload": {
                "snapshot_id": "wrong-snapshot",
                "count": 0,
                "merkle_root": (b"r" * 32).hex(),
                "high_watermark_cursor": "cursor-2",
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


async def test_bootstrap_completes_request_bound_snapshot_before_local_ready(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    request_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    empty_root = hashlib.sha256(b"KTMCTEMPTY\x00").hexdigest()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/v1/service/cache-target-streams/pinvi":
            completed = calls.count(request.url.path) == 2
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
                        "state": "ready" if completed else "fenced",
                        "consumer_id": "pinvi-cache-target-consumer",
                        "blocked_event_id": None,
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
        )
    finally:
        await client.aclose()

    assert calls == [
        "/v1/service/cache-target-streams/pinvi",
        f"/v1/service/cache-target-reconciliations/{request_id}/snapshot",
        f"/v1/service/cache-target-reconciliations/{request_id}/completions",
        "/v1/service/cache-target-streams/pinvi",
    ]
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        assert consumer.snapshot_id == str(snapshot_id)
        assert consumer.ready is True
        assert consumer.stream_control_etag == '"pinvi:8"'


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
