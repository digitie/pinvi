"""`GET /search` — 통합 검색(source-tagged) — `docs/api/search.md`(ADR-054).

feature(kor-travel-map) + address(kor-travel-geo) + 내 POI(Pinvi DB)를 먼저 모으고, 내부 결과가
K(`pinvi_place_search_internal_threshold`) 미만일 때만 Kakao/Naver Local(표시 전용)로 보강한다.
결과는 단일 `PlaceSearchResult[]`로 합쳐 internal → kakao → naver 순으로 반환한다. 한 소스가
불가해도 전체를 실패시키지 않고 해당 소스만 `degraded_sources`에 기록한다.

"내 주변 검색"으로 사용자 좌표를 Kakao에 넘기는 것은 위치정보 제3자 제공이다(§9): `lat`/`lon`이
함께 오면 좌표를 Kakao에만 전달하고 `location_audit`에 기록한다(Naver는 좌표 파라미터 없음).
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import or_, select

from app.clients.kakao_local import KakaoLocalClientDep, KakaoLocalError
from app.clients.kor_travel_geo import KorTravelGeoClientDep, KorTravelGeoError
from app.clients.kor_travel_map import KorTravelMapError, KorTravelMapHttpClientDep
from app.clients.naver_local import NaverLocalClientDep, NaverLocalError
from app.core.bbox import parse_bbox_numbers
from app.core.config import settings
from app.core.consent_deps import assert_location_consent
from app.core.deps import CurrentUserId, DbSession
from app.middleware.location_audit import declare_location_audit
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.schemas.envelope import Envelope
from app.schemas.feature import BBox
from app.schemas.search import PlaceSearchResponse, PlaceSearchResult
from app.services.admin_pois import extract_feature_coord
from app.services.category_labels import get_category_labels
from app.services.place_search import (
    address_candidate_to_result,
    merge_region_biased_items,
    feature_item_to_result,
    kakao_document_to_result,
    my_poi_to_result,
    naver_item_to_result,
)

router = APIRouter(tags=["search"])

_MY_POI_LIMIT = 10
# 자동완성의 주소 소스(kor-travel-geo `/v2/search`) 예산. 평소 0.3~1초다. 짧은 검색어("하회")에서 geo가
# DB statement timeout(504 E0504, ~5초)을 내면 재시도해도 같으므로 1회만, 짧게 끊고 `addresses`를
# degrade로 둔다 — 예전에는 5초씩 3회 재시도가 feature 결과까지 16초 붙잡았다(2026-11-02 prod e2e).
_ADDRESS_SEARCH_TIMEOUT_SECONDS = 3.0


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _snapshot_coord(snapshot: dict[str, Any]) -> tuple[float | None, float | None]:
    """POI feature snapshot에서 `(lon, lat)`.

    T-VN-H29: 과거 구현은 중첩 `coord` 하나만 봤다. kor-travel-map curated import로 들어온 POI의
    snapshot은 좌표를 **top-level `lon`/`lat`**에 담고(`CuratedFeatureDetailFeatureSnapshotView`는
    `extra="forbid"`이고 `coord` property가 아예 없다) 따라서 그 read는 **구조적으로 항상 None**이라
    통합 검색에서만 좌표가 null로 나왔다. 같은 payload를 `admin_pois`/`kasi`는 정상 해석한다.
    중복 구현 대신 그 정본 추출기를 재사용한다(top-level + coord/coordinate/location/geometry,
    lon/lng/longitude/x 별칭, 숫자 강제 변환까지 처리).
    """
    return extract_feature_coord(snapshot)


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


_KOREA_LNG = (124.0, 132.0)
_KOREA_LAT = (33.0, 43.0)


def _parse_bias_bbox(raw: str | None) -> BBox | None:
    """지역 편향 bbox. 형식이 틀리면 400, 한국 범위 밖 값은 범위 안으로 좁힌다(편향일 뿐이다)."""
    if raw is None or not raw.strip():
        return None
    parsed = parse_bbox_numbers(raw)
    lng_min, lat_min, lng_max, lat_max = parsed
    lng_lo, lng_hi = sorted((lng_min, lng_max))
    lat_lo, lat_hi = sorted((lat_min, lat_max))
    return BBox(
        lng_min=min(max(lng_lo, _KOREA_LNG[0]), _KOREA_LNG[1]),
        lat_min=min(max(lat_lo, _KOREA_LAT[0]), _KOREA_LAT[1]),
        lng_max=min(max(lng_hi, _KOREA_LNG[0]), _KOREA_LNG[1]),
        lat_max=min(max(lat_hi, _KOREA_LAT[0]), _KOREA_LAT[1]),
    )


_AUDIT_PRECISION = Decimal("0.000001")


def _audit_decimal(value: float) -> Decimal:
    """확인자료에 적을 좌표 — 저장 정밀도(`numeric(9,6)`)로 맞춘다."""
    return Decimal(str(value)).quantize(_AUDIT_PRECISION)


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
    bbox: Annotated[
        str | None,
        Query(
            max_length=100,
            description=(
                "지역 편향 `lng_min,lat_min,lng_max,lat_max` — 여행 장소 범위 또는 지금 지도 화면. "
                "이 범위 안의 feature를 먼저 보여 주고 밖의 결과도 뒤에 남긴다(필터 아님). "
                "사용자 위치가 아니므로 위치 감사·외부 provider 전달 대상이 아니다."
            ),
        ),
    ] = None,
) -> Envelope[PlaceSearchResponse]:
    user_id = uuid.UUID(current_user_id)
    bias = _parse_bias_bbox(bbox)
    degraded: list[str] = []
    # "내 주변 검색": lat+lon이 함께 오면 좌표를 Kakao에만 전달한다. 위치 감사(§9)는 좌표가 실제로
    # Kakao에 제3자 제공된 경우에만 기록해야 하므로, near-me라도 우선 no-disclosure((None,None))로 두어
    # location_audit 미들웨어의 query 파라미터 fallback을 무력화하고, 실제 Kakao 호출 지점에서만
    # 좌표로 덮어쓴다(short-circuit/ provider 부재 시 거짓 제3자 제공 기록 방지).
    near_me = lat is not None and lon is not None
    if near_me:
        # 사용자 좌표를 제3자(Kakao)에 제공하는 경로다 — 동의를 먼저 확인한다(T-327).
        # dependency로 걸지 않는 이유: 좌표 없는 키워드 검색까지 막히기 때문이다.
        await assert_location_consent(db, user_id=user_id)
        # 출처를 여기서 함께 선언한다. 좌표만 세팅하면 이 행이 `coord_source=NULL`로 남는데, NULL의
        # 계약상 의미는 "이 컬럼이 없던 시기의 행"이라 **제3자 제공이 실제로 일어난 가장 민감한
        # 행**이 레거시와 구분되지 않는다(T-329 리뷰 지적).
        declare_location_audit(request, lat=None, lng=None, source="device")

    results: list[PlaceSearchResult] = []

    # ── 내부 소스: feature → address → my_poi ──────────────────────────────
    # feature(Map)와 address(geo)는 서로 독립인 HTTP 호출이라 동시에 보낸다 — 느린 소스 하나가 다른
    # 소스의 결과를 붙잡지 않는다. 표시 순서는 그대로 feature → address다.
    async def _regional_items() -> list[Any]:
        # 편향용 보조 검색 — 실패해도 전국 결과만으로 계속한다.
        if bias is None:
            return []
        try:
            data = await kor_travel_map.search_features(
                q=q,
                page_size=limit,
                min_lon=bias.lng_min,
                min_lat=bias.lat_min,
                max_lon=bias.lng_max,
                max_lat=bias.lat_max,
            )
        except KorTravelMapError:
            return []
        return list(data.get("items") or [])

    async def _feature_results() -> list[PlaceSearchResult] | None:
        try:
            feature_data, regional, labels = await asyncio.gather(
                kor_travel_map.search_features(q=q, page_size=limit),
                _regional_items(),
                get_category_labels(kor_travel_map),
            )
        except KorTravelMapError:
            return None
        items = merge_region_biased_items(
            regional, list(feature_data.get("items") or []), limit=limit
        )
        return [r for item in items if (r := feature_item_to_result(item, labels)) is not None]

    async def _address_results() -> list[PlaceSearchResult] | None:
        try:
            # httpx timeout은 단계(connect·read…)별 상한이라 합계가 넘칠 수 있다 — 전체를 한 번 더 묶는다.
            async with asyncio.timeout(_ADDRESS_SEARCH_TIMEOUT_SECONDS):
                address_data = await kor_travel_geo.search(
                    query=q,
                    kind="address",
                    size=limit,
                    max_attempts=1,
                    attempt_timeout_seconds=_ADDRESS_SEARCH_TIMEOUT_SECONDS,
                )
        except (KorTravelGeoError, TimeoutError):
            return None
        return [
            r
            for cand in address_data.get("candidates") or []
            if isinstance(cand, dict) and (r := address_candidate_to_result(cand)) is not None
        ]

    feature_results, address_results = await asyncio.gather(_feature_results(), _address_results())
    if feature_results is None:
        degraded.append("features")
    else:
        results.extend(feature_results)
    if address_results is None:
        degraded.append("addresses")
    else:
        results.extend(address_results)

    my_pois = [my_poi_to_result(poi) for poi in await _search_my_pois(db, user_id=user_id, q=q)]
    results.extend(my_pois)

    # ── internal-first short-circuit: 내부 **장소** 결과 ≥ K면 provider 미호출(§10) ──
    # 주소 후보는 세지 않는다 — "하회…길"처럼 도로명만 여러 개 맞는 검색어가 장소 0건인데도
    # Kakao/Naver 보강을 막지 않게(주소 결과는 예전엔 매퍼 버그로 늘 0건이라 K에 들어간 적이 없다).
    internal_place_count = len(feature_results or []) + len(my_pois)
    if internal_place_count < settings.pinvi_place_search_internal_threshold:
        if kakao_local is not None:
            try:
                if lat is not None and lon is not None:
                    # 좌표를 실제로 Kakao에 제3자 제공하는 지점 — 여기서만 감사 기록(§9).
                    # `near_me`와 같은 조건이지만 여기서 다시 쓰는 이유는, 좌표가 non-None임을
                    # 이 지점에서 타입으로도 보이게 하기 위해서다.
                    declare_location_audit(
                        request,
                        lat=_audit_decimal(lat),
                        lng=_audit_decimal(lon),
                        source="device",
                    )
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
