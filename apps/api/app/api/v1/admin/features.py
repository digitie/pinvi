"""`/admin/features/*` — kor-travel-map admin feature read proxy (T-209)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError

from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapError,
    KorTravelMapFeatureNotFound,
    KorTravelMapRateLimited,
    KorTravelMapUnavailable,
)
from app.clients.kor_travel_map_admin import KorTravelMapAdminClientDep
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import (
    AdminFeatureDetail,
    AdminFeaturePagedResponse,
    AdminFeatureSort,
    AdminFeatureSortOrder,
    AdminFeatureSummary,
)
from app.schemas.envelope import Envelope

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
                "message": "kor_travel_map가 feature 조회 요청을 거절했습니다.",
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


@router.get("", response_model=Envelope[AdminFeaturePagedResponse])
async def list_features_endpoint(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
    q: Annotated[str | None, Query(description="name/address/feature/source 검색")] = None,
    kind: Annotated[list[str] | None, Query(description="feature kind 반복 필터")] = None,
    category: Annotated[list[str] | None, Query(description="category 반복 필터")] = None,
    feature_status: Annotated[list[str] | None, Query(alias="status")] = None,
    provider: Annotated[list[str] | None, Query(description="primary provider 반복 필터")] = None,
    dataset_key: Annotated[
        list[str] | None, Query(description="primary dataset_key 반복 필터")
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
    """kor-travel-map `/v1/admin/features` 목록 proxy."""
    with _map_admin_errors():
        payload = await admin_client.list_features(
            q=q,
            kinds=kind,
            categories=category,
            statuses=feature_status,
            providers=provider,
            dataset_keys=dataset_key,
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


@router.get("/{feature_id}", response_model=Envelope[AdminFeatureDetail])
async def get_feature_endpoint(
    feature_id: str,
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    admin_client: KorTravelMapAdminClientDep,
) -> Envelope[AdminFeatureDetail]:
    """kor-travel-map `/v1/admin/features/{feature_id}` 상세 proxy."""
    with _map_admin_errors():
        data = await admin_client.get_feature_detail(feature_id)
    try:
        detail = AdminFeatureDetail.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "FEATURE_SERVICE_BAD_GATEWAY",
                "message": "kor_travel_map admin 상세 응답 형식이 올바르지 않습니다.",
            },
        ) from exc
    return Envelope.of(detail)
