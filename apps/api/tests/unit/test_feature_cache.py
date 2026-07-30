"""Feature TTL/LRU 캐시 단위 테스트 (T-146 / D-26)."""

from __future__ import annotations

from app.services.feature_cache import CachedFeature, FeatureCache


def test_fresh_stale_and_miss_split() -> None:
    cache = FeatureCache(ttl_seconds=100.0, max_size=10)
    cache.put_many(
        {
            "a": CachedFeature(trip_card={"feature_id": "a"}, row_revision=1),
            "b": CachedFeature(trip_card={"feature_id": "b"}, row_revision=2),
        }
    )
    fresh, stale, misses = cache.get_many(["a", "b", "c"])
    assert set(fresh) == {"a", "b"}
    assert stale == {}
    assert misses == ["c"]
    assert fresh["a"].trip_card["feature_id"] == "a"
    assert fresh["b"].row_revision == 2


def test_ttl_zero_is_immediate_stale_hit() -> None:
    cache = FeatureCache(ttl_seconds=0.0, max_size=10)
    cached = CachedFeature(trip_card={"feature_id": "a"}, row_revision=3)
    cache.put_many({"a": cached})
    fresh, stale, misses = cache.get_many(["a"])
    assert fresh == {}
    assert stale == {"a": cached}
    assert misses == []


def test_lru_eviction_by_max_size() -> None:
    cache = FeatureCache(ttl_seconds=100.0, max_size=2)
    cache.put_many({"a": CachedFeature(trip_card={"feature_id": "a"}, row_revision=1)})
    cache.put_many({"b": CachedFeature(trip_card={"feature_id": "b"}, row_revision=1)})
    cache.put_many({"c": CachedFeature(trip_card={"feature_id": "c"}, row_revision=1)})
    fresh, stale, misses = cache.get_many(["a", "b", "c"])
    assert set(fresh) == {"b", "c"}
    assert stale == {}
    assert misses == ["a"]


def test_clear() -> None:
    cache = FeatureCache(ttl_seconds=100.0, max_size=10)
    cache.put_many({"a": CachedFeature(trip_card={"feature_id": "a"}, row_revision=1)})
    cache.clear()
    fresh, stale, misses = cache.get_many(["a"])
    assert fresh == {}
    assert stale == {}
    assert misses == ["a"]
