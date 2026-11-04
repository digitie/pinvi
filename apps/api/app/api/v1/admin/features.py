"""`/admin/features/*` — kor-travel-map admin feature read proxy (T-209)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError

from app.api.v1.features import normalize_asof_query
from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapConflict,
    KorTravelMapError,
    KorTravelMapFeatureNotFound,
    KorTravelMapPreconditionFailed,
    KorTravelMapRateLimited,
    KorTravelMapUnavailable,
    OptionalKorTravelMapHttpClientDep,
)
from app.clients.kor_travel_map_admin import KorTravelMapAdminClientDep
from app.clients.kor_travel_map_weather import create_map_weather_client
from app.clients.kor_travel_weather import OptionalKorTravelWeatherClientDep
from app.core.config import settings
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import (
    AdminFeatureDetail,
    AdminFeatureLifecycleState,
    AdminFeatureOverridesResponse,
    AdminFeaturePagedResponse,
    AdminFeaturePublicationState,
    AdminFeatureQualityState,
    AdminFeatureSort,
    AdminFeatureSortOrder,
    AdminFeatureSourcesResponse,
    AdminFeatureSummary,
    AdminFeatureWeatherValuesResponse,
)
from app.schemas.envelope import Envelope
from app.services.admin_weather_values import build_admin_feature_weather_values

router = APIRouter(prefix="/admin/features", tags=["admin"])


@contextmanager
def _map_admin_errors() -> Iterator[None]:
    """kor_travel_map admin read 예외 → Pinvi admin HTTP error."""
    try:
        yield
    except KorTravelMapFeatureNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "대상 feature를 kor_travel_map에서 찾을 수 없습니다.",
            },
        ) from exc
    except KorTravelMapRateLimited as exc:
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if exc.retry_after_seconds is not None
            else None
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMITED",
                "message": "kor_travel_map 요청이 많아 잠시 후 다시 시도하세요.",
            },
            headers=headers,
        ) from exc
    except KorTravelMapBadRequest as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": exc.code or "VALIDATION_ERROR",
                "message": "kor_travel_map가 feature admin 요청을 거절했습니다.",
            },
        ) from exc
    except KorTravelMapConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code or "INVALID_STATE",
                "message": "kor_travel_map change request 상태가 현재 작업을 허용하지 않습니다.",
            },
        ) from exc
    except KorTravelMapPreconditionFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={
                "code": exc.code or "PRECONDITION_FAILED",
                "message": "feature가 변경되었습니다. 최신 정보를 확인한 뒤 다시 시도하세요.",
            },
        ) from exc
    except KorTravelMapUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "FEATURE_SERVICE_UNAVAILABLE",
                "message": "kor_travel_map admin 서비스가 일시적으로 사용 불가합니다.",
            },
        ) from exc
    except KorTravelMapError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map admin 응답 형식이 올바르지 않습니다.",
            },
        ) from exc


def _next_cursor(meta: dict[str, Any]) -> str | None:
    page = meta.get("page")
    if not isinstance(page, dict):
        return None
    value = page.get("next_cursor")
    return value if isinstance(value, str) and value else None


def _duration_ms(meta: dict[str, Any]) -> int | None:
    value = meta.get("duration_ms")
    return value if isinstance(value, int) else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _validate_feature_detail(data: dict[str, Any]) -> AdminFeatureDetail:
    try:
        return AdminFeatureDetail.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map admin 상세 응답 형식이 올바르지 않습니다.",
            },
        ) from exc


@router.get("", response_model=Envelope[AdminFeaturePagedResponse])
async def list_features_endpoint(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
    q: Annotated[str | None, Query(description="name/address/feature/source 검색")] = None,
    kind: Annotated[list[str] | None, Query(description="feature kind 반복 필터")] = None,
    category: Annotated[list[str] | None, Query(description="category 반복 필터")] = None,
    lifecycle_state: Annotated[
        list[AdminFeatureLifecycleState] | None,
        Query(description="lifecycle 축 반복 필터 (active/retired)"),
    ] = None,
    publication_state: Annotated[
        list[AdminFeaturePublicationState] | None,
        Query(description="publication 축 반복 필터 (draft/published/suppressed)"),
    ] = None,
    quality_state: Annotated[
        list[AdminFeatureQualityState] | None,
        Query(description="quality 축 반복 필터 (valid/quarantined)"),
    ] = None,
    provider_dataset_id: Annotated[
        int | None,
        Query(ge=1, description="primary provider dataset canonical ID 필터"),
    ] = None,
    has_coord: Annotated[bool | None, Query()] = None,
    has_issue: Annotated[bool | None, Query()] = None,
    issue_type: Annotated[list[str] | None, Query()] = None,
    updated_from: Annotated[datetime | None, Query()] = None,
    updated_to: Annotated[datetime | None, Query()] = None,
    include_ended: Annotated[
        bool,
        Query(description="종료된 notice 포함 여부. 기본 false."),
    ] = False,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: Annotated[str | None, Query()] = None,
    sort: Annotated[AdminFeatureSort, Query()] = "name",
    order: Annotated[AdminFeatureSortOrder, Query()] = "asc",
) -> Envelope[AdminFeaturePagedResponse]:
    """kor-travel-map `/v1/admin/features` 목록 proxy.

    필터 이름은 Map upstream query와 1:1이다. legacy `status`/`provider`/`dataset_key`는
    Map 3축 cutover(`1f2bdc3a`) 이후 upstream에 존재하지 않으며, 계속 보내면 FastAPI가
    조용히 버려 "필터가 걸린 척하는" 전량 응답이 된다 — 그래서 여기서도 받지 않는다.
    """
    with _map_admin_errors():
        payload = await admin_client.list_features(
            q=q,
            kinds=kind,
            categories=category,
            lifecycle_states=lifecycle_state,
            publication_states=publication_state,
            quality_states=quality_state,
            provider_dataset_id=provider_dataset_id,
            has_coord=has_coord,
            has_issue=has_issue,
            issue_types=issue_type,
            updated_from=_iso(updated_from),
            updated_to=_iso(updated_to),
            include_ended=include_ended,
            page_size=page_size,
            cursor=cursor,
            sort=sort,
            order=order,
        )
    data = payload.get("data")
    meta = payload.get("meta")
    if not isinstance(data, dict) or not isinstance(meta, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map admin 목록 응답 형식이 올바르지 않습니다.",
            },
        )
    items = data.get("items")
    if not isinstance(items, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map admin 목록에 items가 없습니다.",
            },
        )
    try:
        summaries = [AdminFeatureSummary.model_validate(item) for item in items]
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map admin 목록 item 형식이 올바르지 않습니다.",
            },
        ) from exc
    return Envelope.of(
        AdminFeaturePagedResponse(
            items=summaries,
            page_size=page_size,
            next_cursor=_next_cursor(meta),
            duration_ms=_duration_ms(meta),
        )
    )


@router.get(
    "/{feature_id}/sources",
    response_model=Envelope[AdminFeatureSourcesResponse],
)
async def get_feature_sources_endpoint(
    feature_id: str,
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
) -> Envelope[AdminFeatureSourcesResponse]:
    """kor-travel-map admin 상세의 source links만 read-only tab 응답으로 투영."""
    with _map_admin_errors():
        data = await admin_client.get_feature_detail(feature_id)
    detail = _validate_feature_detail(data)
    return Envelope.of(
        AdminFeatureSourcesResponse(feature_id=detail.feature.feature_id, items=detail.sources)
    )


@router.get(
    "/{feature_id}/overrides",
    response_model=Envelope[AdminFeatureOverridesResponse],
)
async def get_feature_overrides_endpoint(
    feature_id: str,
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
) -> Envelope[AdminFeatureOverridesResponse]:
    """kor-travel-map admin 상세의 override history만 read-only tab 응답으로 투영."""
    with _map_admin_errors():
        data = await admin_client.get_feature_detail(feature_id)
    detail = _validate_feature_detail(data)
    return Envelope.of(
        AdminFeatureOverridesResponse(feature_id=detail.feature.feature_id, items=detail.overrides)
    )


@router.get(
    "/{feature_id}/weather-values",
    response_model=Envelope[AdminFeatureWeatherValuesResponse],
)
async def get_feature_weather_values_endpoint(
    feature_id: str,
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
    db: DbSession,
    weather_client: OptionalKorTravelWeatherClientDep,
    map_client: OptionalKorTravelMapHttpClientDep,
    asof: Annotated[datetime | None, Query()] = None,
) -> Envelope[AdminFeatureWeatherValuesResponse]:
    """관리자 상세 좌표와 사용자와 같은 소스 설정으로 정본 weather 사실을 조회한다.

    Map 모드의 관측·예보는 Map, 특보는 선택적인 직접 weather 경로다. 직접 모드와
    asof 축소는 기존 계약을 유지한다. Map 원천 dataset provenance는 지어내지 않는다.
    """
    map_mode = settings.pinvi_kor_travel_map_weather_enabled
    map_weather_client = (
        create_map_weather_client(map_client)
        if map_mode and map_client is not None and map_client.has_service_token
        else None
    )
    if (map_mode and map_weather_client is None) or (not map_mode and weather_client is None):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "WEATHER_SERVICE_UNAVAILABLE",
                "message": "날씨 서비스가 일시적으로 사용 불가합니다.",
            },
        )
    with _map_admin_errors():
        detail_payload = await admin_client.get_feature_detail(feature_id)
    detail = _validate_feature_detail(detail_payload)
    lon, lat = detail.feature.lon, detail.feature.lat
    if lon is None or lat is None:
        return Envelope.of(AdminFeatureWeatherValuesResponse(feature_id=feature_id, asof=asof))
    normalized_asof = normalize_asof_query(asof)
    return Envelope.of(
        await build_admin_feature_weather_values(
            db,
            feature_id=feature_id,
            lat=lat,
            lon=lon,
            asof=normalized_asof,
            weather_client=weather_client,
            map_weather_client=map_weather_client,
            map_budget_seconds=settings.pinvi_kor_travel_map_weather_request_budget_seconds,
        )
    )


@router.get("/{feature_id}", response_model=Envelope[AdminFeatureDetail])
async def get_feature_endpoint(
    feature_id: str,
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
) -> Envelope[AdminFeatureDetail]:
    """kor-travel-map `/v1/admin/features/{feature_id}` 상세 proxy."""
    with _map_admin_errors():
        data = await admin_client.get_feature_detail(feature_id)
    return Envelope.of(_validate_feature_detail(data))
