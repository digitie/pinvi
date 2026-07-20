"""`app.trip` ↔ `feature.feature` join — Trip 응답 빌더.

Trip 상세 응답에 POI별 feature 정보 (좌표 / 마커 / 카테고리) 를 채워주는 빌더.
kor_travel_map `POST /v1/features/batch`(`KorTravelMapClient.get_features`) batch 호출로 N+1 회피.

SPRINT-4 산출물 `apps/api/app/services/trip_view_builder.py`.

데이터 모델 주의:
- `TripDay` PK = composite `(trip_id, day_index)` — 단일 `day_id` 컬럼 없음
- `TripDayPoi` PK = `attachment_id` UUID 컬럼 (legacy 명명). FK `(trip_id, day_index)`
  로 TripDay 에 연결
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map import KorTravelMapClient
from app.core.config import settings
from app.core.markers import resolve_display_marker_color
from app.models.companion import TripCompanion
from app.models.kasi import KasiSpecialDay
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
    kor_travel_map_client: KorTravelMapClient | None,
    include_management: bool = True,
) -> dict[str, Any]:
    """Trip + 모든 Day + 모든 POI + (feature snapshot 또는 라이브러리 fresh fetch).

    동작:
    1. trip의 day 목록 + 모든 POI 로드 (`trip_id` 단일 인덱스로 batch query)
    2. feature-backed POI의 `feature_id` 수집 후 unique 리스트로
    3. `kor_travel_map_client.get_features(ids)` 1회 batch 호출 (N+1 회피) → `{found, missing}`
    4. POI에 feature 정보 merge — `feature_link_broken_at` 처리 (kor_travel_map에서 사라진
       feature 는 `is_broken=True` 표시)

    kor_travel_map client가 미주입 (`kor_travel_map_client=None`) 인 경우 — POI의 stored `feature_snapshot`
    만 사용 (fresh fetch 없음). 사용자에게 stale 경고 표시.

    Args:
        db: AsyncSession.
        trip: Trip 인스턴스 (eager loaded 권장).
        kor_travel_map_client: 라이브러리 client. None 가능 (placeholder).

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

    # ADR-055: effective_date(파생) + out_of_range + 일자 색 override를 일자별로 미리 계산한다.
    # date는 override-only이므로 비면 trip.start_date + (day_index-1)로 파생한다.
    day_effective_date: dict[int, date | None] = {}
    day_out_of_range: dict[int, bool] = {}
    day_color_override: dict[int, str | None] = {}
    for day in days:
        if day.date is not None:
            eff = day.date
        elif trip.start_date is not None:
            eff = trip.start_date + timedelta(days=day.day_index - 1)
        else:
            eff = None
        day_effective_date[day.day_index] = eff
        day_out_of_range[day.day_index] = bool(
            trip.start_date is not None
            and trip.end_date is not None
            and eff is not None
            and (eff < trip.start_date or eff > trip.end_date)
        )
        day_color_override[day.day_index] = day.marker_color

    # 공휴일은 raw date가 아니라 effective_date 기준으로 조회한다(파생 일자도 공휴일 표시).
    holidays_by_date = await _load_holidays_by_date(db, list(day_effective_date.values()))
    day_holidays: dict[int, list[dict[str, Any]]] = {
        di: (holidays_by_date.get(eff, []) if eff is not None else [])
        for di, eff in day_effective_date.items()
    }

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

    # feature_id batch 수집 (unique). feature 없는 자유 POI는 snapshot만 사용한다.
    feature_ids: list[str] = []
    seen: set[str] = set()
    for poi in pois:
        fid_str = _canonical_feature_id(poi.feature_id)
        if fid_str is None:
            continue
        if fid_str not in seen:
            seen.add(fid_str)
            feature_ids.append(fid_str)

    # kor_travel_map batch fetch — process-local TTL 캐시(T-146/D-26)로 miss만 재조회.
    # kor_travel_map `POST /v1/features/batch`는 {found:{id:detail}, missing:[id]} 반환(cap 청크는 client).
    fresh_features: dict[str, dict[str, Any]] = {}
    if kor_travel_map_client is not None and feature_ids:
        use_cache = settings.pinvi_feature_cache_enabled
        if use_cache:
            cached, missing = feature_cache.get_many(feature_ids)
            fresh_features.update(cached)
        else:
            missing = feature_ids
        if missing:
            try:
                batch = await kor_travel_map_client.get_features(missing)
                found_map: dict[str, Any] = batch.get("found") or {}
                fetched: dict[str, dict[str, Any]] = {}
                for fid, feature in found_map.items():
                    if not isinstance(feature, dict):
                        continue
                    canonical_id = _canonical_feature_id(str(fid))
                    if canonical_id is not None:
                        fetched[canonical_id] = feature
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
        fresh = fresh_features.get(feature_id) if feature_id is not None else None
        is_broken = feature_id is not None and kor_travel_map_client is not None and fresh is None
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
                # ADR-055: 지도 핀·목록 뱃지 parity용 서버 계산 색 — custom(POI) > 일자색(override/기본).
                "display_marker_color": resolve_display_marker_color(
                    poi.day_index,
                    day_color_override.get(poi.day_index),
                    poi.custom_marker_color,
                ),
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
                "effective_date": day_effective_date[d.day_index],
                "out_of_range": day_out_of_range[d.day_index],
                "marker_color": d.marker_color,
                "title": d.title,
                "version": d.version,
                "holidays": day_holidays[d.day_index],
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


async def _load_holidays_by_date(
    db: AsyncSession,
    dates: list[date | None],
) -> dict[date, list[dict[str, Any]]]:
    unique_dates = sorted({value for value in dates if value is not None})
    if not unique_dates:
        return {}

    result = await db.execute(
        select(KasiSpecialDay)
        .where(
            KasiSpecialDay.sol_date.in_(unique_dates),
            KasiSpecialDay.is_holiday.is_(True),
        )
        .order_by(KasiSpecialDay.sol_date.asc(), KasiSpecialDay.name.asc())
    )
    holidays_by_date: dict[date, list[dict[str, Any]]] = {}
    seen: dict[date, set[tuple[str, str]]] = {}
    for row in result.scalars():
        key = (row.dataset, row.name)
        row_seen = seen.setdefault(row.sol_date, set())
        if key in row_seen:
            continue
        row_seen.add(key)
        holidays_by_date.setdefault(row.sol_date, []).append(
            {
                "date": row.sol_date,
                "name": row.name,
                "dataset": row.dataset,
            }
        )
    return holidays_by_date


def _canonical_feature_id(feature_id: str | None) -> str | None:
    """저장 snapshot suffix를 제외하고 kor_travel_map feature_id 문자열을 보존한다."""
    if feature_id is None:
        return None
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
