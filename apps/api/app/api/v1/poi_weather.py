"""`GET /trips/{trip_id}/pois/{poi_id}/weather` — 장소 하나의 현재 날씨·예보·특보.

장소 목록의 날씨 배지(아이콘 + 현재 기온 + 오늘 최고/최저)와 날씨 팝업(시간별·일별 예보, 특보)이
쓴다. 여행 멤버(읽기 권한 포함)면 볼 수 있다. 소스 선택(Map 경로/kor-travel-weather 직접 경로)과
503 정책은 `GET /features/{id}/weather`와 같다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.clients.kor_travel_map import OptionalKorTravelMapHttpClientDep
from app.clients.kor_travel_map_weather import create_map_weather_client
from app.clients.kor_travel_weather import OptionalKorTravelWeatherClientDep
from app.core.config import settings
from app.core.deps import CurrentUserId, DbSession
from app.schemas.envelope import Envelope
from app.schemas.feature import FeatureWeatherCard
from app.services.poi import PoiNotFoundError, get_poi
from app.services.poi_weather import build_poi_weather_card
from app.services.trip import TripNotFoundError, TripPermissionError, get_trip_access

router = APIRouter(prefix="/trips/{trip_id}/pois", tags=["pois"])


@router.get("/{poi_id}/weather", response_model=Envelope[FeatureWeatherCard])
async def get_poi_weather(
    trip_id: uuid.UUID,
    poi_id: uuid.UUID,
    current_user_id: CurrentUserId,
    db: DbSession,
    map_client: OptionalKorTravelMapHttpClientDep,
    weather_client: OptionalKorTravelWeatherClientDep,
) -> Envelope[FeatureWeatherCard]:
    try:
        await get_trip_access(db, trip_id=trip_id, user_id=uuid.UUID(current_user_id))
        poi = await get_poi(db, attachment_id=poi_id, trip_id=trip_id)
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
    card = await build_poi_weather_card(
        db,
        poi=poi,
        weather_client=weather_client,
        map_weather_client=map_weather_client,
        map_budget_seconds=settings.pinvi_kor_travel_map_weather_request_budget_seconds,
    )
    return Envelope.of(card)
