"""`/features/*` — `docs/api/features.md`.

지도 feature read는 `python-krtour-map`의 운영 HTTP API(`openapi.user.json`, 포트 12301)를
`app.clients.krtour_map.KrtourMapClient`로 호출한다(ADR-026/027). TripMate 책임: 권한 /
좌표 validation / 사용자 컨텍스트 / 응답 schema 투영 / 에러·저하 정책(T-178). krtour 책임:
정규화 / 클러스터링 / dedup / sources / weather.

`POST /features/requests` 큐(T-177)는 krtour를 직접 호출하지 않고 `app.feature_suggestions`
에만 적재한다 — Admin 검토 후 krtour feature change API 반영은 T-179.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, cast

from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.krtour_map import (
    KrtourMapBadRequest,
    KrtourMapFeatureNotFound,
    KrtourMapHttpClientDep,
    KrtourMapRateLimited,
    KrtourMapUnavailable,
)
from app.core.deps import CurrentUserId, DbSession
from app.models.feature_suggestion import FeatureSuggestion
from app.schemas.envelope import Envelope
from app.schemas.feature import (
    BBox,
    Coord,
    FeatureCategory,
    FeatureCluster,
    FeatureDetail,
    FeatureKind,
    FeatureRequestCreate,
    FeatureRequestResponse,
    FeatureRequestStatus,
    FeatureRequestType,
    FeaturesInBoundsResponse,
    FeatureSummary,
    FeatureWeatherCard,
    WeatherMetric,
)

router = APIRouter(prefix="/features", tags=["features"])

# 허용 viewport 한국 범위 (ADR-018)
LNG_MIN, LNG_MAX = 124.0, 132.0
LAT_MIN, LAT_MAX = 33.0, 43.0
MIN_ZOOM, MAX_ZOOM = 5, 19
FEATURE_SUGGESTION_DAILY_LIMIT = 20
DECIMAL_6 = Decimal("0.000001")
_DEFAULT_INBOUNDS_KINDS: list[FeatureKind] = ["place", "event", "notice"]
_DEFAULT_NEARBY_KINDS: list[FeatureKind] = ["place"]


@contextmanager
def _map_krtour_errors() -> Iterator[None]:
    """krtour-map 도메인 예외 → HTTP status 변환 (T-178 저하 정책).

    transient(타임아웃/연결/5xx) = 503 FEATURE_SERVICE_UNAVAILABLE,
    429/409 = RATE_LIMITED(+Retry-After), 4xx = 422, 404 = RESOURCE_NOT_FOUND.
    """
    try:
        yield
    except KrtourMapFeatureNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Feature not found."},
        ) from exc
    except KrtourMapRateLimited as exc:
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if exc.retry_after_seconds is not None
            else None
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMITED", "message": "요청이 많아 잠시 후 다시 시도하세요."},
            headers=headers,
        ) from exc
    except KrtourMapBadRequest as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": exc.code or "VALIDATION_ERROR",
                "message": "잘못된 feature 요청입니다.",
            },
        ) from exc
    except KrtourMapUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "FEATURE_SERVICE_UNAVAILABLE",
                "message": "지도 feature 서비스가 일시적으로 사용 불가합니다.",
            },
        ) from exc


def _parse_bbox(bbox_str: str) -> BBox:
    """`lng_min,lat_min,lng_max,lat_max` → BBox."""
    parts = bbox_str.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "bbox 는 'lng_min,lat_min,lng_max,lat_max' 형식이어야 합니다.",
            },
        )
    try:
        nums = [float(p) for p in parts]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "VALIDATION_ERROR", "message": "bbox 숫자 변환 실패."},
        ) from exc
    return BBox(lng_min=nums[0], lat_min=nums[1], lng_max=nums[2], lat_max=nums[3])


def _coord_from_krtour(dto: dict[str, Any]) -> Coord | None:
    """krtour 평면 `lon`/`lat`(nullable) → Coord | None."""
    lon = dto.get("lon")
    lat = dto.get("lat")
    if lon is None or lat is None:
        return None
    return Coord(lon=float(lon), lat=float(lat))


def _summary_from_krtour(dto: dict[str, Any]) -> FeatureSummary:
    """krtour `FeatureSummary`/`NearbyFeatureSummary` → TripMate FeatureSummary."""
    distance = dto.get("distance_m")
    return FeatureSummary(
        feature_id=str(dto["feature_id"]),
        kind=dto["kind"],
        name=dto.get("name") or dto.get("title") or "",
        coord=_coord_from_krtour(dto),
        category=dto.get("category"),
        marker_color=dto.get("marker_color") or "P-13",
        marker_icon=dto.get("marker_icon") or "marker",
        status=dto.get("status"),
        distance_m=float(distance) if distance is not None else None,
    )


def _cluster_from_krtour(dto: dict[str, Any]) -> FeatureCluster:
    """krtour `ClusterSummary` → TripMate FeatureCluster (cluster_key = 행정코드 자연키)."""
    return FeatureCluster(
        cluster_key=str(dto["cluster_key"]),
        coord=Coord(lon=float(dto["lon"]), lat=float(dto["lat"])),
        feature_count=int(dto["feature_count"]),
    )


def _detail_from_krtour(dto: dict[str, Any]) -> FeatureDetail:
    """krtour `FeatureDetailResponse` → TripMate FeatureDetail."""
    address = dto.get("address")
    return FeatureDetail(
        feature_id=str(dto["feature_id"]),
        kind=dto["kind"],
        name=dto.get("name") or dto.get("title") or "",
        coord=_coord_from_krtour(dto),
        category=dto.get("category"),
        address=address if isinstance(address, dict) else None,
        legal_dong_code=dto.get("legal_dong_code"),
        sido_code=dto.get("sido_code"),
        sigungu_code=dto.get("sigungu_code"),
        marker_color=dto.get("marker_color") or "P-13",
        marker_icon=dto.get("marker_icon") or "marker",
        urls=dto.get("urls") if isinstance(dto.get("urls"), dict) else {},
        detail=dto.get("detail") if isinstance(dto.get("detail"), dict) else {},
        status=dto.get("status"),
        updated_at=dto.get("updated_at") or datetime.now(UTC),
    )


def _weather_metric_from_krtour(metric: dict[str, Any]) -> WeatherMetric:
    return WeatherMetric(
        metric_key=str(metric["metric_key"]),
        metric_name=metric.get("metric_name"),
        forecast_style=str(metric.get("forecast_style") or "observed"),
        timeline_bucket=metric.get("timeline_bucket"),
        valid_at=metric.get("valid_at"),
        issued_at=metric.get("issued_at"),
        observed_at=metric.get("observed_at"),
        value_number=metric.get("value_number"),
        value_text=metric.get("value_text"),
        unit=metric.get("unit"),
        severity=metric.get("severity"),
    )


def _weather_from_krtour(dto: dict[str, Any], *, feature_id: str) -> FeatureWeatherCard:
    """krtour `WeatherCardData` → TripMate FeatureWeatherCard (평탄 metric 목록)."""
    metrics = [
        _weather_metric_from_krtour(m) for m in dto.get("metrics", []) if isinstance(m, dict)
    ]
    return FeatureWeatherCard(
        feature_id=str(dto.get("feature_id") or feature_id),
        asof=dto.get("asof"),
        latest_at=dto.get("latest_at"),
        is_stale=bool(dto.get("is_stale", False)),
        source_styles=list(dto.get("source_styles", [])),
        metrics=metrics,
    )


def _category_from_krtour(dto: dict[str, Any]) -> FeatureCategory:
    """krtour `CategorySummary` → TripMate FeatureCategory."""
    return FeatureCategory(
        code=str(dto["code"]),
        label=str(dto.get("label") or dto["code"]),
        parent_code=dto.get("parent_code"),
        depth=int(dto.get("depth", 0)),
        path=[str(p) for p in dto.get("path", [])],
        maki_icon=str(dto.get("maki_icon") or "marker"),
        is_active=bool(dto.get("is_active", True)),
        sort_order=int(dto.get("sort_order", 0)),
    )


def _current_user_uuid(current_user_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(current_user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_INVALID", "message": "토큰 sub 클레임이 잘못되었습니다."},
        ) from exc


def _decimal6(value: float) -> Decimal:
    return Decimal(str(value)).quantize(DECIMAL_6)


def _normalise_title(title: str) -> str:
    normalised = " ".join(title.split())
    if not normalised:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": "title 은 공백만 입력할 수 없습니다."},
        )
    return normalised


def _normalise_categories(categories: list[str]) -> list[str]:
    seen: set[str] = set()
    normalised: list[str] = []
    for raw in categories:
        category = " ".join(raw.split())
        key = category.lower()
        if category and key not in seen:
            normalised.append(category)
            seen.add(key)
    return normalised


def _feature_request_response(row: FeatureSuggestion) -> FeatureRequestResponse:
    return FeatureRequestResponse(
        request_id=row.request_id,
        status=cast(FeatureRequestStatus, row.status),
        type=cast(FeatureRequestType, row.suggestion_type),
        kind=cast(FeatureKind, row.kind),
        title=row.name,
        coord=Coord(lon=float(row.lng), lat=float(row.lat)),
        categories=row.categories,
        note=row.note,
        target_feature_id=row.target_feature_id,
        created_at=row.created_at,
        resolved_at=row.resolved_at,
    )


async def _find_duplicate_feature_suggestion(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    suggestion_type: str,
    target_feature_id: str | None,
    kind: str,
    name: str,
    lng: Decimal,
    lat: Decimal,
) -> FeatureSuggestion | None:
    row = await db.scalar(
        select(FeatureSuggestion)
        .where(
            FeatureSuggestion.requester_user_id == user_id,
            FeatureSuggestion.status == "pending",
            FeatureSuggestion.suggestion_type == suggestion_type,
            FeatureSuggestion.target_feature_id.is_not_distinct_from(target_feature_id),
            FeatureSuggestion.kind == kind,
            func.lower(FeatureSuggestion.name) == name.lower(),
            FeatureSuggestion.lng == lng,
            FeatureSuggestion.lat == lat,
        )
        .order_by(FeatureSuggestion.created_at.desc())
    )
    return row


async def _enforce_feature_suggestion_rate_limit(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> None:
    since = datetime.now(UTC) - timedelta(days=1)
    # 거절/중복(rejected/duplicate)은 한도 카운트에서 제외 — 거절 많이 받은 사용자가 정당한
    # 신규 제안을 못 하는 것을 방지(#108 리뷰). pending/approved/added만 남용 신호로 본다.
    submitted = await db.scalar(
        select(func.count(FeatureSuggestion.request_id)).where(
            FeatureSuggestion.requester_user_id == user_id,
            FeatureSuggestion.created_at >= since,
            FeatureSuggestion.status.in_(("pending", "approved", "added")),
        )
    )
    if int(submitted or 0) >= FEATURE_SUGGESTION_DAILY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMITED",
                "message": "feature 제안은 사용자당 24시간에 20건까지 등록할 수 있습니다.",
            },
            headers={"Retry-After": "86400"},
        )


@router.get("/in-bounds", response_model=Envelope[FeaturesInBoundsResponse])
async def features_in_bounds(
    _current_user: CurrentUserId,
    client: KrtourMapHttpClientDep,
    bbox: Annotated[str, Query(description="lng_min,lat_min,lng_max,lat_max")],
    zoom: Annotated[int, Query(ge=MIN_ZOOM, le=MAX_ZOOM)],
    kinds: Annotated[list[FeatureKind] | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    cluster_unit: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> Envelope[FeaturesInBoundsResponse]:
    """viewport 내 feature(`items`) + 서버 클러스터(`clusters`). 클러스터링은 krtour 책임."""
    bbox_obj = _parse_bbox(bbox)
    with _map_krtour_errors():
        data = await client.features_in_bounds(
            min_lon=bbox_obj.lng_min,
            min_lat=bbox_obj.lat_min,
            max_lon=bbox_obj.lng_max,
            max_lat=bbox_obj.lat_max,
            kinds=[str(k) for k in (kinds or _DEFAULT_INBOUNDS_KINDS)],
            category=category,
            zoom=zoom,
            cluster_unit=cluster_unit,
            max_items=limit,
        )
    items = [_summary_from_krtour(x) for x in data.get("items", []) if isinstance(x, dict)]
    clusters = [_cluster_from_krtour(x) for x in data.get("clusters", []) if isinstance(x, dict)]
    return Envelope.of(
        FeaturesInBoundsResponse(
            items=items,
            clusters=clusters,
            cluster_unit=data.get("cluster_unit"),
            zoom=zoom,
            bbox=bbox_obj,
        )
    )


@router.get("/nearby", response_model=Envelope[list[FeatureSummary]])
async def features_nearby(
    _current_user: CurrentUserId,
    client: KrtourMapHttpClientDep,
    lon: Annotated[float, Query(ge=LNG_MIN, le=LNG_MAX)],
    lat: Annotated[float, Query(ge=LAT_MIN, le=LAT_MAX)],
    radius_m: Annotated[int, Query(ge=10, le=50000)],
    kinds: Annotated[list[FeatureKind] | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Envelope[list[FeatureSummary]]:
    """반경 검색 (distance_m 포함). location_audit 미들웨어가 좌표 query 자동 적재."""
    with _map_krtour_errors():
        data = await client.features_nearby(
            lon=lon,
            lat=lat,
            radius_m=radius_m,
            kinds=[str(k) for k in (kinds or _DEFAULT_NEARBY_KINDS)],
            category=category,
            page_size=limit,
        )
    return Envelope.of(
        [_summary_from_krtour(x) for x in data.get("items", []) if isinstance(x, dict)]
    )


@router.get("/search", response_model=Envelope[list[FeatureSummary]])
async def search_features(
    _current_user: CurrentUserId,
    client: KrtourMapHttpClientDep,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    kinds: Annotated[list[FeatureKind] | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    bbox: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Envelope[list[FeatureSummary]]:
    """자유 텍스트 검색 (feature 파트만 — 검색 인덱스/ranking은 krtour 책임)."""
    bbox_obj = _parse_bbox(bbox) if bbox else None
    with _map_krtour_errors():
        data = await client.search_features(
            q=q,
            min_lon=bbox_obj.lng_min if bbox_obj else None,
            min_lat=bbox_obj.lat_min if bbox_obj else None,
            max_lon=bbox_obj.lng_max if bbox_obj else None,
            max_lat=bbox_obj.lat_max if bbox_obj else None,
            kinds=[str(k) for k in kinds] if kinds else None,
            category=category,
            page_size=limit,
        )
    return Envelope.of(
        [_summary_from_krtour(x) for x in data.get("items", []) if isinstance(x, dict)]
    )


@router.get("/requests/{request_id}", response_model=Envelope[FeatureRequestResponse])
async def get_feature_request(
    request_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> Envelope[FeatureRequestResponse]:
    """사용자 본인이 등록한 feature 제안 큐 1건을 조회한다."""
    user_id = _current_user_uuid(current_user_id)
    row = await db.scalar(
        select(FeatureSuggestion).where(
            FeatureSuggestion.request_id == request_id,
            FeatureSuggestion.requester_user_id == user_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Feature request not found."},
        )
    return Envelope.of(_feature_request_response(row))


@router.get("/categories", response_model=Envelope[list[FeatureCategory]])
async def list_feature_categories(
    _current_user: CurrentUserId,
    client: KrtourMapHttpClientDep,
    active_only: Annotated[bool, Query()] = True,
) -> Envelope[list[FeatureCategory]]:
    """krtour 카테고리 카탈로그 (마커 범례 / 필터 칩). 저빈도 → 클라이언트 긴 TTL 캐시 권장."""
    with _map_krtour_errors():
        data = await client.categories(active_only=active_only)
    return Envelope.of(
        [_category_from_krtour(c) for c in data.get("items", []) if isinstance(c, dict)]
    )


@router.get("/{feature_id}", response_model=Envelope[FeatureDetail])
async def get_feature(
    feature_id: Annotated[str, Path(min_length=1, max_length=200)],
    _current_user: CurrentUserId,
    client: KrtourMapHttpClientDep,
) -> Envelope[FeatureDetail]:
    """feature 1건 상세."""
    with _map_krtour_errors():
        dto = await client.get_feature(feature_id)
    if dto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Feature not found."},
        )
    return Envelope.of(_detail_from_krtour(dto))


@router.get("/{feature_id}/weather", response_model=Envelope[FeatureWeatherCard])
async def get_feature_weather(
    feature_id: Annotated[str, Path(min_length=1, max_length=200)],
    _current_user: CurrentUserId,
    client: KrtourMapHttpClientDep,
    asof: Annotated[datetime | None, Query()] = None,
) -> Envelope[FeatureWeatherCard]:
    """weather card — krtour 평탄 metric 목록 + source_styles."""
    with _map_krtour_errors():
        dto = await client.feature_weather(feature_id, asof=asof)
    return Envelope.of(_weather_from_krtour(dto, feature_id=feature_id))


@router.post(
    "/requests",
    response_model=Envelope[FeatureRequestResponse],
    status_code=status.HTTP_201_CREATED,
)
async def request_feature(
    body: FeatureRequestCreate,
    current_user_id: CurrentUserId,
    db: DbSession,
    request: Request,
) -> Envelope[FeatureRequestResponse]:
    """사용자가 feature 제안을 TripMate 소유 큐에 등록한다. krtour-map 직접 호출은 하지 않는다."""
    user_id = _current_user_uuid(current_user_id)
    name = _normalise_title(body.title)
    lng = _decimal6(body.coord.lon)
    lat = _decimal6(body.coord.lat)
    request.state.location_audit_coord = (lat, lng)
    categories = _normalise_categories(body.categories)

    duplicate = await _find_duplicate_feature_suggestion(
        db,
        user_id=user_id,
        suggestion_type=body.type,
        target_feature_id=body.target_feature_id,
        kind=body.kind,
        name=name,
        lng=lng,
        lat=lat,
    )
    if duplicate is not None:
        return Envelope.of(_feature_request_response(duplicate))

    await _enforce_feature_suggestion_rate_limit(db, user_id=user_id)
    row = FeatureSuggestion(
        requester_user_id=user_id,
        suggestion_type=body.type,
        target_feature_id=body.target_feature_id,
        kind=body.kind,
        name=name,
        lng=lng,
        lat=lat,
        categories=categories,
        note=body.note,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        duplicate = await _find_duplicate_feature_suggestion(
            db,
            user_id=user_id,
            suggestion_type=body.type,
            target_feature_id=body.target_feature_id,
            kind=body.kind,
            name=name,
            lng=lng,
            lat=lat,
        )
        if duplicate is not None:
            return Envelope.of(_feature_request_response(duplicate))
        raise
    await db.refresh(row)
    return Envelope.of(_feature_request_response(row))
