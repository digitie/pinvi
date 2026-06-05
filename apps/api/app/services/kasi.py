"""KASI 부속 데이터 준비 로직."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from app.models.kasi import TripPoiRiseSet
from app.models.poi import TripDayPoi


def extract_feature_coordinates(snapshot: Mapping[str, Any]) -> tuple[float, float] | None:
    """feature snapshot에서 외부 표면 기준 `(lon, lat)` 좌표를 찾습니다."""

    for lon_key, lat_key in (("lon", "lat"), ("longitude", "latitude")):
        coord = _to_lon_lat(snapshot.get(lon_key), snapshot.get(lat_key))
        if coord is not None:
            return coord

    for key in ("coord", "coordinate", "location"):
        value = snapshot.get(key)
        if isinstance(value, Mapping):
            for lon_key, lat_key in (("lon", "lat"), ("longitude", "latitude")):
                coord = _to_lon_lat(value.get(lon_key), value.get(lat_key))
                if coord is not None:
                    return coord

    return None


def build_initial_poi_rise_set(
    *,
    poi: TripDayPoi,
    locdate: date | None,
    feature_snapshot: Mapping[str, Any],
) -> TripPoiRiseSet:
    """POI 생성 직후 KASI 출몰시각 fetch 상태 row를 만듭니다."""

    coord = extract_feature_coordinates(feature_snapshot)
    if locdate is None:
        status = "pending_date"
        longitude = None
        latitude = None
    elif coord is None:
        status = "pending_coord"
        longitude = None
        latitude = None
    else:
        status = "pending_fetch"
        longitude, latitude = coord

    return TripPoiRiseSet(
        poi_id=poi.attachment_id,
        locdate=locdate,
        longitude=longitude,
        latitude=latitude,
        status=status,
    )


def _to_lon_lat(lon: object, lat: object) -> tuple[float, float] | None:
    if lon is None or lat is None:
        return None
    lon_value = _coerce_float(lon)
    lat_value = _coerce_float(lat)
    if lon_value is None or lat_value is None:
        return None
    if not (-180 <= lon_value <= 180 and -90 <= lat_value <= 90):
        return None
    return lon_value, lat_value


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        return float(value)
    except ValueError:
        return None
