"""`app.trip` ↔ `feature.feature` join — Trip 응답 빌더.

Trip 상세 응답에 POI별 feature 정보 (좌표 / 마커 / 카테고리) 를 채워주는 빌더.
krtour `POST /v1/features/batch`(`KrtourMapClient.get_features`) batch 호출로 N+1 회피.

SPRINT-4 산출물 `apps/api/app/services/trip_view_builder.py`.

데이터 모델 주의:
- `TripDay` PK = composite `(trip_id, day_index)` — 단일 `day_id` 컬럼 없음
- `TripDayPoi` PK = `attachment_id` UUID 컬럼 (legacy 명명). FK `(trip_id, day_index)`
  로 TripDay 에 연결
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.krtour_map import KrtourMapClient
from app.core.config import settings
from app.models.companion import TripCompanion
from app.models.poi import TripDayPoi
from app.models.share_link import TripShareLink
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.services.feature_cache import feature_cache
from app.services.poi import get_poi_rise_sets, poi_rise_set_to_dict

logger = logging.getLogger(__name__)


async def build_trip_view(
    db: AsyncSession,
    *,
    trip: Trip,
    krtour_client: KrtourMapClient | None,
    include_management: bool = True,
) -> dict[str, Any]:
    """Trip + 모든 Day + 모든 POI + (feature snapshot 또는 라이브러리 fresh fetch).

    동작:
    1. trip의 day 목록 + 모든 POI 로드 (`trip_id` 단일 인덱스로 batch query)
    2. POI의 `feature_id` 수집 후 unique 리스트로
    3. `krtour_client.get_features(ids)` 1회 batch 호출 (N+1 회피) → `{found, missing}`
    4. POI에 feature 정보 merge — `feature_link_broken_at` 처리 (krtour에서 사라진
       feature 는 `is_broken=True` 표시)

    krtour client가 미주입 (`krtour_client=None`) 인 경우 — POI의 stored `feature_snapshot`
    만 사용 (fresh fetch 없음). 사용자에게 stale 경고 표시.

    Args:
        db: AsyncSession.
        trip: Trip 인스턴스 (eager loaded 권장).
        krtour_client: 라이브러리 client. None 가능 (placeholder).

    Returns:
        dict: {
            "trip": Trip dict,
            "days": [{day_index, date, pois: [...]}, ...],
            "companions": [...],
            "share_links": [...],
            "broken_feature_count": int,
        }
    """
    # Day 로드 — `(trip_id, day_index)` composite PK
    day_query = select(TripDay).where(TripDay.trip_id == trip.trip_id).order_by(TripDay.day_index)
    days_result = await db.execute(day_query)
    days = list(days_result.scalars())

    companion_query = (
        select(TripCompanion)
        .where(TripCompanion.trip_id == trip.trip_id)
        .order_by(TripCompanion.invited_at.desc(), TripCompanion.companion_id.asc())
    )
    companion_result = await db.execute(companion_query)
    companions = list(companion_result.scalars())

    # 동반자 PII(invited_email)와 공유 링크 메타는 owner/co_owner(관리 권한)에게만 노출.
    companions_view = [
        _companion_to_dict(c, include_management=include_management) for c in companions
    ]
    share_links_view: list[dict[str, Any]] = []
    if include_management:
        share_link_query = (
            select(TripShareLink)
            .where(TripShareLink.trip_id == trip.trip_id)
            .order_by(TripShareLink.created_at.desc(), TripShareLink.share_id.asc())
        )
        share_link_result = await db.execute(share_link_query)
        share_links_view = [_share_link_to_dict(s) for s in share_link_result.scalars()]

    if not days:
        return {
            "trip": _trip_to_dict(trip),
            "days": [],
            "companions": companions_view,
            "share_links": share_links_view,
            "broken_feature_count": 0,
        }

    # POI 로드 — trip_id 단일 인덱스
    poi_query = (
        select(TripDayPoi)
        .where(TripDayPoi.trip_id == trip.trip_id, TripDayPoi.deleted_at.is_(None))
        .order_by(TripDayPoi.day_index, TripDayPoi.sort_order)
    )
    poi_result = await db.execute(poi_query)
    pois = list(poi_result.scalars())
    rise_sets_by_poi_id = await get_poi_rise_sets(
        db,
        poi_ids=[poi.attachment_id for poi in pois],
    )

    # feature_id batch 수집 (unique). krtour-map feature_id는 불투명 문자열이다.
    feature_ids: list[str] = []
    seen: set[str] = set()
    for poi in pois:
        fid_str = _canonical_feature_id(poi.feature_id)
        if fid_str not in seen:
            seen.add(fid_str)
            feature_ids.append(fid_str)

    # krtour batch fetch — process-local TTL 캐시(T-146/D-26)로 miss만 재조회.
    # krtour `POST /v1/features/batch`는 {found:{id:detail}, missing:[id]} 반환(cap 청크는 client).
    fresh_features: dict[str, dict[str, Any]] = {}
    if krtour_client is not None and feature_ids:
        use_cache = settings.tripmate_feature_cache_enabled
        if use_cache:
            cached, missing = feature_cache.get_many(feature_ids)
            fresh_features.update(cached)
        else:
            missing = feature_ids
        if missing:
            try:
                batch = await krtour_client.get_features(missing)
                found_map: dict[str, Any] = batch.get("found") or {}
                fetched: dict[str, dict[str, Any]] = {
                    _canonical_feature_id(str(fid)): feature
                    for fid, feature in found_map.items()
                    if isinstance(feature, dict)
                }
                fresh_features.update(fetched)
                if use_cache and fetched:
                    feature_cache.put_many(fetched)
            except Exception as exc:
                logger.error("get_features batch 실패: %s — snapshot으로 fallback", exc)

    # day_index → POI 리스트
    pois_by_day_index: dict[int, list[dict[str, Any]]] = {}
    broken_count = 0
    for poi in pois:
        feature_id = _canonical_feature_id(poi.feature_id)
        fresh = fresh_features.get(feature_id)
        is_broken = krtour_client is not None and fresh is None
        if is_broken:
            broken_count += 1

        feature_view = fresh or poi.feature_snapshot or {}
        title = None
        if isinstance(feature_view, dict):
            title = feature_view.get("title") or feature_view.get("name")

        pois_by_day_index.setdefault(poi.day_index, []).append(
            {
                "poi_id": str(poi.attachment_id),  # legacy 컬럼명
                "feature_id": poi.feature_id,
                "sort_order": poi.sort_order,
                "title": title,
                "feature": feature_view,
                "marker_color": poi.custom_marker_color
                or (feature_view.get("marker_color") if isinstance(feature_view, dict) else None),
                "marker_icon": poi.custom_marker_icon
                or (feature_view.get("marker_icon") if isinstance(feature_view, dict) else None),
                "is_broken": is_broken,
                "user_note": poi.user_note,
                "planned_arrival_at": poi.planned_arrival_at,
                "planned_departure_at": poi.planned_departure_at,
                "budget_amount": poi.budget_amount,
                "actual_amount": poi.actual_amount,
                "currency": poi.currency,
                "user_url": poi.user_url,
                "rise_set": poi_rise_set_to_dict(rise_sets_by_poi_id.get(poi.attachment_id)),
                "feature_link_broken_at": poi.feature_link_broken_at,
                "version": poi.version,
                "created_at": poi.created_at,
                "updated_at": poi.updated_at,
            }
        )

    return {
        "trip": _trip_to_dict(trip),
        "days": [
            {
                "day_index": d.day_index,
                "date": d.date,
                "title": d.title,
                "pois": pois_by_day_index.get(d.day_index, []),
            }
            for d in days
        ],
        "companions": companions_view,
        "share_links": share_links_view,
        "broken_feature_count": broken_count,
    }


def _trip_to_dict(trip: Trip) -> dict[str, Any]:
    return {
        "trip_id": trip.trip_id,
        "owner_user_id": trip.owner_user_id,
        "title": trip.title,
        "description": trip.description,
        "region_hint": trip.region_hint,
        "primary_region_code": trip.primary_region_code,
        "primary_region_source": trip.primary_region_source,
        "start_date": trip.start_date,
        "end_date": trip.end_date,
        "visibility": trip.visibility,
        "status": trip.status,
        "version": trip.version,
        "created_at": trip.created_at,
        "updated_at": trip.updated_at,
    }


def _canonical_feature_id(feature_id: str) -> str:
    """저장 snapshot suffix를 제외하고 krtour feature_id 문자열을 보존한다."""
    return feature_id.split("@", 1)[0]


def _companion_to_dict(companion: TripCompanion, *, include_management: bool) -> dict[str, Any]:
    # 비관리 viewer에게는 invited_email(PII)을 마스킹. 닉네임/역할은 협업 표시용으로 유지.
    return {
        "companion_id": companion.companion_id,
        "trip_id": companion.trip_id,
        "user_id": companion.user_id,
        "invited_email": companion.invited_email if include_management else None,
        "invited_nickname": companion.invited_nickname,
        "role": companion.role,
        "invited_at": companion.invited_at,
        "joined_at": companion.joined_at,
        "created_at": companion.created_at,
        "updated_at": companion.updated_at,
    }


def _share_link_to_dict(share_link: TripShareLink) -> dict[str, Any]:
    return {
        "share_id": share_link.share_id,
        "visibility": share_link.visibility,
        "expires_at": share_link.expires_at,
        "revoked_at": share_link.revoked_at,
        "last_used_at": share_link.last_used_at,
        "created_at": share_link.created_at,
    }
