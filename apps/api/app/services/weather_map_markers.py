"""지도 weather marker — kor-travel-weather 직접 조회 (ADR-068, T-368).

`kor-travel-map`을 전혀 거치지 않는다 — T-363 trip view와 같은 "완전 분리" 원칙을
지도 marker 표면에 적용한다(설계 `docs/integrations/kor-travel-weather.md`
§4.6/§7-3). weather marker는 feature가 아니라 `kor-travel-weather`의 location을
직접 노출한다.

viewport(bbox)는 `kor-travel-weather`의 `/nearby`가 이해하는 center+radius로
변환한다. 전국 스케일(zoom 5)에서는 bbox 대각선이 그 서비스의 반경 상한(500km)을
넘어 한 번의 원형 쿼리로 못 덮으므로, `MIN_WEATHER_MARKER_ZOOM` 미만에서는 아예
조회하지 않는다 — 전국 뷰에서 개별 지점 온도 마커를 보여줄 필요도 없다는 판단이다.

`condition`(맑음/흐림/비/눈)은 provider마다 하늘상태 코드 체계가 달라 안전하게
정규화할 수 없다(`weather_metrics.py`도 `WEATHER_CODE`를 원문 그대로 통과시키고
매핑하지 않는다). 강수량(안전 정규화된 `RN1`/`PCP`)이 있을 때만 rainy/snowy를
판정하고, 신호가 없으면 항상 `cloudy` — "맑음"을 근거 없이 단정하지 않는다.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence

from pydantic import ValidationError

from app.clients.kor_travel_weather import KorTravelWeatherClient, NearbyOut, WeatherValueOut
from app.schemas.feature import BBox, Coord
from app.schemas.weather_map import WeatherCondition, WeatherMapMarker
from app.services.weather_metrics import dedupe_by_provider_priority, normalize_metric

logger = logging.getLogger(__name__)

#: 도시/지역 스케일부터 표시(§ 모듈 docstring). 5~7은 항상 빈 목록.
MIN_WEATHER_MARKER_ZOOM = 8
_EARTH_RADIUS_KM = 6_371.0
_MAX_RADIUS_KM = 500.0  # kor_travel_weather.py `_RADIUS_KM_MAX`와 동일
_TEMP_NORM_KEYS = {"T1H", "TMP"}
_PRECIP_NORM_KEYS = {"RN1", "PCP"}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def bbox_to_center_radius_km(bbox: BBox) -> tuple[float, float, float]:
    """bbox 중심(lat, lon)과 그 중심에서 네 모서리까지 거리 중 최댓값(km)."""

    center_lat = (bbox.lat_min + bbox.lat_max) / 2
    center_lon = (bbox.lng_min + bbox.lng_max) / 2
    corners = (
        (bbox.lat_min, bbox.lng_min),
        (bbox.lat_min, bbox.lng_max),
        (bbox.lat_max, bbox.lng_min),
        (bbox.lat_max, bbox.lng_max),
    )
    radius_km = max(_haversine_km(center_lat, center_lon, lat, lon) for lat, lon in corners)
    return center_lat, center_lon, radius_km


def _pick_temperature(deduped: Sequence[WeatherValueOut]) -> tuple[float, str] | None:
    """안전 정규화된 온도(`T1H`/`TMP`) 중 가장 최근 수신 값을 하나 고릅니다. 없으면 `None`."""

    candidates: list[tuple[WeatherValueOut, float]] = []
    for value in deduped:
        norm_key, number, _unit = normalize_metric(value)
        if norm_key in _TEMP_NORM_KEYS and number is not None:
            candidates.append((value, number))
    if not candidates:
        return None
    best_value, best_number = max(
        candidates, key=lambda pair: pair[0].known_at or pair[0].collected_at
    )
    return best_number, best_value.provider


def _derive_condition(
    deduped: Sequence[WeatherValueOut], *, temperature_c: float | None
) -> WeatherCondition:
    """강수 신호가 있을 때만 rainy/snowy로 판정하고, 없으면 항상 cloudy(§ 모듈 docstring)."""

    for value in deduped:
        norm_key, number, _unit = normalize_metric(value)
        if norm_key in _PRECIP_NORM_KEYS and number is not None and number > 0:
            if temperature_c is not None and temperature_c <= 0:
                return "snowy"
            return "rainy"
    return "cloudy"


def _marker_from_nearby(item: NearbyOut) -> WeatherMapMarker | None:
    """`None`은 "이 location은 마커로 안 만든다"는 두 가지 뜻을 겸한다: 온도를 못
    구했거나(정상 케이스, §모듈 docstring), 좌표가 `Coord`의 한반도 유효 범위를
    벗어난 방어적 케이스(국경 부근 location 등, 비정상이지만 이 한 건 때문에
    나머지 마커까지 500으로 잃으면 안 된다) — 후자는 경고 로그를 남긴다.
    """
    deduped = dedupe_by_provider_priority(item.latest)
    temperature = _pick_temperature(deduped)
    if temperature is None:
        return None
    temperature_c, provider = temperature
    condition = _derive_condition(deduped, temperature_c=temperature_c)
    try:
        return WeatherMapMarker(
            location_id=item.location_id,
            name=item.name,
            coord=Coord(lon=item.longitude, lat=item.latitude),
            temperature_c=temperature_c,
            condition=condition,
            provider=provider,
        )
    except ValidationError:
        logger.warning(
            "weather_map_markers.invalid_marker_skipped",
            extra={"location_id": item.location_id},
        )
        return None


async def build_weather_markers_in_bounds(
    *,
    bbox: BBox,
    zoom: int,
    limit: int,
    weather_client: KorTravelWeatherClient,
) -> list[WeatherMapMarker]:
    """viewport(bbox+zoom) → `kor-travel-weather` `/nearby` 조회 → marker 목록."""

    if zoom < MIN_WEATHER_MARKER_ZOOM:
        return []
    center_lat, center_lon, radius_km = bbox_to_center_radius_km(bbox)
    if radius_km <= 0 or radius_km > _MAX_RADIUS_KM:
        return []
    nearby = await weather_client.nearby(
        lat=center_lat, lon=center_lon, radius_km=radius_km, limit=limit
    )
    markers = [_marker_from_nearby(item) for item in nearby]
    return [marker for marker in markers if marker is not None]
