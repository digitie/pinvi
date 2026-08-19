"""`/admin/features/*` — kor-travel-map admin feature read proxy (T-209)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import ValidationError

from app.api.v1.features import normalize_asof_query
from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapConflict,
    KorTravelMapError,
    KorTravelMapFeatureNotFound,
    KorTravelMapHttpClientDep,
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
    """weather card payload → admin weather-values 투영.

    payload는 **user** 표면(`GET /v1/features/{id}/weather[/snapshot]`, user client)에서
    온다. Map bitemporal cutover(`6650aa71`)의 `asof` → `selected_at` 개명이 그대로
    적용되므로 여기서 `selected_at`을 읽는다.

    주의(사실관계): Map admin profile에도 `GET /v1/admin/features/{feature_id}/weather`가
    **존재한다**(query 없음, 응답은 user와 같은 `FeatureWeatherResponse`/`WeatherCardData`).
    두 경로의 차이는 가시성이다 — user 경로는 `public_features` 기반이라 비공개 feature를
    404로 막고, admin 경로는 base `features`(lifecycle=active) 기반이라 비공개까지 본다.
    지금 이 admin tab은 user 카드를 투영하므로 **비공개 feature에서 404가 난다**.
    admin route로 갈아타는 것은 별도 과제다(후속: admin weather 경로 전환).
    """
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
    client: KorTravelMapHttpClientDep,
    asof: Annotated[datetime | None, Query()] = None,
) -> Envelope[AdminFeatureWeatherValuesResponse]:
    """kor-travel-map weather card를 admin deep-link tab용 값 목록으로 투영.

    `asof`는 **반드시** `normalize_asof_query()`(user 라우터 소유)를 통과시킨다. transport는
    aware만 받고(`clients/kor_travel_map.py _require_aware_datetime`) naive → aware 보정은
    시간대 의미를 아는 HTTP 경계 한 곳이 KST로 한다 — 그 helper를 건너뛰고 raw query를 넘기면
    offset 없는 `?asof=2026-07-01T09:00:00`이 transport `ValueError`가 되고, 그 예외는
    KorTravelMap* 계열만 잡는 `_map_admin_errors()`를 뚫고 나가 **500**이 된다(직전 릴리스에서는
    200이었다). user weather 라우터와 같은 helper를 쓰는 것이 두 경계의 시간대 해석이 갈라지지
    않는 유일한 방법이다(user는 KST, admin은 UTC 같은 조용한 분화 차단).

    `ValueError → 422` 방어 매핑은 **의도적으로 넣지 않았다**: `ValueError`는 너무 넓어
    (`int()` 파싱·언패킹 등 평범한 서버 버그가 전부 여기 해당) `_map_admin_errors()`에서 잡으면
    이 파일의 모든 핸들러에서 500이어야 할 결함이 "요청이 잘못됐다"는 422로 위장된다. 여기서
    나는 naive datetime `ValueError`는 사용자 입력 오류가 아니라 **경계가 보정을 빼먹은 코드
    결함**이므로, 조용히 4xx로 덮지 않고 보정 자체를 강제하고 통합 테스트
    (`test_admin_features_api.py`)로 고정한다.
    """
    with _map_admin_errors():
        data = await client.feature_weather(feature_id, asof=normalize_asof_query(asof))
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
