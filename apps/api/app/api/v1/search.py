"""`GET /search` — 통합 검색(source-tagged) — `docs/api/search.md`(ADR-054).

feature(kor-travel-map) + address(kor-travel-geo) + 내 POI(Pinvi DB)를 먼저 모으고, 내부 결과가
K(`pinvi_place_search_internal_threshold`) 미만일 때만 Kakao/Naver Local(표시 전용)로 보강한다.
결과는 단일 `PlaceSearchResult[]`로 합쳐 internal → kakao → naver 순으로 반환한다. 한 소스가
불가해도 전체를 실패시키지 않고 해당 소스만 `degraded_sources`에 기록한다.

"내 주변 검색"으로 사용자 좌표를 Kakao에 넘기는 것은 위치정보 제3자 제공이다(§9): `lat`/`lon`이
함께 오면 좌표를 Kakao에만 전달하고 `location_audit`에 기록한다(Naver는 좌표 파라미터 없음).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import or_, select

from app.clients.kakao_local import KakaoLocalClientDep, KakaoLocalError
from app.clients.kor_travel_geo import KorTravelGeoClientDep, KorTravelGeoError
from app.clients.kor_travel_map import KorTravelMapError, KorTravelMapHttpClientDep
from app.clients.naver_local import NaverLocalClientDep, NaverLocalError
from app.core.config import settings
from app.core.deps import CurrentUserId, DbSession
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.schemas.envelope import Envelope
from app.schemas.search import PlaceSearchResponse, PlaceSearchResult
from app.services.place_search import (
    address_candidate_to_result,
    feature_item_to_result,
    kakao_document_to_result,
    my_poi_to_result,
    naver_item_to_result,
)

router = APIRouter(tags=["search"])

_MY_POI_LIMIT = 10


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _snapshot_coord(snapshot: dict[str, Any]) -> tuple[float | None, float | None]:
    coord = snapshot.get("coord")
    if isinstance(coord, dict):
        lon = coord.get("lon", coord.get("longitude"))
        lat = coord.get("lat", coord.get("latitude"))
        return lon, lat
    return None, None


async def _search_my_pois(db: DbSession, *, user_id: uuid.UUID, q: str) -> list[dict[str, Any]]:
    """내 여행의 POI 중 이름/메모가 q에 매칭되는 것(소유 trip 한정)."""
    needle = f"%{_escape_like(q)}%"
    stmt = (
        select(TripDayPoi, Trip.title)
        .join(Trip, Trip.trip_id == TripDayPoi.trip_id)
        .where(
            Trip.owner_user_id == user_id,
            Trip.deleted_at.is_(None),
            TripDayPoi.deleted_at.is_(None),
            or_(
                TripDayPoi.feature_snapshot["name"].astext.ilike(needle, escape="\\"),
                TripDayPoi.user_note.ilike(needle, escape="\\"),
            ),
        )
        .order_by(TripDayPoi.updated_at.desc())
        .limit(_MY_POI_LIMIT)
    )
    rows = await db.execute(stmt)
    out: list[dict[str, Any]] = []
    for poi, trip_title in rows:
        snapshot = poi.feature_snapshot if isinstance(poi.feature_snapshot, dict) else {}
        lon, lat = _snapshot_coord(snapshot)
        out.append(
            {
                "poi_id": str(poi.attachment_id),
                "trip_id": str(poi.trip_id),
                "trip_title": trip_title,
                "feature_id": poi.feature_id,
                "name": snapshot.get("name"),
                "user_note": poi.user_note,
                "lon": lon,
                "lat": lat,
            }
        )
    return out


@router.get("/search", response_model=Envelope[PlaceSearchResponse])
async def unified_search(
    request: Request,
    current_user_id: CurrentUserId,
    db: DbSession,
    kor_travel_map: KorTravelMapHttpClientDep,
    kor_travel_geo: KorTravelGeoClientDep,
    kakao_local: KakaoLocalClientDep,
    naver_local: NaverLocalClientDep,
    q: Annotated[str, Query(min_length=2, max_length=120)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
) -> Envelope[PlaceSearchResponse]:
    user_id = uuid.UUID(current_user_id)
    degraded: list[str] = []
    # "내 주변 검색": lat+lon이 함께 오면 좌표를 Kakao에만 전달한다. 위치 감사(§9)는 좌표가 실제로
    # Kakao에 제3자 제공된 경우에만 기록해야 하므로, near-me라도 우선 no-disclosure((None,None))로 두어
    # location_audit 미들웨어의 query 파라미터 fallback을 무력화하고, 실제 Kakao 호출 지점에서만
    # 좌표로 덮어쓴다(short-circuit/ provider 부재 시 거짓 제3자 제공 기록 방지).
    near_me = lat is not None and lon is not None
    if near_me:
        request.state.location_audit_coord = (None, None)

    results: list[PlaceSearchResult] = []

    # ── 내부 소스: feature → address → my_poi ──────────────────────────────
    try:
        feature_data = await kor_travel_map.search_features(q=q, page_size=limit)
        for item in feature_data.get("items") or []:
            if isinstance(item, dict) and (r := feature_item_to_result(item)) is not None:
                results.append(r)
    except KorTravelMapError:
        degraded.append("features")

    try:
        address_data = await kor_travel_geo.search(query=q, kind="address", size=limit)
        for cand in address_data.get("candidates") or []:
            if isinstance(cand, dict) and (r := address_candidate_to_result(cand)) is not None:
                results.append(r)
    except KorTravelGeoError:
        degraded.append("addresses")

    for poi in await _search_my_pois(db, user_id=user_id, q=q):
        results.append(my_poi_to_result(poi))

    # ── internal-first short-circuit: 내부 결과 ≥ K면 provider 미호출(§10) ──
    if len(results) < settings.pinvi_place_search_internal_threshold:
        if kakao_local is not None:
            try:
                if near_me:
                    # 좌표를 실제로 Kakao에 제3자 제공하는 지점 — 여기서만 감사 기록(§9).
                    request.state.location_audit_coord = (lat, lon)
                kakao_data = await kakao_local.search_keyword(
                    query=q,
                    size=limit,
                    x=lon if near_me else None,
                    y=lat if near_me else None,
                )
                for doc in kakao_data.get("documents") or []:
                    if isinstance(doc, dict) and (r := kakao_document_to_result(doc)) is not None:
                        results.append(r)
            except KakaoLocalError:
                degraded.append("kakao")
        else:
            degraded.append("kakao")

        if naver_local is not None:
            try:
                naver_data = await naver_local.search_local(query=q, display=limit)
                for item in naver_data.get("items") or []:
                    if isinstance(item, dict) and (r := naver_item_to_result(item)) is not None:
                        results.append(r)
            except NaverLocalError:
                degraded.append("naver")
        else:
            degraded.append("naver")

    return Envelope.of(PlaceSearchResponse(results=results, degraded_sources=degraded))
