"""cache generation multi-process 관찰과 비밀 없는 health projection."""

from __future__ import annotations

from app.api.v1.healthz import cache_target_sync_health
from app.models.cache_target_sync import KtmCacheTargetConsumer
from app.services.feature_cache import CachedFeature, FeatureCache, FeatureCacheGenerationObserver


async def test_each_process_observer_clears_only_after_its_own_generation_observation(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        db.add(
            KtmCacheTargetConsumer(
                consumer_id="pinvi-cache-target-consumer",
                external_system="pinvi",
                active_restore_epoch=7,
                feature_cache_generation=0,
            )
        )
        await db.commit()

    caches = [FeatureCache(ttl_seconds=60, max_size=10) for _ in range(2)]
    observers = [FeatureCacheGenerationObserver(cache) for cache in caches]
    for cache in caches:
        cache.put_many({"feature-1": CachedFeature(trip_card={"name": "old"}, row_revision=1)})
    async with session_factory() as db:
        for observer in observers:
            assert await observer.observe(db, consumer_id="pinvi-cache-target-consumer") == (7, 0)

    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        consumer.feature_cache_generation = 1
        await db.commit()

    async with session_factory() as db:
        assert await observers[0].observe(db, consumer_id="pinvi-cache-target-consumer") == (7, 1)
        assert caches[0].get_many(["feature-1"])[2] == ["feature-1"]
        assert caches[1].get_many(["feature-1"])[0]["feature-1"].row_revision == 1
        assert await observers[1].observe(db, consumer_id="pinvi-cache-target-consumer") == (7, 1)
        assert caches[1].get_many(["feature-1"])[2] == ["feature-1"]

    caches[0].put_many({"feature-1": CachedFeature(trip_card={"name": "stale"}, row_revision=2)})
    async with session_factory() as db:
        consumer = await db.get(KtmCacheTargetConsumer, "pinvi-cache-target-consumer")
        assert consumer is not None
        await db.delete(consumer)
        await db.commit()
    async with session_factory() as db:
        assert await observers[0].observe(db, consumer_id="pinvi-cache-target-consumer") is None
        assert caches[0].get_many(["feature-1"])[2] == ["feature-1"]


async def test_cache_target_health_is_default_off_and_contains_no_credentials(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        response = await cache_target_sync_health(db)

    assert response.enabled is False
    assert response.ready is False
    assert response.disabled_reason == "network_disabled_by_default"
    assert "token" not in response.model_dump_json().lower()
    assert "host" not in response.model_dump_json().lower()
