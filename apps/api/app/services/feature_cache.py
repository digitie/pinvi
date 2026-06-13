"""Feature 조회 process-local TTL 캐시 (T-146 / D-26).

trip view마다 kor-travel-map을 재호출하는 단일 노드 hotspot을 완화한다. feature_id(불투명 문자열,
canonical) → feature dict를 짧은 TTL로 캐시하고, miss만 라이브러리에서 가져온다.
멀티 워커 간 공유는 하지 않는다(프로세스 로컬). 동시성 race는 캐시 특성상 무해(중복 fetch 정도).
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Iterable
from typing import Any

from app.core.config import settings


class FeatureCache:
    """단순 TTL + LRU(maxsize) 캐시. monotonic clock 기반."""

    def __init__(self, *, ttl_seconds: float, max_size: int) -> None:
        self._ttl = ttl_seconds
        self._max_size = max(1, max_size)
        # feature_id -> (expires_at_monotonic, feature)
        self._store: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()

    def get_many(self, feature_ids: Iterable[str]) -> tuple[dict[str, dict[str, Any]], list[str]]:
        """캐시 hit(만료 안 된 것)과 miss(재조회 필요) 분리."""
        now = time.monotonic()
        hits: dict[str, dict[str, Any]] = {}
        misses: list[str] = []
        for fid in feature_ids:
            entry = self._store.get(fid)
            if entry is not None and entry[0] > now:
                self._store.move_to_end(fid)  # LRU 갱신
                hits[fid] = entry[1]
            else:
                if entry is not None:
                    self._store.pop(fid, None)  # 만료 정리
                misses.append(fid)
        return hits, misses

    def put_many(self, features: dict[str, dict[str, Any]]) -> None:
        expires_at = time.monotonic() + self._ttl
        for fid, feature in features.items():
            self._store[fid] = (expires_at, feature)
            self._store.move_to_end(fid)
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)  # 가장 오래된 것 evict

    def clear(self) -> None:
        self._store.clear()


feature_cache = FeatureCache(
    ttl_seconds=settings.pinvi_feature_cache_ttl_seconds,
    max_size=settings.pinvi_feature_cache_max_size,
)
