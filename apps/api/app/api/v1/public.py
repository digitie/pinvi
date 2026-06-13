"""`/public/*` — 인증 없는 공개 read-only 표면.

해수욕장/축제 공개 데이터는 kor-travel-map `/v1/public/*` user OpenAPI 계약을 HTTP로
소비한다. Pinvi는 응답 envelope, cache header, frontend-facing schema만 투영한다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Response, status

from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapFeatureNotFound,
    KorTravelMapHttpClientDep,
    KorTravelMapRateLimited,
    KorTravelMapUnavailable,
)
from app.schemas.envelope import Envelope, EnvelopeMeta, EnvelopeWithMeta
from app.schemas.public import (
    PublicBeachList,
    PublicBeachView,
    PublicFestivalMonth,
    PublicFestivalMonthly,
    PublicFestivalView,
    PublicMapMarkerLayer,
)

router = APIRouter(prefix="/public", tags=["public"])

_CACHE_CONTROL = "public, max-age=300"


@contextmanager
def _map_kor_travel_map_errors() -> Iterator[None]:
    """kor-travel-map 도메인 예외 → Pinvi HTTP 오류 envelope."""
    try:
        yield
    except KorTravelMapFeatureNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Public feature not found."},
        ) from exc
    except KorTravelMapRateLimited as exc:
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
    except KorTravelMapBadRequest as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": exc.code or "VALIDATION_ERROR",
                "message": "잘못된 public feature 요청입니다.",
            },
        ) from exc
    except KorTravelMapUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "FEATURE_SERVICE_UNAVAILABLE",
                "message": "지도 feature 서비스가 일시적으로 사용 불가합니다.",
            },
        ) from exc


def _set_public_cache(response: Response) -> None:
    response.headers["Cache-Control"] = _CACHE_CONTROL


def _page_meta(data: dict[str, Any], *, limit: int) -> EnvelopeMeta:
    cursor = data.get("next_cursor")
    total = data.get("total")
    return EnvelopeMeta(
        cursor=str(cursor) if cursor is not None else None,
        has_more=cursor is not None,
        total=int(total) if total is not None else None,
        limit=limit,
    )


def _validate_bbox(
    *,
    min_lon: float | None,
    min_lat: float | None,
    max_lon: float | None,
    max_lat: float | None,
) -> None:
    values = (min_lon, min_lat, max_lon, max_lat)
    if any(value is not None for value in values) and any(value is None for value in values):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "bbox 필터는 min_lon/min_lat/max_lon/max_lat를 모두 함께 보내야 합니다.",
            },
        )
    if min_lon is not None and max_lon is not None and min_lon > max_lon:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "VALIDATION_ERROR", "message": "min_lon은 max_lon보다 클 수 없습니다."},
        )
    if min_lat is not None and max_lat is not None and min_lat > max_lat:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "VALIDATION_ERROR", "message": "min_lat은 max_lat보다 클 수 없습니다."},
        )


@router.get("/beaches", response_model=EnvelopeWithMeta[PublicBeachList])
async def list_public_beaches(
    response: Response,
    client: KorTravelMapHttpClientDep,
    sido_code: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    sigungu_code: Annotated[str | None, Query(min_length=5, max_length=5)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
    include_quality: Annotated[bool, Query()] = False,
    include_forecast: Annotated[bool, Query()] = False,
) -> EnvelopeWithMeta[PublicBeachList]:
    """공개 해수욕장 목록."""
    with _map_kor_travel_map_errors():
        data = await client.public_beaches(
            sido_code=sido_code,
            sigungu_code=sigungu_code,
            q=q,
            page_size=page_size,
            cursor=cursor,
            include_quality=include_quality,
            include_forecast=include_forecast,
        )
    _set_public_cache(response)
    return EnvelopeWithMeta.of(
        PublicBeachList(
            items=[
                PublicBeachView.model_validate(item)
                for item in data.get("items", [])
                if isinstance(item, dict)
            ]
        ),
        meta=_page_meta(data, limit=page_size),
    )


@router.get("/beaches/map-markers", response_model=Envelope[PublicMapMarkerLayer])
async def list_public_beach_markers(
    response: Response,
    client: KorTravelMapHttpClientDep,
    min_lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    min_lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    max_lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    max_lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    sido_code: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    sigungu_code: Annotated[str | None, Query(min_length=5, max_length=5)] = None,
    max_items: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> Envelope[PublicMapMarkerLayer]:
    """공개 해수욕장 지도 marker layer."""
    _validate_bbox(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat)
    with _map_kor_travel_map_errors():
        data = await client.public_beach_markers(
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            sido_code=sido_code,
            sigungu_code=sigungu_code,
            max_items=max_items,
        )
    _set_public_cache(response)
    return Envelope.of(PublicMapMarkerLayer.model_validate(data))


@router.get("/beaches/{feature_id}", response_model=Envelope[PublicBeachView])
async def get_public_beach(
    response: Response,
    client: KorTravelMapHttpClientDep,
    feature_id: Annotated[str, Path(min_length=1, max_length=200)],
    include_quality: Annotated[bool, Query()] = False,
    include_forecast: Annotated[bool, Query()] = False,
) -> Envelope[PublicBeachView]:
    """공개 해수욕장 상세."""
    with _map_kor_travel_map_errors():
        data = await client.get_public_beach(
            feature_id, include_quality=include_quality, include_forecast=include_forecast
        )
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Public beach not found."},
        )
    _set_public_cache(response)
    return Envelope.of(PublicBeachView.model_validate(data))


@router.get("/festivals/monthly", response_model=EnvelopeWithMeta[PublicFestivalMonthly])
async def list_public_festivals_monthly(
    response: Response,
    client: KorTravelMapHttpClientDep,
    year: Annotated[int | None, Query(ge=1900, le=2200)] = None,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    sido_code: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    sigungu_code: Annotated[str | None, Query(min_length=5, max_length=5)] = None,
    page_size: Annotated[int, Query(ge=1, le=50)] = 12,
    cursor: Annotated[str | None, Query()] = None,
    include_months: Annotated[bool, Query()] = True,
) -> EnvelopeWithMeta[PublicFestivalMonthly]:
    """공개 월별 축제 목록."""
    with _map_kor_travel_map_errors():
        data = await client.public_festivals_monthly(
            year=year,
            month=month,
            sido_code=sido_code,
            sigungu_code=sigungu_code,
            page_size=page_size,
            cursor=cursor,
            include_months=include_months,
        )
    _set_public_cache(response)
    return EnvelopeWithMeta.of(
        PublicFestivalMonthly(
            months=[
                PublicFestivalMonth.model_validate(item)
                for item in data.get("months", [])
                if isinstance(item, dict)
            ],
            items=[
                PublicFestivalView.model_validate(item)
                for item in data.get("items", [])
                if isinstance(item, dict)
            ],
        ),
        meta=_page_meta(data, limit=page_size),
    )


@router.get("/festivals/map-markers", response_model=Envelope[PublicMapMarkerLayer])
async def list_public_festival_markers(
    response: Response,
    client: KorTravelMapHttpClientDep,
    year: Annotated[int | None, Query(ge=1900, le=2200)] = None,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    min_lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    min_lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    max_lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    max_lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    max_items: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> Envelope[PublicMapMarkerLayer]:
    """공개 축제 지도 marker layer."""
    _validate_bbox(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat)
    with _map_kor_travel_map_errors():
        data = await client.public_festival_markers(
            year=year,
            month=month,
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            max_items=max_items,
        )
    _set_public_cache(response)
    return Envelope.of(PublicMapMarkerLayer.model_validate(data))


@router.get("/festivals/{feature_id}", response_model=Envelope[PublicFestivalView])
async def get_public_festival(
    response: Response,
    client: KorTravelMapHttpClientDep,
    feature_id: Annotated[str, Path(min_length=1, max_length=200)],
) -> Envelope[PublicFestivalView]:
    """공개 축제 상세."""
    with _map_kor_travel_map_errors():
        data = await client.get_public_festival(feature_id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Public festival not found."},
        )
    _set_public_cache(response)
    return Envelope.of(PublicFestivalView.model_validate(data))
