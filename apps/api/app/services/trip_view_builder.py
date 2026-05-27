"""`app.trip` ↔ `feature.feature` join — Trip 응답 빌더.

Trip 상세 응답에 POI별 feature 정보 (좌표 / 마커 / 카테고리) 를 채워주는 빌더.
라이브러리 측 `features_by_ids` batch 호출로 N+1 회피.

SPRINT-4 산출물 `apps/api/app/services/trip_view_builder.py`.

데이터 모델 주의:
- `TripDay` PK = composite `(trip_id, day_index)` — 단일 `day_id` 컬럼 없음
- `TripDayPoi` PK = `attachment_id` UUID 컬럼 (legacy 명명). FK `(trip_id, day_index)`
  로 TripDay 에 연결
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.etl_bridge.krtour_map import KrtourMapClient
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.trip_day import TripDay

logger = logging.getLogger(__name__)


async def build_trip_view(
    db: AsyncSession,
    *,
    trip: Trip,
    krtour_client: KrtourMapClient | None,
) -> dict[str, Any]:
    """Trip + 모든 Day + 모든 POI + (feature snapshot 또는 라이브러리 fresh fetch).

    동작:
    1. trip의 day 목록 + 모든 POI 로드 (`trip_id` 단일 인덱스로 batch query)
    2. POI의 `feature_id` 수집 후 unique 리스트로
    3. `krtour_client.features_by_ids(ids)` 1회 batch 호출 (N+1 회피)
    4. POI에 feature 정보 merge — `feature_link_broken_at` 처리 (라이브러리에서 사라진
       feature 는 `is_broken=True` 표시)

    라이브러리가 미주입 (`krtour_client=None`) 인 경우 — POI의 stored `feature_snapshot`
    만 사용 (fresh fetch 없음). 사용자에게 stale 경고 표시.

    Args:
        db: AsyncSession.
        trip: Trip 인스턴스 (eager loaded 권장).
        krtour_client: 라이브러리 client. None 가능 (placeholder).

    Returns:
        dict: {
            "trip": Trip dict,
            "days": [{day_index, date, pois: [...]}, ...],
            "broken_feature_count": int,
        }
    """
    # Day 로드 — `(trip_id, day_index)` composite PK
    day_query = select(TripDay).where(TripDay.trip_id == trip.trip_id).order_by(TripDay.day_index)
    days_result = await db.execute(day_query)
    days = list(days_result.scalars())

    if not days:
        return {
            "trip": {"trip_id": str(trip.trip_id), "title": trip.title},
            "days": [],
            "broken_feature_count": 0,
        }

    # POI 로드 — trip_id 단일 인덱스
    poi_query = (
        select(TripDayPoi)
        .where(TripDayPoi.trip_id == trip.trip_id)
        .order_by(TripDayPoi.day_index, TripDayPoi.sort_order)
    )
    poi_result = await db.execute(poi_query)
    pois = list(poi_result.scalars())

    # feature_id batch 수집 (unique)
    feature_ids: list[uuid.UUID] = []
    seen: set[str] = set()
    for poi in pois:
        fid_str = poi.feature_id
        if fid_str not in seen:
            seen.add(fid_str)
            try:
                feature_ids.append(uuid.UUID(fid_str.split("@")[0]))
            except (ValueError, AttributeError):
                logger.warning("Invalid feature_id: %s", fid_str)

    # 라이브러리 batch fetch
    fresh_features: dict[uuid.UUID, dict[str, Any]] = {}
    if krtour_client is not None and feature_ids:
        try:
            features = await krtour_client.features_by_ids(feature_ids)
            fresh_features = {uuid.UUID(f["feature_id"]): f for f in features}
        except Exception as exc:
            logger.error("features_by_ids batch 실패: %s — snapshot으로 fallback", exc)

    # day_index → POI 리스트
    pois_by_day_index: dict[int, list[dict[str, Any]]] = {}
    broken_count = 0
    for poi in pois:
        feature_uuid: uuid.UUID | None = None
        try:
            feature_uuid = uuid.UUID(poi.feature_id.split("@")[0])
        except (ValueError, AttributeError):
            pass

        fresh = fresh_features.get(feature_uuid) if feature_uuid else None
        is_broken = krtour_client is not None and feature_uuid is not None and fresh is None
        if is_broken:
            broken_count += 1

        feature_view = fresh or poi.feature_snapshot or {}

        pois_by_day_index.setdefault(poi.day_index, []).append(
            {
                "poi_id": str(poi.attachment_id),  # legacy 컬럼명
                "feature_id": poi.feature_id,
                "sort_order": poi.sort_order,
                "title": feature_view.get("title") if isinstance(feature_view, dict) else None,
                "feature": feature_view,
                "marker_color": poi.custom_marker_color
                or (feature_view.get("marker_color") if isinstance(feature_view, dict) else None),
                "marker_icon": poi.custom_marker_icon
                or (feature_view.get("marker_icon") if isinstance(feature_view, dict) else None),
                "is_broken": is_broken,
                "user_note": poi.user_note,
                "planned_arrival_at": poi.planned_arrival_at,
                "planned_departure_at": poi.planned_departure_at,
            }
        )

    return {
        "trip": {
            "trip_id": str(trip.trip_id),
            "title": trip.title,
            "description": trip.description,
            "start_date": trip.start_date,
            "end_date": trip.end_date,
            "visibility": trip.visibility,
            "version": trip.version,
        },
        "days": [
            {
                "day_index": d.day_index,
                "date": d.date,
                "title": d.title,
                "pois": pois_by_day_index.get(d.day_index, []),
            }
            for d in days
        ],
        "broken_feature_count": broken_count,
    }
