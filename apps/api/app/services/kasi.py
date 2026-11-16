"""feature snapshot 좌표 추출(해·달 출몰 계산·일자 기준 좌표가 쓴다)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


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
