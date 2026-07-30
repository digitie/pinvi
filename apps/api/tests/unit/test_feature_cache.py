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


def test_older_positive_revision_cannot_replace_newer_cache() -> None:
    cache = FeatureCache(ttl_seconds=100.0, max_size=10)
    newer = CachedFeature(trip_card={"feature_id": "a", "name": "new"}, row_revision=2)
    older = CachedFeature(trip_card={"feature_id": "a", "name": "old"}, row_revision=1)
    cache.put_many({"a": newer})
    cache.put_many({"a": older})

    fresh, stale, misses = cache.get_many(["a"])
    assert fresh == {"a": newer}
    assert stale == {}
    assert misses == []


def test_terminal_revision_fence_blocks_late_found_and_allows_newer_revision() -> None:
    cache = FeatureCache(ttl_seconds=100.0, max_size=10)
    old_refresh = cache.begin_refresh(["a"])
    terminal_refresh = cache.begin_refresh(["a"])
    cache.invalidate_many({"a": 2}, refresh=terminal_refresh)
    cache.put_many(
        {"a": CachedFeature(trip_card={"feature_id": "a"}, row_revision=1)},
        refresh=old_refresh,
    )
    assert cache.get_many(["a"]) == ({}, {}, ["a"])

    recovered_refresh = cache.begin_refresh(["a"])
    recovered = CachedFeature(trip_card={"feature_id": "a"}, row_revision=3)
    cache.put_many({"a": recovered}, refresh=recovered_refresh)
    assert cache.get_many(["a"]) == ({"a": recovered}, {}, [])


def test_new_refresh_recovers_same_revision_after_terminal_state() -> None:
    cache = FeatureCache(ttl_seconds=100.0, max_size=10)
    terminal_refresh = cache.begin_refresh(["a"])
    cache.invalidate_many({"a": 2}, refresh=terminal_refresh)

    recovered_refresh = cache.begin_refresh(["a"])
    recovered = CachedFeature(trip_card={"feature_id": "a"}, row_revision=2)
    cache.put_many({"a": recovered}, refresh=recovered_refresh)

    assert cache.get_many(["a"]) == ({"a": recovered}, {}, [])


def test_new_refresh_recovers_lower_revision_after_missing_recreation() -> None:
    cache = FeatureCache(ttl_seconds=100.0, max_size=10)
    terminal_refresh = cache.begin_refresh(["a"])
    cache.invalidate_many({"a": 3}, refresh=terminal_refresh)
    missing_refresh = cache.begin_refresh(["a"])
    cache.invalidate_many({"a": None}, refresh=missing_refresh)

    recovered_refresh = cache.begin_refresh(["a"])
    recovered = CachedFeature(trip_card={"feature_id": "a"}, row_revision=1)
    cache.put_many({"a": recovered}, refresh=recovered_refresh)

    assert cache.get_many(["a"]) == ({"a": recovered}, {}, [])


def test_missing_refresh_blocks_older_in_flight_found_without_revision() -> None:
    cache = FeatureCache(ttl_seconds=100.0, max_size=10)
    old_refresh = cache.begin_refresh(["a"])
    missing_refresh = cache.begin_refresh(["a"])
    cache.invalidate_many({"a": None}, refresh=missing_refresh)
    cache.put_many(
        {"a": CachedFeature(trip_card={"feature_id": "a"}, row_revision=1)},
        refresh=old_refresh,
    )
    assert cache.get_many(["a"]) == ({}, {}, ["a"])
