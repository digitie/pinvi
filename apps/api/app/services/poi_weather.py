"""여행 장소(POI) 하나의 현재 날씨 + 며칠 예보 + 특보 카드.

`GET /trips/{trip_id}/pois/{poi_id}/weather`의 서비스 계층이다. 장소 목록의 날씨 배지와 날씨 팝업이
쓴다 — trip view의 일자별 날씨(`trip_weather_batch.py`)는 그 **여행 날짜**로 잘린 카드라 "지금 이
장소의 날씨"를 보여줄 수 없다.

`build_feature_weather_card`(`GET /features/{id}/weather`)를 그대로 재사용한다(`asof` 없음 = 관측 +
가까운 3일 예보 + 특보). 차이는 두 가지다.

- 좌표는 POI가 이미 가진 snapshot 좌표(`cache_target_lon/lat` 생성 열 — `coord.{lon,lat}`와 평면
  `lon,lat` 두 shape를 DB가 접는다)를 쓴다. Map feature를 다시 조회하지 않으므로 지도 feature가 없는
  직접 추가 장소(manual/kakao/naver)도 날씨가 나온다.
- 위치 해석 캐시(`weather_location_links`)의 키는 feature가 있으면 `feature_id`, 없으면
  `poi:{poi_id}`다. 캐시는 좌표가 달라지면 다시 해석하므로(`cache_hit`) 키 충돌로 다른 장소의
  날씨가 섞이지 않는다.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map_weather import KorTravelMapWeatherClient
from app.clients.kor_travel_weather import KorTravelWeatherClient
from app.models.poi import TripDayPoi
from app.schemas.feature import FeatureWeatherCard
from app.services.weather_card import build_feature_weather_card


def poi_weather_key(poi: TripDayPoi) -> str:
    """위치 해석 캐시 키 — feature가 있으면 그 id(trip view와 캐시 공유), 없으면 POI 전용 키."""
    return poi.feature_id or f"poi:{poi.attachment_id}"


def poi_coord(poi: TripDayPoi) -> tuple[float, float] | None:
    """`(lat, lon)` — snapshot에 좌표가 없으면 None."""
    if poi.cache_target_lat is None or poi.cache_target_lon is None:
        return None
    return float(poi.cache_target_lat), float(poi.cache_target_lon)


async def build_poi_weather_card(
    db: AsyncSession,
    *,
    poi: TripDayPoi,
    weather_client: KorTravelWeatherClient | None,
    map_weather_client: KorTravelMapWeatherClient | None,
    map_budget_seconds: float,
) -> FeatureWeatherCard:
    """POI 좌표의 현재 날씨·예보·특보 카드. 좌표가 없으면 빈 카드(`metrics=[]`)다."""
    key = poi_weather_key(poi)
    coord = poi_coord(poi)
    if coord is None:
        return FeatureWeatherCard(feature_id=key)
    lat, lon = coord
    return await build_feature_weather_card(
        db,
        feature_id=key,
        lat=lat,
        lon=lon,
        asof=None,
        weather_client=weather_client,
        map_weather_client=map_weather_client,
        map_budget_seconds=map_budget_seconds,
    )
