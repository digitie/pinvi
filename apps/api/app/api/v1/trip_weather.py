"""`POST /trips/{trip_id}/days/{day_index}/weather/refresh` — 일정 화면 날씨 새로고침(요청 15).

날씨 위치 해석 캐시를 건너뛰고 다시 해석한다(`services/weather_refresh.py` — 무엇을 하고 무엇을 하지 않는지, 속도
제한). 여행을 볼 수 있는 구성원이면 누구나 부를 수 있다(값을 바꾸지 않고 캐시만 새로 한다). 호출자는 응답 뒤
`GET /trips/{trip_id}`로 다시 읽는다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.clients.kor_travel_map import OptionalKorTravelMapHttpClientDep
from app.clients.kor_travel_map_weather import create_map_weather_client
from app.core.config import settings
from app.core.deps import CurrentUserId, DbSession
from app.models.poi import TripDayPoi
from app.schemas.envelope import Envelope
from app.schemas.trip_weather import TripWeatherRefreshRequest, TripWeatherRefreshResponse
from app.services.trip import TripNotFoundError, TripPermissionError, get_trip_access
from app.services.trip_weather_batch import _snapshot_coord
from app.services.weather_refresh import MAX_REFRESH_FEATURES, refresh_weather_locations

router = APIRouter(prefix="/trips", tags=["trips"])


def _http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


@router.post(
    "/{trip_id}/days/{day_index}/weather/refresh",
    response_model=Envelope[TripWeatherRefreshResponse],
)
async def refresh_trip_day_weather_endpoint(
    trip_id: uuid.UUID,
    day_index: int,
    current_user_id: CurrentUserId,
    db: DbSession,
    kor_travel_map_client: OptionalKorTravelMapHttpClientDep,
    body: TripWeatherRefreshRequest | None = None,
) -> Envelope[TripWeatherRefreshResponse]:
    try:
        await get_trip_access(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
    except TripNotFoundError as exc:
        raise _http_error(status.HTTP_404_NOT_FOUND, exc.code, str(exc)) from exc
    except TripPermissionError as exc:
        raise _http_error(status.HTTP_403_FORBIDDEN, exc.code, str(exc)) from exc

    poi_id = body.poi_id if body is not None else None
    query = select(TripDayPoi).where(
        TripDayPoi.trip_id == trip_id,
        TripDayPoi.day_index == day_index,
        TripDayPoi.deleted_at.is_(None),
    )
    if poi_id is not None:
        query = query.where(TripDayPoi.attachment_id == poi_id)
    pois = list(await db.scalars(query.order_by(TripDayPoi.sort_order)))
    if poi_id is not None and not pois:
        raise _http_error(status.HTTP_404_NOT_FOUND, "POI_NOT_FOUND", "장소를 찾을 수 없습니다.")

    # 날씨는 POI 자신의 feature_id + 저장 좌표만 쓴다(trip view와 같은 대상 판정 — trip_weather_batch).
    coords: dict[str, tuple[float, float]] = {}
    skipped = 0
    for poi in pois:
        coord = _snapshot_coord(poi)
        if poi.feature_id is None or coord is None:
            skipped += 1
            continue
        coords.setdefault(poi.feature_id, coord)
    if len(coords) > MAX_REFRESH_FEATURES:
        coords = dict(list(coords.items())[:MAX_REFRESH_FEATURES])

    map_client = None
    if settings.pinvi_kor_travel_map_weather_enabled:
        if kor_travel_map_client is None or not kor_travel_map_client.has_service_token:
            raise _http_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "WEATHER_SERVICE_UNAVAILABLE",
                "날씨 서비스가 일시적으로 사용 불가합니다.",
            )
        map_client = create_map_weather_client(kor_travel_map_client)

    result = await refresh_weather_locations(db, coords, map_client=map_client)
    return Envelope.of(
        TripWeatherRefreshResponse(
            trip_id=trip_id,
            day_index=day_index,
            refreshed=len(result.refreshed),
            cooldown=len(result.cooldown),
            no_data=len(result.no_data),
            failed=len(result.failed),
            skipped=skipped,
            retry_after_seconds=result.retry_after_seconds,
        )
    )
