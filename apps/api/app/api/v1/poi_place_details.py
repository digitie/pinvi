"""`/trips/{trip_id}/pois/{poi_id}/place-details` — 장소 영업 정보(영업시간·휴무일·전화·웹사이트).

- `GET`: 저장된 값, 없으면 출처에서 한 번 받아 저장한 값. 여행 멤버(viewer 포함)면 볼 수 있다. 출처
  장애는 200 `status="unavailable"`로 조용히 알린다(저장하지 않는다).
- `POST .../refresh`: "다시 읽어오기" — 편집 권한(owner/co_owner/editor)만. 같은 장소 60초에 1회
  (`429 RATE_LIMITED` + `Retry-After`). 출처 장애는 `503 PLACE_DETAILS_UNAVAILABLE`이고 기존 값을 둔다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.clients.kor_travel_map import OptionalKorTravelMapHttpClientDep
from app.core.deps import CurrentUserId, DbSession
from app.models.poi import TripDayPoi
from app.models.poi_place_detail import TripPoiPlaceDetail
from app.schemas.envelope import Envelope
from app.schemas.poi import PoiPlaceDetails
from app.services.poi import PoiNotFoundError, get_poi
from app.services.poi_place_details import (
    REFRESH_INTERVAL,
    PlaceDetailsRefreshTooSoon,
    PlaceDetailsUnavailable,
    get_or_fetch_place_details,
    refresh_place_details,
)
from app.services.trip import (
    TripNotFoundError,
    TripPermissionError,
    get_trip_access,
    get_trip_for_user_write,
)

router = APIRouter(prefix="/trips/{trip_id}/pois", tags=["pois"])


def _to_response(row: TripPoiPlaceDetail) -> PoiPlaceDetails:
    return PoiPlaceDetails(
        poi_id=row.poi_id,
        status="ready" if row.status == "ready" else "empty",
        opening_hours=list(row.opening_hours or []),
        closed_days=row.closed_days,
        phone=row.phone,
        website=row.website,
        sources=dict(row.sources or {}),
        fetched_at=row.fetched_at,
        refresh_available_at=row.fetched_at + REFRESH_INTERVAL,
    )


async def _load_poi(
    db: DbSession, trip_id: uuid.UUID, poi_id: uuid.UUID, user_id: str, *, write: bool
) -> TripDayPoi:
    try:
        if write:
            await get_trip_for_user_write(db, trip_id=trip_id, user_id=uuid.UUID(user_id))
        else:
            await get_trip_access(db, trip_id=trip_id, user_id=uuid.UUID(user_id))
        return await get_poi(db, attachment_id=poi_id, trip_id=trip_id)
    except (TripNotFoundError, PoiNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except TripPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


@router.get("/{poi_id}/place-details", response_model=Envelope[PoiPlaceDetails])
async def get_poi_place_details(
    trip_id: uuid.UUID,
    poi_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
    map_client: OptionalKorTravelMapHttpClientDep,
) -> Envelope[PoiPlaceDetails]:
    poi = await _load_poi(db, trip_id, poi_id, current_user_id, write=False)
    try:
        row = await get_or_fetch_place_details(db, poi=poi, map_client=map_client)
    except PlaceDetailsUnavailable:
        return Envelope.of(PoiPlaceDetails(poi_id=poi_id, status="unavailable"))
    return Envelope.of(_to_response(row))


@router.post("/{poi_id}/place-details/refresh", response_model=Envelope[PoiPlaceDetails])
async def refresh_poi_place_details(
    trip_id: uuid.UUID,
    poi_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
    map_client: OptionalKorTravelMapHttpClientDep,
) -> Envelope[PoiPlaceDetails]:
    poi = await _load_poi(db, trip_id, poi_id, current_user_id, write=True)
    try:
        row = await refresh_place_details(db, poi=poi, map_client=map_client)
    except PlaceDetailsRefreshTooSoon as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMITED",
                "message": f"{exc.retry_after_seconds}초 뒤에 다시 읽어올 수 있습니다.",
            },
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except PlaceDetailsUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "PLACE_DETAILS_UNAVAILABLE",
                "message": "장소 정보를 가져오지 못했습니다. 잠시 뒤 다시 시도해 주세요.",
            },
        ) from exc
    return Envelope.of(_to_response(row))
