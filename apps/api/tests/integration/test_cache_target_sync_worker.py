"""cache target startup epoch/snapshot fail-closed bootstrap."""

from __future__ import annotations

import hashlib

import httpx
import pytest

from app.clients.kor_travel_map_cache_target import CacheTargetServiceClient
from app.models.cache_target_sync import KtmCacheTargetConsumer
from app.services.cache_target_sync_worker import bootstrap_cache_target_sync

pytestmark = pytest.mark.asyncio


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
