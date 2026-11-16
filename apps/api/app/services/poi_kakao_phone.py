"""장소 정보 패널의 Kakao 전화번호 — 표시 시점 라이브 조회, 저장하지 않음(ADR-054).

저장된 영업 정보(`trip_poi_place_details`, 공공데이터)에 전화가 없을 때만 패널이 부른다. Kakao Local
키워드 검색 결과 중 이름·좌표가 확실히 맞는 장소(`best_match_enrichment`, 300 m·이름 유사도 가드)의
전화와 카카오맵 back-link를 돌려준다.

- DB에 쓰지 않는다. 같은 장소를 짧은 시간에 여러 번 열 때를 위해 프로세스 메모리 캐시(`_TTL_SECONDS`,
  최대 `_MAX_ENTRIES`건)만 둔다. 실패는 캐시하지 않는다.
- 저장된 전화가 있으면 Kakao를 부르지 않는다(공공데이터 우선, 요청 절약).
- 좌표는 장소 자신의 좌표(사용자 위치 아님)라 위치 감사 대상이 아니다(feature 상세 카드 enrichment와 같다).
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kakao_local import KakaoLocalClient
from app.models.poi import TripDayPoi
from app.models.poi_place_detail import TripPoiPlaceDetail
from app.schemas.feature import Coord, ExternalEnrichment
from app.services.feature_detail import best_match_enrichment
from app.services.poi_weather import poi_coord

logger = logging.getLogger(__name__)

_TTL_SECONDS = 600.0
_MAX_ENTRIES = 1024
_cache: OrderedDict[tuple[str, float, float], tuple[float, ExternalEnrichment]] = OrderedDict()


def _unmatched() -> ExternalEnrichment:
    return ExternalEnrichment(provider="kakao", matched=False)


def poi_name(poi: TripDayPoi) -> str | None:
    snapshot = poi.feature_snapshot if isinstance(poi.feature_snapshot, dict) else {}
    for key in ("name", "title"):
        value = snapshot.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _cache_get(key: tuple[str, float, float], now: float) -> ExternalEnrichment | None:
    hit = _cache.get(key)
    if hit is None:
        return None
    stored_at, value = hit
    if now - stored_at > _TTL_SECONDS:
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)
    return value


def _cache_put(key: tuple[str, float, float], value: ExternalEnrichment, now: float) -> None:
    _cache[key] = (now, value)
    _cache.move_to_end(key)
    while len(_cache) > _MAX_ENTRIES:
        _cache.popitem(last=False)


def clear_cache() -> None:
    """테스트 전용."""
    _cache.clear()


async def kakao_phone_for_poi(
    db: AsyncSession, *, poi: TripDayPoi, kakao: KakaoLocalClient | None
) -> ExternalEnrichment:
    """확실히 맞는 Kakao 장소의 전화·back-link. 못 찾거나 장애면 `matched=False`(조용히)."""
    stored = await db.get(TripPoiPlaceDetail, poi.attachment_id)
    if stored is not None and stored.phone:
        return _unmatched()
    name = poi_name(poi)
    coord = poi_coord(poi)
    if kakao is None or name is None or coord is None:
        return _unmatched()
    lat, lon = coord
    key = (name, round(lat, 5), round(lon, 5))
    now = time.monotonic()
    cached = _cache_get(key, now)
    if cached is not None:
        return cached
    try:
        data: dict[str, Any] = await kakao.search_keyword(query=name, size=5, x=lon, y=lat)
        documents = data.get("documents")
        rows = (
            [row for row in documents if isinstance(row, dict)]
            if isinstance(documents, list)
            else []
        )
        enrichment = best_match_enrichment(
            "kakao", feature_name=name, feature_coord=Coord(lon=lon, lat=lat), documents=rows
        )
    except Exception as exc:  # 선택 정보 — 장애는 표시하지 않고 캐시하지 않는다.
        logger.warning("poi_kakao_phone.failed", extra={"failure_type": type(exc).__name__})
        return _unmatched()
    _cache_put(key, enrichment, now)
    return enrichment
