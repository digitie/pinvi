"""`/features/*` — `docs/api/features.md`.

라이브러리 `python-krtour-map` 의 `AsyncKrtourMapClient` 를 호출 wrapping (ADR-002).
TripMate 책임: 권한 / 좌표 validation / 사용자 컨텍스트 / 응답 schema.
라이브러리 책임: 정규화 / 클러스터링 / dedup / sources / overrides / weather.

본 라우터는 라이브러리 client 미주입 (Sprint 2 라이브러리 진행 중) 시 503 응답
(`docs/architecture/mcp-server.md` 와 비슷한 placeholder 패턴이 아닌, 실제
라이브러리 lifespan이 ready 후 동작).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, cast

from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUserId, DbSession
from app.etl_bridge.krtour_map import KrtourMapClientDep
from app.models.feature_suggestion import FeatureSuggestion
from app.schemas.envelope import Envelope
from app.schemas.feature import (
    BBox,
    Coord,
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
)

router = APIRouter(prefix="/features", tags=["features"])

# 허용 viewport 한국 범위 (ADR-018)
LNG_MIN, LNG_MAX = 124.0, 132.0
LAT_MIN, LAT_MAX = 33.0, 43.0
MIN_ZOOM, MAX_ZOOM = 5, 19
FEATURE_SUGGESTION_DAILY_LIMIT = 20
DECIMAL_6 = Decimal("0.000001")


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


def _summary_from_dto(dto: dict[str, Any]) -> FeatureSummary:
    """라이브러리 DTO → TripMate FeatureSummary."""
    return FeatureSummary(
        feature_id=str(dto["feature_id"]),
        kind=dto["kind"],
        title=dto["title"],
        coord=Coord(lon=dto["coord"]["longitude"], lat=dto["coord"]["latitude"]),
        marker_color=dto.get("marker_color", "P-13"),
        marker_icon=dto.get("marker_icon", "marker"),
        category=dto.get("category"),
        summary=dto.get("summary"),
    )


def _cluster_from_dto(dto: dict[str, Any]) -> FeatureCluster:
    return FeatureCluster(
        cluster_id=str(dto["cluster_id"]),
        center=Coord(lon=dto["center"]["longitude"], lat=dto["center"]["latitude"]),
        feature_count=int(dto["feature_count"]),
        sample_kinds=list(dto.get("sample_kinds", [])),
        bbox=BBox(**dto["bbox"]),
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
    client: KrtourMapClientDep,
    bbox: Annotated[str, Query(description="lng_min,lat_min,lng_max,lat_max")],
    zoom: Annotated[int, Query(ge=MIN_ZOOM, le=MAX_ZOOM)],
    kinds: Annotated[list[FeatureKind] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> Envelope[FeaturesInBoundsResponse]:
    """viewport 내 feature 목록 (개별 + 클러스터). zoom별 클러스터링은 라이브러리 책임."""
    bbox_obj = _parse_bbox(bbox)
    items = await client.features_in_bounds(
        bbox_obj.as_tuple(),
        kinds=list(kinds) if kinds else ["place", "event", "notice"],
        zoom=zoom,
        limit=limit,
    )
    features: list[FeatureSummary] = []
    clusters: list[FeatureCluster] = []
    for item in items:
        if item.get("type") == "cluster":
            clusters.append(_cluster_from_dto(item))
        else:
            features.append(_summary_from_dto(item))
    return Envelope.of(
        FeaturesInBoundsResponse(features=features, clusters=clusters, zoom=zoom, bbox=bbox_obj)
    )


@router.get("/nearby", response_model=Envelope[list[FeatureSummary]])
async def features_nearby(
    _current_user: CurrentUserId,
    client: KrtourMapClientDep,
    lon: Annotated[float, Query(ge=LNG_MIN, le=LNG_MAX)],
    lat: Annotated[float, Query(ge=LAT_MIN, le=LAT_MAX)],
    radius_m: Annotated[int, Query(ge=10, le=50000)],
    kinds: Annotated[list[FeatureKind] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Envelope[list[FeatureSummary]]:
    """반경 검색 — `coord_5179` 기반 (라이브러리 책임). location_audit 미들웨어가
    좌표 query 자동 감지 후 `app.location_access_log` chain 적재."""
    items = await client.features_nearby(
        lon=lon,
        lat=lat,
        radius_m=radius_m,
        kinds=list(kinds) if kinds else ["place"],
        limit=limit,
    )
    return Envelope.of([_summary_from_dto(item) for item in items])


@router.get("/search", response_model=Envelope[list[FeatureSummary]])
async def search_features(
    _current_user: CurrentUserId,
    client: KrtourMapClientDep,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    kinds: Annotated[list[FeatureKind] | None, Query()] = None,
    bbox: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Envelope[list[FeatureSummary]]:
    """자유 텍스트 검색 (FTS5 또는 pg_trgm — 라이브러리 책임)."""
    bbox_tuple = _parse_bbox(bbox).as_tuple() if bbox else None
    items = await client.search(
        q=q,
        kinds=list(kinds) if kinds else None,
        bbox=bbox_tuple,
        limit=limit,
    )
    return Envelope.of([_summary_from_dto(item) for item in items])


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


@router.get("/{feature_id}", response_model=Envelope[FeatureDetail])
async def get_feature(
    feature_id: Annotated[str, Path(min_length=1, max_length=200)],
    _current_user: CurrentUserId,
    client: KrtourMapClientDep,
) -> Envelope[FeatureDetail]:
    """feature 1건 상세."""
    dto = await client.get_feature(feature_id)
    if dto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Feature not found."},
        )
    return Envelope.of(
        FeatureDetail(
            feature_id=str(dto["feature_id"]),
            kind=dto["kind"],
            title=dto["title"],
            coord=Coord(lon=dto["coord"]["longitude"], lat=dto["coord"]["latitude"]),
            marker_color=dto.get("marker_color", "P-13"),
            marker_icon=dto.get("marker_icon", "marker"),
            category=dto.get("category"),
            address=dto.get("address"),
            address_road=dto.get("address_road"),
            bjd_code=dto.get("bjd_code"),
            sigungu_code=dto.get("sigungu_code"),
            description=dto.get("description"),
            detail=dto.get("detail", {}),
            source_ids=list(dto.get("source_ids", [])),
            updated_at=dto.get("updated_at") or datetime.now(UTC),
        )
    )


@router.get("/{feature_id}/weather", response_model=Envelope[FeatureWeatherCard])
async def get_feature_weather(
    feature_id: Annotated[str, Path(min_length=1, max_length=200)],
    _current_user: CurrentUserId,
    client: KrtourMapClientDep,
) -> Envelope[FeatureWeatherCard]:
    """KMA 시간축 weather card — 라이브러리가 sources 배열 포함 반환."""
    asof = datetime.now(UTC)
    dto = await client.build_weather_card(feature_id, asof=asof)
    return Envelope.of(
        FeatureWeatherCard(
            feature_id=str(dto.get("feature_id") or feature_id),
            asof=dto.get("asof") or asof,
            short_term=dto.get("short_term", []),
            daily=dto.get("daily", []),
            sources=list(dto.get("sources", [])),
        )
    )


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
