"""`/weather/markers-in-bounds` — 지도 weather marker, kor-travel-weather 직접 조회.

ADR-068, T-368. `kor-travel-map`을 전혀 거치지 않는다 — T-363 trip view가 확립한
"완전 분리" 원칙을 지도 marker 표면에 적용한다. 설계 정본은
`docs/integrations/kor-travel-weather.md` §4.6/§7-3.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.clients.kor_travel_weather import KorTravelWeatherError, OptionalKorTravelWeatherClientDep
from app.core.bbox import MAX_ZOOM, MIN_ZOOM, parse_bbox
from app.core.config import settings
from app.core.deps import CurrentUserId
from app.schemas.envelope import Envelope
from app.schemas.weather_map import WeatherMarkersInBoundsResponse
from app.services.weather_map_markers import build_weather_markers_in_bounds

router = APIRouter(prefix="/weather", tags=["weather"])

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 100


@router.get(
    "/markers-in-bounds",
    response_model=Envelope[WeatherMarkersInBoundsResponse],
)
async def weather_markers_in_bounds(
    _current_user: CurrentUserId,
    weather_client: OptionalKorTravelWeatherClientDep,
    bbox: Annotated[str, Query(description="lng_min,lat_min,lng_max,lat_max")],
    zoom: Annotated[int, Query(ge=MIN_ZOOM, le=MAX_ZOOM)],
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
) -> Envelope[WeatherMarkersInBoundsResponse]:
    """viewport 내 weather marker(위치+현재 온도) 목록.

    `pinvi_kor_travel_weather_map_markers_enabled`가 꺼져 있으면 (기본값) 빈 목록을
    돌려준다 — 지금 운영 중인 `/features/in-bounds`가 `weather` kind를 기본에서
    제외해 마커가 애초에 하나도 안 보이는 것과 관측상 동일하다. 새 기능이 검증돼
    켜지기 전까지는 사용자 경험 변화가 없다.
    """
    bbox_obj = parse_bbox(bbox)
    if not settings.pinvi_kor_travel_weather_map_markers_enabled:
        return Envelope.of(WeatherMarkersInBoundsResponse(items=[], zoom=zoom, bbox=bbox_obj))
    if weather_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "WEATHER_SERVICE_UNAVAILABLE",
                "message": "날씨 서비스가 일시적으로 사용 불가합니다.",
            },
        )
    try:
        items = await build_weather_markers_in_bounds(
            bbox=bbox_obj, zoom=zoom, limit=limit, weather_client=weather_client
        )
    except KorTravelWeatherError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "WEATHER_SERVICE_UNAVAILABLE",
                "message": "날씨 서비스가 일시적으로 사용 불가합니다.",
            },
        ) from exc
    return Envelope.of(WeatherMarkersInBoundsResponse(items=items, zoom=zoom, bbox=bbox_obj))
