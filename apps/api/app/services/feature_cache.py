"""Feature 조회 process-local TTL 캐시 (T-146 / D-26).

trip view마다 kor-travel-map을 재호출하는 단일 노드 hotspot을 완화한다. feature_id(불투명 문자열,
canonical) → ``trip_card + row_revision``을 짧은 TTL로 캐시한다. 만료 entry는 버리지 않고
conditional batch validator와 transport 실패 시 stale snapshot으로 재사용한다.
멀티 워커 간 공유는 하지 않는다(프로세스 로컬). 동시성 race는 캐시 특성상 무해(중복 fetch 정도).
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.core.config import settings


@dataclass(frozen=True)
class CachedFeature:
    trip_card: dict[str, Any]
    row_revision: int


class FeatureCache:
    """revision-aware TTL + LRU(maxsize) 캐시. monotonic clock 기반."""

    def __init__(self, *, ttl_seconds: float, max_size: int) -> None:
        self._ttl = ttl_seconds
        self._max_size = max(1, max_size)
        # feature_id -> (expires_at_monotonic, revision-aware trip_card)
        self._store: OrderedDict[str, tuple[float, CachedFeature]] = OrderedDict()

    def get_many(
        self,
        feature_ids: Iterable[str],
    ) -> tuple[dict[str, CachedFeature], dict[str, CachedFeature], list[str]]:
        """fresh hit, validator로 재검증할 stale hit, 완전 miss를 분리한다."""
        now = time.monotonic()
        fresh: dict[str, CachedFeature] = {}
        stale: dict[str, CachedFeature] = {}
        misses: list[str] = []
        for fid in feature_ids:
            entry = self._store.get(fid)
            if entry is None:
                misses.append(fid)
            else:
                self._store.move_to_end(fid)
                target = fresh if entry[0] > now else stale
                target[fid] = entry[1]
        return fresh, stale, misses

    def put_many(self, features: Mapping[str, CachedFeature]) -> None:
        expires_at = time.monotonic() + self._ttl
        for fid, feature in features.items():
            self._store[fid] = (expires_at, feature)
            self._store.move_to_end(fid)
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)  # 가장 오래된 것 evict

    def discard_many(self, feature_ids: Iterable[str]) -> None:
        for feature_id in feature_ids:
            self._store.pop(feature_id, None)

    def clear(self) -> None:
        self._store.clear()


feature_cache = FeatureCache(
    ttl_seconds=settings.pinvi_feature_cache_ttl_seconds,
    max_size=settings.pinvi_feature_cache_max_size,
)
