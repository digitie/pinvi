"""`/admin/features/*` — kor-travel-map admin feature read proxy (T-209)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import ValidationError

from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapConflict,
    KorTravelMapError,
    KorTravelMapFeatureNotFound,
    KorTravelMapPreconditionFailed,
    KorTravelMapRateLimited,
    KorTravelMapUnavailable,
)
from app.clients.kor_travel_map_admin import KorTravelMapAdminClientDep
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import (
    AdminFeatureChangeRequestActionRequest,
    AdminFeatureChangeRequestPagedResponse,
    AdminFeatureChangeRequestRecord,
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
from app.services.admin_audit import append_admin_audit

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


def _parse_request_id(value: str | None) -> uuid.UUID:
    if value is None:
        return uuid.uuid4()
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "X-Request-Id 형식이 올바르지 않습니다.",
            },
        ) from exc


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


def _weather_values_from_payload(
    payload: dict[str, Any], *, feature_id: str
) -> AdminFeatureWeatherValuesResponse:
    """Admin weather card의 최신값을 admin weather-values 응답으로 투영."""
    try:
        return AdminFeatureWeatherValuesResponse.model_validate(
            {
                "feature_id": str(payload.get("feature_id") or feature_id),
                # 공개 필드 이름 `asof`는 admin UI 계약이라 유지하고 소스만 갈아끼운다.
                "asof": payload.get("selected_at"),
                "latest_at": payload.get("latest_at"),
                "is_stale": bool(payload.get("is_stale", False)),
                "source_styles": payload.get("source_styles", []),
                "items": payload.get("metrics", []),
            }
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map weather 응답 형식이 올바르지 않습니다.",
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
    "/change-requests",
    response_model=Envelope[AdminFeatureChangeRequestPagedResponse],
)
async def list_feature_change_requests_endpoint(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
    status_filter: Annotated[list[str] | None, Query(alias="status")] = None,
    action: Annotated[list[str] | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Envelope[AdminFeatureChangeRequestPagedResponse]:
    """kor-travel-map `/v1/admin/features/change-requests` queue proxy."""
    with _map_admin_errors():
        data = await admin_client.list_change_requests(
            statuses=status_filter,
            actions=action,
            q=q,
            page_size=page_size,
        )
    items = data.get("items")
    if not isinstance(items, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map admin change request 목록에 items가 없습니다.",
            },
        )
    try:
        records = [AdminFeatureChangeRequestRecord.model_validate(item) for item in items]
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map admin change request 형식이 올바르지 않습니다.",
            },
        ) from exc
    review_mode = data.get("review_mode")
    return Envelope.of(
        AdminFeatureChangeRequestPagedResponse(
            items=records,
            review_mode=review_mode if isinstance(review_mode, str) else None,
            page_size=page_size,
        )
    )


@router.post(
    "/change-requests/{request_id}/approve",
    response_model=Envelope[AdminFeatureChangeRequestRecord],
)
async def approve_feature_change_request_endpoint(
    request_id: str,
    body: AdminFeatureChangeRequestActionRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    admin_client: KorTravelMapAdminClientDep,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminFeatureChangeRequestRecord]:
    """Approve/apply upstream change request and append Pinvi audit."""
    reason = body.kor_travel_map_reason or body.access_reason
    with _map_admin_errors():
        raw = await admin_client.approve_change_request(
            request_id, operator="pinvi-admin", reason=reason
        )
    record = AdminFeatureChangeRequestRecord.model_validate(raw)
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="feature_change_request.approve",
        resource_type="feature_change_request",
        resource_id=request_id,
        before_state=None,
        after_state=record.model_dump(mode="json"),
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )
    await db.commit()
    return Envelope.of(record)


@router.post(
    "/change-requests/{request_id}/reject",
    response_model=Envelope[AdminFeatureChangeRequestRecord],
)
async def reject_feature_change_request_endpoint(
    request_id: str,
    body: AdminFeatureChangeRequestActionRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    admin_client: KorTravelMapAdminClientDep,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminFeatureChangeRequestRecord]:
    """Reject upstream change request and append Pinvi audit."""
    reason = body.kor_travel_map_reason or body.access_reason
    with _map_admin_errors():
        raw = await admin_client.reject_change_request(
            request_id, operator="pinvi-admin", reason=reason
        )
    record = AdminFeatureChangeRequestRecord.model_validate(raw)
    await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="feature_change_request.reject",
        resource_type="feature_change_request",
        resource_id=request_id,
        before_state=None,
        after_state=record.model_dump(mode="json"),
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=_parse_request_id(x_request_id),
    )
    await db.commit()
    return Envelope.of(record)


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
    asof: Annotated[
        datetime | None,
        Query(description="미지원. Map Admin weather 계약은 현재값만 제공한다."),
    ] = None,
) -> Envelope[AdminFeatureWeatherValuesResponse]:
    """비공개 feature도 보이는 Map Admin 최신 weather card를 값 목록으로 투영.

    Map Admin 경로는 `asof` query를 선언하지 않는다. FastAPI upstream이 모르는 query를
    조용히 버리는 일을 막기 위해, 기존 Pinvi query가 오면 현재값으로 가장하지 않고 422로
    명시 거부한다. Admin 시점 조회는 Map에 별도 계약이 생긴 뒤 복원한다.
    """
    if asof is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "admin weather-values는 현재값만 지원하며 asof를 받을 수 없습니다.",
            },
        )
    with _map_admin_errors():
        data = await admin_client.get_feature_weather(feature_id)
    return Envelope.of(_weather_values_from_payload(data, feature_id=feature_id))


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
