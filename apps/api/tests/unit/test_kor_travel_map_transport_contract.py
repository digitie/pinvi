"""Map transport 상태 표면 계약 게이트 (ADR-076 D3).

vendored service OpenAPI(`contract/kor-travel-map-openapi-service.json` — byte 핀은
`test_kor_travel_map_cache_target_contract.py` 소유)의 `/v1/service/transport/*`와 PinVi 쪽을 대조한다.

1. **query** — client가 보내는 query 이름이 각 경로 선언에 있고, 선언 집합 자체를 exact로 핀한다(FastAPI는
   모르는 query를 조용히 버린다 — 기존 Map 게이트와 같은 이유). PinVi가 쓰는 `limit`·`radius_m` 상한도 맞춘다.
2. **필드** — PinVi 해석 모델(`app/schemas/transport.py`)이 읽는 필드가 Map schema properties에 있고, 모델에서
   필수인 필드는 Map에서도 required다.
3. **fixture** — 테스트 fixture(`tests/transport_map_fixtures.py`)가 vendored schema에 맞는다. 저장소에
   `jsonschema`가 없어 fixture가 쓰는 구성만 다루는 작은 검증기를 둔다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from app.api.v1.transport import _MAX_LIMIT
from app.schemas.transport import (
    AirportItem,
    FuelPrice,
    FuelPriceHistoryPoint,
    FuelStationItem,
    HighwayIncidentItem,
    RestAreaFuelPrices,
    RestAreaItem,
    TransportAddress,
    TransportCoord,
    TransportFreshness,
)
from app.services.transport_layers import LAYER_DATASET_PATH, LAYER_MAP_DATASET
from tests import transport_map_fixtures as fx

_SNAPSHOT = (
    Path(__file__).resolve().parent.parent / "contract" / "kor-travel-map-openapi-service.json"
)


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return json.loads(_SNAPSHOT.read_bytes())


_LIST_QUERY = {
    "cursor",
    "limit",
    "lon",
    "lat",
    "radius_m",
    "min_lon",
    "min_lat",
    "max_lon",
    "max_lat",
}
_EXPECTED_QUERY: dict[str, set[str]] = {
    **{f"/v1/service/transport/{d}": _LIST_QUERY for d in LAYER_DATASET_PATH.values()},
    **{f"/v1/service/transport/{d}/{{feature_id}}": set() for d in LAYER_DATASET_PATH.values()},
    "/v1/service/transport/fuel-stations/{feature_id}/price-history": {
        "product_code",
        "since",
        "until",
        "limit",
    },
    "/v1/service/transport/status": set(),
}
#: client가 실제로 보내는 query(선언의 부분집합이어야 한다).
_CLIENT_SENDS: dict[str, set[str]] = {
    "list": {
        "min_lon",
        "min_lat",
        "max_lon",
        "max_lat",
        "lon",
        "lat",
        "radius_m",
        "limit",
        "cursor",
    },
    "history": {"since", "limit"},
}


def _query_names(spec: dict[str, Any], path: str) -> set[str]:
    op = spec["paths"][path]["get"]
    return {p["name"] for p in op.get("parameters", []) if p["in"] == "query"}


def test_transport_query_parameters_are_pinned(spec: dict[str, Any]) -> None:
    transport_paths = {p for p in spec["paths"] if p.startswith("/v1/service/transport")}
    assert transport_paths == set(_EXPECTED_QUERY), "Map transport 경로 집합이 바뀌었다"
    for path, expected in _EXPECTED_QUERY.items():
        assert _query_names(spec, path) == expected, path
    for dataset in LAYER_DATASET_PATH.values():
        assert _CLIENT_SENDS["list"] <= _query_names(spec, f"/v1/service/transport/{dataset}")
    assert _CLIENT_SENDS["history"] <= _query_names(
        spec, "/v1/service/transport/fuel-stations/{feature_id}/price-history"
    )


def test_pinvi_limit_matches_map_cap(spec: dict[str, Any]) -> None:
    for dataset in LAYER_DATASET_PATH.values():
        params = spec["paths"][f"/v1/service/transport/{dataset}"]["get"]["parameters"]
        limit = next(p for p in params if p["name"] == "limit")
        assert limit["schema"]["maximum"] == _MAX_LIMIT


def test_status_dataset_names_match_map_router() -> None:
    # Map `/status`는 TRANSPORT_STATE_DATASETS 순서로 이름을 싣는다 — fixture가 그 이름을 쓴다.
    names = {d["dataset"] for d in fx.status_body()["data"]["datasets"]}
    assert set(LAYER_MAP_DATASET.values()) <= names


_MODEL_SCHEMAS: list[tuple[type[BaseModel], str, set[str]]] = [
    # (PinVi 모델, Map schema, PinVi가 붙이는 필드)
    (FuelStationItem, "FuelStationOut", {"layer"}),
    (RestAreaItem, "RestAreaOut", {"layer"}),
    (HighwayIncidentItem, "HighwayIncidentOut", {"layer"}),
    (AirportItem, "AirportOut", {"layer"}),
    (TransportCoord, "StateCoordinate", set()),
    (TransportAddress, "StateAddress", set()),
    (TransportFreshness, "TransportFreshness", set()),
    (FuelPrice, "FuelPriceState", set()),
    (RestAreaFuelPrices, "RestAreaFuelPriceState", set()),
    (FuelPriceHistoryPoint, "PriceHistoryPoint", set()),
]


@pytest.mark.parametrize(("model", "schema_name", "local"), _MODEL_SCHEMAS)
def test_consumed_fields_exist_and_required_matches(
    spec: dict[str, Any], model: type[BaseModel], schema_name: str, local: set[str]
) -> None:
    schema = spec["components"]["schemas"][schema_name]
    properties = set(schema["properties"])
    required = set(schema.get("required", []))
    for name, field in model.model_fields.items():
        if name in local:
            continue
        assert name in properties, f"{schema_name}에 {name}이 없다"
        if field.is_required():
            assert name in required, f"{schema_name}.{name}은 Map에서 required가 아니다"


# ── fixture 검증기 ──────────────────────────────────────────────────────────

_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
    "null": (type(None),),
}


def _errors(spec: dict[str, Any], schema: dict[str, Any], value: Any, at: str) -> list[str]:
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        return _errors(spec, spec["components"]["schemas"][name], value, at)
    if "anyOf" in schema:
        branches = [_errors(spec, branch, value, at) for branch in schema["anyOf"]]
        return [] if any(not b for b in branches) else [f"{at}: anyOf 불일치 {branches}"]
    if "const" in schema and value != schema["const"]:
        return [f"{at}: const {schema['const']!r} ≠ {value!r}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{at}: enum 밖 {value!r}"]
    kind = schema.get("type")
    if kind is not None:
        allowed = _TYPES[kind]
        if isinstance(value, bool) and kind in ("integer", "number"):
            return [f"{at}: bool은 {kind}가 아니다"]
        if not isinstance(value, allowed):
            return [f"{at}: {kind} 아님 ({type(value).__name__})"]
    out: list[str] = []
    if isinstance(value, dict) and (kind == "object" or "properties" in schema):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                out.append(f"{at}.{name}: required 누락")
        for name, item in value.items():
            if name in properties:
                out += _errors(spec, properties[name], item, f"{at}.{name}")
            elif schema.get("additionalProperties") is False:
                out.append(f"{at}.{name}: 선언되지 않은 필드")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            out += _errors(spec, schema["items"], item, f"{at}[{index}]")
    return out


def test_validator_rejects_a_broken_fixture(spec: dict[str, Any]) -> None:
    """검증기가 실제로 잡는지 — 항진명제 게이트 방지."""
    broken = fx.list_body("fuel-stations")
    del broken["data"]["items"][0]["prices"]
    broken["data"]["items"][0]["unexpected"] = 1
    errors = _errors(spec, {"$ref": "#/components/schemas/FuelStationListResponse"}, broken, "$")
    assert any("prices: required 누락" in e for e in errors)
    assert any("unexpected: 선언되지 않은 필드" in e for e in errors)


@pytest.mark.parametrize(("name", "body"), sorted(fx.all_fixtures().items()))
def test_fixture_matches_vendored_schema(spec: dict[str, Any], name: str, body: Any) -> None:
    schema_name = fx.RESPONSE_SCHEMAS[name]
    errors = _errors(spec, {"$ref": f"#/components/schemas/{schema_name}"}, body, "$")
    assert errors == [], errors


def test_every_fixture_has_a_schema() -> None:
    assert set(fx.all_fixtures()) == set(fx.RESPONSE_SCHEMAS)
