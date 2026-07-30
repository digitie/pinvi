"""Feature 조회 process-local TTL 캐시 (T-146 / D-26).

trip view마다 kor-travel-map을 재호출하는 단일 노드 hotspot을 완화한다. feature_id(불투명 문자열,
canonical) → ``trip_card + row_revision``을 짧은 TTL로 캐시한다. 만료 entry는 버리지 않고
conditional batch validator와 transport 실패 시 stale snapshot으로 재사용한다.
멀티 워커 간 공유는 하지 않는다(프로세스 로컬). 같은 프로세스의 동시 refresh는 시작 sequence와
revision fence로 늦은 이전 응답의 상태 역행을 막는다.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from app.core.config import settings


@dataclass(frozen=True)
class CachedFeature:
    trip_card: dict[str, Any]
    row_revision: int


@dataclass(frozen=True)
class _CacheRecord:
    expires_at: float
    feature: CachedFeature | None
    latest_refresh: int
    revision_fence: int | None


class FeatureCache:
    """revision/refresh 순서를 보존하는 TTL + LRU(maxsize) 캐시."""

    def __init__(self, *, ttl_seconds: float, max_size: int) -> None:
        self._ttl = ttl_seconds
        self._max_size = max(1, max_size)
        self._store: OrderedDict[str, _CacheRecord] = OrderedDict()
        self._refresh_sequence = 0

    def _trim(self) -> None:
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

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
            if entry is None or entry.feature is None:
                misses.append(fid)
            else:
                self._store.move_to_end(fid)
                target = fresh if entry.expires_at > now else stale
                target[fid] = entry.feature
        return fresh, stale, misses

    def begin_refresh(self, feature_ids: Iterable[str]) -> int:
        """refresh 시작 순서를 기록해 늦게 도착한 이전 응답의 적용을 막는다."""
        self._refresh_sequence += 1
        refresh = self._refresh_sequence
        now = time.monotonic()
        for feature_id in feature_ids:
            current = self._store.get(feature_id)
            if current is None:
                current = _CacheRecord(
                    expires_at=now,
                    feature=None,
                    latest_refresh=refresh,
                    revision_fence=None,
                )
            else:
                current = replace(current, latest_refresh=refresh)
            self._store[feature_id] = current
            self._store.move_to_end(feature_id)
        self._trim()
        return refresh

    def put_many(
        self,
        features: Mapping[str, CachedFeature],
        *,
        refresh: int | None = None,
    ) -> None:
        """더 최신 refresh/revision을 되돌리지 않는 positive cache 갱신."""
        expires_at = time.monotonic() + self._ttl
        for fid, feature in features.items():
            current = self._store.get(fid)
            if refresh is not None and (current is None or current.latest_refresh != refresh):
                continue
            if current is not None:
                if (
                    current.feature is not None
                    and current.feature.row_revision > feature.row_revision
                ):
                    continue
                if (
                    current.revision_fence is not None
                    and current.revision_fence >= feature.row_revision
                ):
                    continue
            self._store[fid] = _CacheRecord(
                expires_at=expires_at,
                feature=feature,
                latest_refresh=current.latest_refresh if current is not None else 0,
                revision_fence=None,
            )
            self._store.move_to_end(fid)
        self._trim()

    def invalidate_many(
        self,
        revisions: Mapping[str, int | None],
        *,
        refresh: int,
    ) -> None:
        """terminal/missing 응답을 revision fence로 남겨 이전 found 재삽입을 막는다."""
        for feature_id, revision in revisions.items():
            current = self._store.get(feature_id)
            if current is None or current.latest_refresh != refresh:
                continue
            if (
                revision is not None
                and current.feature is not None
                and current.feature.row_revision > revision
            ):
                continue
            fences = [fence for fence in (current.revision_fence, revision) if fence is not None]
            self._store[feature_id] = replace(
                current,
                feature=None,
                revision_fence=max(fences) if fences else None,
            )
            self._store.move_to_end(feature_id)
        self._trim()

    def clear(self) -> None:
        self._store.clear()
        self._refresh_sequence = 0


feature_cache = FeatureCache(
    ttl_seconds=settings.pinvi_feature_cache_ttl_seconds,
    max_size=settings.pinvi_feature_cache_max_size,
)
