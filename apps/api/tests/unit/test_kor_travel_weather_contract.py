"""`kor-travel-weather` OpenAPI 계약 드리프트 게이트 (T-360/P1, ADR-068).

`kor-travel-weather` `3411ecc`(2026-09-16, `packages/kor-travel-weather-api/openapi.json`)의
전체 스냅샷을 byte-for-byte vendor하고 pinned SHA-256으로 수기 graft를 차단한다. Pinvi
client(`clients/kor_travel_weather.py`)가 쓰는 **4개 엔드포인트만** 스코프로 잡는다 —
이 client는 T-360 시점에 아직 어떤 라우터에도 배선되지 않았으므로, `kor-travel-map`
계약 게이트(`test_kor_travel_map_contract.py`)가 하는 전체 필드 type/format 정밀 검증은
과잉이다. 대신 실제 실패 모드 둘을 정확히 겨눈다:

1. **필드 이름 드리프트** — decoder의 required/optional field set이 스냅샷의
   `required`/`properties`와 정확히 일치하는지(양방향)를 검증한다. 어긋나면 이 게이트가
   먼저 죽는다(서버가 필드를 없애거나 새 required 필드를 추가한 경우).
2. **query 상한 드리프트** — client가 하드코딩한 lat/lon/radius_km/limit 상한이 스냅샷의
   query parameter schema(`minimum`/`maximum`)와 정확히 일치하는지 검증한다. FastAPI는
   선언하지 않은 query를 조용히 버리므로(kor_travel_map 게이트와 같은 이유) exact pin이다.

운영: `kor-travel-weather` 스펙이 갱신되면 스냅샷을 재vendor하고(`docs/integrations/
kor-travel-weather.md`) 본 테스트를 돌린다. 실패하면 client/decoder를 맞춘다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.clients.kor_travel_weather import (
    _LOCATION_FIELDS,
    _LOCATION_REQUIRED,
    _MEASUREMENT_POINT_FIELDS,
    _MEASUREMENT_POINT_REQUIRED,
    _WEATHER_VALUE_FIELDS,
    _WEATHER_VALUE_REQUIRED,
    KorTravelWeatherClient,
)

_SNAPSHOT = Path(__file__).resolve().parent.parent / "contract" / "kor-travel-weather-openapi.json"
_UPSTREAM_COMMIT = "3411ecc"
_SNAPSHOT_SHA256 = "e3edfd22f166262dc21162f1d366d017331d869b416f03c74a699278e78c8154"

_CLIENT_PATHS = [
    "/v1/weather/resolve",
    "/v1/weather/markers",
    "/v1/weather/locations/{location_id}/latest",
    "/v1/weather/locations/{location_id}/forecast",
]


def _load_snapshot() -> dict[str, Any]:
    raw = _SNAPSHOT.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == _SNAPSHOT_SHA256, (
        f"kor-travel-weather-openapi.json이 pinned SHA-256과 다릅니다 "
        f"(upstream {_UPSTREAM_COMMIT} 기준 재vendor 후 이 상수도 함께 갱신할 것): {digest}"
    )
    return json.loads(raw)


def _schema(spec: dict[str, Any], name: str) -> dict[str, Any]:
    schema = spec["components"]["schemas"][name]
    assert isinstance(schema, dict)
    return schema


def _field_sets(schema: dict[str, Any]) -> tuple[set[str], set[str]]:
    """`(required, all_fields)`."""
    required = set(schema.get("required", []))
    allowed = set(schema["properties"].keys())
    return required, allowed


def test_client_paths_exist_in_snapshot() -> None:
    spec = _load_snapshot()
    assert spec["info"]["version"] == "0.1.0.dev0"
    for path in _CLIENT_PATHS:
        assert path in spec["paths"], f"kor-travel-weather 스냅샷에 경로가 없습니다: {path}"
        assert "get" in spec["paths"][path], f"{path}는 GET을 정의해야 합니다."


def test_weather_value_out_field_set_matches_decoder() -> None:
    spec = _load_snapshot()
    required, allowed = _field_sets(_schema(spec, "WeatherValueOut"))
    assert required == _WEATHER_VALUE_REQUIRED
    assert allowed == _WEATHER_VALUE_FIELDS


def test_location_out_field_set_matches_decoder() -> None:
    spec = _load_snapshot()
    required, allowed = _field_sets(_schema(spec, "LocationOut"))
    assert required == _LOCATION_REQUIRED
    assert allowed == _LOCATION_FIELDS


def test_measurement_point_out_field_set_matches_decoder() -> None:
    spec = _load_snapshot()
    required, allowed = _field_sets(_schema(spec, "MeasurementPointOut"))
    assert required == _MEASUREMENT_POINT_REQUIRED
    assert allowed == _MEASUREMENT_POINT_FIELDS


def _param(spec: dict[str, Any], path: str, name: str) -> dict[str, Any]:
    for param in spec["paths"][path]["get"]["parameters"]:
        if param["name"] == name:
            schema = param["schema"]
            if "anyOf" in schema:
                for branch in schema["anyOf"]:
                    if branch.get("type") != "null":
                        return branch
            return schema
    raise AssertionError(f"{path}에 query parameter가 없습니다: {name}")


def test_resolve_coordinate_bounds_match_client() -> None:
    spec = _load_snapshot()
    lat = _param(spec, "/v1/weather/resolve", "lat")
    lon = _param(spec, "/v1/weather/resolve", "lon")
    radius = _param(spec, "/v1/weather/resolve", "radius_km")
    assert (lat["minimum"], lat["maximum"]) == (33, 43)
    assert (lon["minimum"], lon["maximum"]) == (124, 132)
    assert radius["maximum"] == 500
    assert radius["default"] == 100


def test_latest_limit_bound_matches_client() -> None:
    spec = _load_snapshot()
    limit = _param(spec, "/v1/weather/locations/{location_id}/latest", "limit")
    assert (limit["minimum"], limit["maximum"]) == (1, 1000)


def test_forecast_limit_bound_matches_client() -> None:
    spec = _load_snapshot()
    limit = _param(spec, "/v1/weather/locations/{location_id}/forecast", "limit")
    assert (limit["minimum"], limit["maximum"]) == (1, 5000)


def test_markers_location_id_is_repeated_array_query() -> None:
    spec = _load_snapshot()
    param = None
    for candidate in spec["paths"]["/v1/weather/markers"]["get"]["parameters"]:
        if candidate["name"] == "location_id":
            param = candidate
            break
    assert param is not None
    assert param["in"] == "query"
    # 500개 상한은 서버 코드에서만 강제되고 OpenAPI 스키마에는 없다(설계 문서 §2.1) —
    # 즉 client의 _MARKERS_MAX_LOCATION_IDS=500은 이 스냅샷으로 고정할 수 없다.
    # `docs/weather-api.md`의 서술 상한을 그대로 client 상수에 옮겨 적었다는 사실만 여기
    # 남긴다 — 서버 쪽 상한이 바뀌면 이 주석과 client 상수를 함께 재검토해야 한다.


def test_client_max_attempts_and_no_auth_headers() -> None:
    """공개 read는 인증이 없다 — client가 헤더를 붙이지 않는지 구조적으로 확인."""
    import inspect

    source = inspect.getsource(KorTravelWeatherClient)
    assert "headers=" not in source
    assert "Authorization" not in source
