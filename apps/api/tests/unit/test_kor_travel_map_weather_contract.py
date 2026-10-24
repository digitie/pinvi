"""Map weather 상태 표면 계약 게이트 (ADR-077, Map ADR-114 W7).

vendored service OpenAPI(`contract/kor-travel-map-openapi-service.json` — byte 핀은
`test_kor_travel_map_cache_target_contract.py` 소유)의 `/v1/service/weather/*`와 PinVi 쪽을 대조한다.
transport 게이트(`test_kor_travel_map_transport_contract.py`)와 같은 세 축이다.

1. **query·본문** — client가 MockTransport로 실제로 보낸 query 이름이 각 경로 선언에 있고, 선언 집합 자체를 exact로
   핀한다(FastAPI는 모르는 query를 조용히 버린다). 배치 본문 키는 `WeatherBatchRequest` properties 안에 있다.
   PinVi가 쓰는 상한(배치 50·반경 100 km·목록 500)도 맞춘다.
2. **필드** — PinVi 해석 모델(`app/services/weather_map_state.py`)이 읽는 필드가 Map schema properties에 있고, 모델에서
   필수인 필드는 Map에서도 required이며, Map이 보낼 수 있는 JSON 타입(null 포함)을 PinVi가 받는다. 부분 `status`·관측
   style·요약 구간·예보 style 키는 exact로 핀한다(새 값이 조용히 접히지 않게).
3. **fixture** — `tests/weather_map_fixtures.py`의 대표 본문이 vendored schema에 맞는다.
"""

from __future__ import annotations

import inspect
import json
import re
import typing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.api.v1.weather_markers import _MAX_LIMIT as MARKERS_MAX_LIMIT
from app.clients import kor_travel_map_weather
from app.clients.kor_travel_map import KorTravelMapClient
from app.clients.kor_travel_map_weather import (
    MAX_BATCH_IDS,
    MAX_LIST_LIMIT,
    MAX_RADIUS_M,
    KorTravelMapWeatherClient,
)
from app.services import weather_map_state as st
from app.services.weather_location_resolver import _RESOLVE_RADII_KM
from tests import weather_map_fixtures as fx
from tests.openapi_subset import json_types, schema_errors

_SNAPSHOT = (
    Path(__file__).resolve().parent.parent / "contract" / "kor-travel-map-openapi-service.json"
)
_PREFIX = "/v1/service/weather"


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return json.loads(_SNAPSHOT.read_bytes())


_BUNDLE_QUERY = {"sections", "forecast_styles", "from", "to"}
_EXPECTED: dict[tuple[str, str], set[str]] = {
    ("get", f"{_PREFIX}/locations"): {
        "include_current",
        "cursor",
        "limit",
        "lon",
        "lat",
        "radius_m",
        "min_lon",
        "min_lat",
        "max_lon",
        "max_lat",
    },
    ("get", f"{_PREFIX}/locations/{{feature_id}}"): _BUNDLE_QUERY,
    ("get", f"{_PREFIX}/nearest"): {"lon", "lat", "radius_m", *_BUNDLE_QUERY},
    ("post", f"{_PREFIX}/locations/batch"): set(),
    ("get", f"{_PREFIX}/status"): set(),
}


def _query_names(spec: dict[str, Any], method: str, path: str) -> set[str]:
    op = spec["paths"][path][method]
    return {p["name"] for p in op.get("parameters", []) if p["in"] == "query"}


async def _sent() -> tuple[dict[tuple[str, str], set[str]], list[dict[str, Any]]]:
    """client를 MockTransport로 실제 호출해 **나간** query 키(경로별)와 배치 본문을 모은다."""
    queries: dict[tuple[str, str], set[str]] = {}
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith(f"{_PREFIX}/locations/") and not path.endswith("/batch"):
            path = f"{_PREFIX}/locations/{{feature_id}}"
        queries.setdefault((request.method.lower(), path), set()).update(request.url.params.keys())
        if request.method == "POST":
            bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"data": {}, "meta": {"duration_ms": 0}})

    client = KorTravelMapWeatherClient(
        KorTravelMapClient(
            httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler)),
            service_token="t",
            max_attempts=1,
        )
    )
    now = datetime.now(UTC)
    window = {"from_": now, "to": now + timedelta(days=1)}
    styles = ("short", "external")
    await client.list_locations(bbox=(126.0, 37.0, 127.0, 38.0), include_current=True, limit=10)
    await client.list_locations(near=(126.5, 37.5, 1000.0), limit=10)
    await client.list_locations(cursor="c", limit=10)
    await client.location(fx.FID_KMA, sections=("current",), forecast_styles=styles, **window)
    await client.nearest(
        lon=126.9,
        lat=37.5,
        radius_m=20_000.0,
        sections=("forecasts",),
        forecast_styles=styles,
        **window,
    )
    await client.batch(
        feature_ids=[fx.FID_KMA],
        location_ids=[fx.LOC_KMA],
        sections=("current", "forecasts", "daily_summaries"),
        forecast_styles=styles,
        forecast_from=now,
        forecast_to=now + timedelta(days=1),
    )
    return queries, bodies


async def test_weather_query_parameters_are_pinned(spec: dict[str, Any]) -> None:
    declared = {
        (method, path)
        for path, item in spec["paths"].items()
        if path.startswith(_PREFIX)
        for method in item
    }
    assert declared == set(_EXPECTED), "Map weather 경로 집합이 바뀌었다"
    for (method, path), expected in _EXPECTED.items():
        assert _query_names(spec, method, path) == expected, (method, path)
    queries, _bodies = await _sent()
    assert queries, "client가 아무 요청도 보내지 않았다"
    for (method, path), keys in queries.items():
        assert keys <= _query_names(spec, method, path), (method, path, keys)


async def test_batch_body_keys_are_declared(spec: dict[str, Any]) -> None:
    _queries, bodies = await _sent()
    assert bodies, "배치 본문이 없다"
    request_schema = spec["components"]["schemas"]["WeatherBatchRequest"]
    for body in bodies:
        assert set(body) <= set(request_schema["properties"]), body
        assert schema_errors(spec, request_schema, body, "$") == []


def test_client_module_requests_only_vendored_weather_paths(spec: dict[str, Any]) -> None:
    """client 소스의 경로 리터럴 ⊆ vendored weather 경로. `/status`(운영 진단)만 PinVi가 부르지 않는다."""
    source = Path(inspect.getsourcefile(kor_travel_map_weather) or "").read_text(encoding="utf-8")
    requested = set(re.findall(r'"(/v1/[^"]*)"', source))
    weather_paths = {p for p in spec["paths"] if p.startswith(_PREFIX)}
    assert requested <= weather_paths
    assert weather_paths - requested == {f"{_PREFIX}/status"}


def test_pinvi_limits_match_map_caps(spec: dict[str, Any]) -> None:
    schemas = spec["components"]["schemas"]
    batch = schemas["WeatherBatchRequest"]["properties"]
    assert batch["feature_ids"]["maxItems"] == MAX_BATCH_IDS
    assert batch["location_ids"]["maxItems"] == MAX_BATCH_IDS
    nearest = spec["paths"][f"{_PREFIX}/nearest"]["get"]["parameters"]
    radius = next(p for p in nearest if p["name"] == "radius_m")["schema"]
    assert radius["maximum"] == MAX_RADIUS_M
    # 해석기의 반경 확대 상한이 Map 상한을 넘지 않는다(넘으면 마지막 시도가 422).
    assert max(_RESOLVE_RADII_KM) * 1000.0 <= MAX_RADIUS_M
    listing = spec["paths"][f"{_PREFIX}/locations"]["get"]["parameters"]
    limit = next(p for p in listing if p["name"] == "limit")["schema"]
    assert limit["maximum"] == MAX_LIST_LIMIT
    assert MARKERS_MAX_LIMIT <= MAX_LIST_LIMIT


def _enum(schema: dict[str, Any]) -> list[Any]:
    if "enum" in schema:
        return list(schema["enum"])
    [values] = [branch["enum"] for branch in schema.get("anyOf", []) if "enum" in branch]
    return list(values)


def test_closed_vocabularies_are_pinned(spec: dict[str, Any]) -> None:
    schemas = spec["components"]["schemas"]
    for section in ("WeatherCurrentSection", "WeatherForecastSection", "WeatherDailySection"):
        assert set(_enum(schemas[section]["properties"]["status"])) == set(
            typing.get_args(st.SectionStatus)
        )
    observation_styles = typing.get_args(
        st.MapWeatherObservation.model_fields["forecast_style"].annotation
    )
    assert set(_enum(schemas["WeatherObservationState"]["properties"]["forecast_style"])) == set(
        observation_styles
    )
    slots = typing.get_args(st.MapWeatherDailySlot.model_fields["slot"].annotation)
    assert set(_enum(schemas["WeatherDailySlotOut"]["properties"]["slot"])) == set(slots)
    assert set(slots) == set(st.DAILY_SLOT_HOURS)
    assert set(schemas["WeatherForecastSections"]["properties"]) == set(
        st.MapWeatherForecastSections.model_fields
    )
    styles = _enum(
        schemas["WeatherBatchRequest"]["properties"]["forecast_styles"]["anyOf"][0]["items"]
    )
    assert set(styles) == set(typing.get_args(kor_travel_map_weather.WeatherForecastStyle))
    sections = _enum(schemas["WeatherBatchRequest"]["properties"]["sections"]["anyOf"][0]["items"])
    assert set(sections) == set(typing.get_args(kor_travel_map_weather.WeatherSection))


_MODEL_SCHEMAS: list[tuple[type[BaseModel], str]] = [
    (st.MapWeatherFreshness, "WeatherStateFreshness"),
    (st.MapWeatherSource, "WeatherSectionSource"),
    (st.MapWeatherCoord, "StateCoordinate"),
    (st.MapWeatherObservation, "WeatherObservationState"),
    (st.MapWeatherLocation, "WeatherLocationOut"),
    (st.MapWeatherForecastGroup, "WeatherForecastGroupState"),
    (st.MapWeatherSlotDelta, "WeatherSlotDelta"),
    (st.MapWeatherDailySlot, "WeatherDailySlotOut"),
    (st.MapWeatherCurrentSection, "WeatherCurrentSection"),
    (st.MapWeatherForecastSection, "WeatherForecastSection"),
    (st.MapWeatherForecastSections, "WeatherForecastSections"),
    (st.MapWeatherDailySection, "WeatherDailySection"),
    (st.MapWeatherBundle, "WeatherBundleData"),
    (st.MapWeatherBatchMissing, "WeatherBatchMissing"),
    (st.MapWeatherBatch, "WeatherBatchData"),
    (st.MapWeatherLocationList, "WeatherLocationListData"),
]


@pytest.mark.parametrize(("model", "schema_name"), _MODEL_SCHEMAS)
def test_consumed_fields_exist_and_required_matches(
    spec: dict[str, Any], model: type[BaseModel], schema_name: str
) -> None:
    schema = spec["components"]["schemas"][schema_name]
    properties = schema["properties"]
    required = set(schema.get("required", []))
    ours_schema = model.model_json_schema()
    for name, field in model.model_fields.items():
        assert name in properties, f"{schema_name}에 {name}이 없다"
        if field.is_required():
            assert name in required, f"{schema_name}.{name}은 Map에서 required가 아니다"
        ours = json_types(ours_schema, ours_schema["properties"][name])
        theirs = json_types(spec, properties[name])
        assert theirs <= ours, f"{schema_name}.{name}: Map {theirs} ⊄ PinVi {ours}"


def test_validator_rejects_a_broken_fixture(spec: dict[str, Any]) -> None:
    """검증기가 실제로 잡는지 — 항진명제 게이트 방지."""
    broken = fx.bundle_body(fx.kma_bundle())
    del broken["data"]["current"]["observations"]
    broken["data"]["forecasts"]["short"]["groups"][0]["metrics"]["TMP"][0] = True
    broken["data"]["location"]["unexpected"] = 1
    errors = schema_errors(
        spec, {"$ref": "#/components/schemas/WeatherBundleResponse"}, broken, "$"
    )
    assert any("observations: required 누락" in e for e in errors)
    assert any("unexpected: 선언되지 않은 필드" in e for e in errors)
    assert any("metrics.TMP" in e for e in errors)


@pytest.mark.parametrize(("name", "body"), sorted(fx.all_fixtures().items()))
def test_fixture_matches_vendored_schema(spec: dict[str, Any], name: str, body: Any) -> None:
    schema_name = fx.RESPONSE_SCHEMAS[name]
    errors = schema_errors(spec, {"$ref": f"#/components/schemas/{schema_name}"}, body, "$")
    assert errors == [], errors


def test_every_fixture_has_a_schema() -> None:
    assert set(fx.all_fixtures()) == set(fx.RESPONSE_SCHEMAS)


@pytest.mark.parametrize(
    ("name", "parse"),
    [
        ("bundle_kma", st.parse_bundle),
        ("bundle_nearest_split", st.parse_bundle),
        ("bundle_current_only", st.parse_bundle),
        ("batch", st.parse_batch),
        ("list_with_current", st.parse_location_list),
        ("list_without_current", st.parse_location_list),
    ],
)
def test_pinvi_models_parse_every_fixture(name: str, parse: Any) -> None:
    """schema에 맞는 fixture를 PinVi 해석 모델이 받는다(양쪽이 같은 본문을 본다)."""
    parse(fx.all_fixtures()[name]["data"])
