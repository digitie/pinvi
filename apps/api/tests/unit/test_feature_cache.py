"""Feature TTL/LRU 캐시 단위 테스트 (T-146 / D-26)."""

from __future__ import annotations

from app.services.feature_cache import FeatureCache


def test_hit_and_miss_split() -> None:
    cache = FeatureCache(ttl_seconds=100.0, max_size=10)
    cache.put_many({"a": {"feature_id": "a"}, "b": {"feature_id": "b"}})
    hits, misses = cache.get_many(["a", "b", "c"])
    assert set(hits) == {"a", "b"}
    assert misses == ["c"]
    assert hits["a"]["feature_id"] == "a"


def test_ttl_zero_is_immediate_miss() -> None:
    cache = FeatureCache(ttl_seconds=0.0, max_size=10)
    cache.put_many({"a": {"feature_id": "a"}})
    hits, misses = cache.get_many(["a"])
    assert hits == {}
    assert misses == ["a"]


def test_lru_eviction_by_max_size() -> None:
    cache = FeatureCache(ttl_seconds=100.0, max_size=2)
    cache.put_many({"a": {"feature_id": "a"}})
    cache.put_many({"b": {"feature_id": "b"}})
    cache.put_many({"c": {"feature_id": "c"}})  # a 가 evict
    hits, misses = cache.get_many(["a", "b", "c"])
    assert set(hits) == {"b", "c"}
    assert misses == ["a"]


def test_clear() -> None:
    cache = FeatureCache(ttl_seconds=100.0, max_size=10)
    cache.put_many({"a": {"feature_id": "a"}})
    cache.clear()
    _, misses = cache.get_many(["a"])
    assert misses == ["a"]
