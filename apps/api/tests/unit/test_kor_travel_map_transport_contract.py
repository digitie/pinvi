"""Map transport 상태 표면 계약 게이트 (ADR-076 D3).

vendored service OpenAPI(`contract/kor-travel-map-openapi-service.json` — byte 핀은
`test_kor_travel_map_cache_target_contract.py` 소유)의 `/v1/service/transport/*`와 PinVi 쪽을 대조한다.

1. **query** — client가 MockTransport로 실제로 보낸 query 이름이 각 경로 선언에 있고, 선언 집합 자체를 exact로 핀한다(FastAPI는
   모르는 query를 조용히 버린다 — 기존 Map 게이트와 같은 이유). PinVi가 쓰는 `limit`·`radius_m` 상한도 맞춘다.
2. **필드** — PinVi 해석 모델(`app/schemas/transport.py`)이 읽는 필드가 Map schema properties에 있고, 모델에서
   필수인 필드는 Map에서도 required이며, Map이 보낼 수 있는 JSON 타입(null 포함)을 PinVi가 받는다.
3. **fixture** — 테스트 fixture(`tests/transport_map_fixtures.py`)가 vendored schema에 맞는다. 저장소에
   `jsonschema`가 없어 fixture가 쓰는 구성만 다루는 작은 검증기를 둔다.
"""

from __future__ import annotations

import inspect
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.api.v1.transport import _MAX_LIMIT
from app.clients import kor_travel_map_transport
from app.clients.kor_travel_map import KorTravelMapClient
from app.clients.kor_travel_map_transport import KorTravelMapTransportClient
from app.core.time import KST
from app.schemas.transport import (
    PRICE_HISTORY_REASONS,
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
from app.services.transport_layers import LAYER_DATASET_PATH, LAYER_MAP_DATASET, PRODUCT_CODE_BY_KEY
from tests import transport_map_fixtures as fx
from tests.openapi_subset import json_types as _json_types
from tests.openapi_subset import schema_errors as _errors

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
        "cursor",  # Map ADR-114 D6 T4 — PinVi는 보내지 않는다(첫 페이지만 읽는다)
    },
    "/v1/service/transport/status": set(),
}


async def _sent_queries() -> dict[str, set[str]]:
    """client를 MockTransport로 실제 호출해 **나간** query 키를 경로별로 모은다(손으로 적은 표가 아니다)."""
    sent: dict[str, set[str]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.setdefault(request.url.path, set()).update(request.url.params.keys())
        return httpx.Response(200, json={"data": {}, "meta": {"duration_ms": 0}})

    client = KorTravelMapTransportClient(
        KorTravelMapClient(
            httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler)),
            service_token="t",
            max_attempts=1,
        )
    )
    for dataset in LAYER_DATASET_PATH.values():
        await client.list_items(dataset, bbox=(126.0, 37.0, 127.0, 38.0), limit=10)
        await client.list_items(dataset, near=(126.5, 37.5, 1000.0), limit=10)
        await client.list_items(dataset, cursor="c", limit=10)
    await client.fuel_price_history(
        "f1", product_code="B027", since=datetime(2026, 10, 1, tzinfo=KST), limit=5
    )
    return sent


def _query_names(spec: dict[str, Any], path: str) -> set[str]:
    op = spec["paths"][path]["get"]
    return {p["name"] for p in op.get("parameters", []) if p["in"] == "query"}


async def test_transport_query_parameters_are_pinned(spec: dict[str, Any]) -> None:
    transport_paths = {p for p in spec["paths"] if p.startswith("/v1/service/transport")}
    assert transport_paths == set(_EXPECTED_QUERY), "Map transport 경로 집합이 바뀌었다"
    for path, expected in _EXPECTED_QUERY.items():
        assert _query_names(spec, path) == expected, path
    sent = await _sent_queries()
    assert sent, "client가 아무 요청도 보내지 않았다"
    for path, keys in sent.items():
        template = path.replace("/f1", "/{feature_id}")
        assert keys <= _query_names(spec, template), (path, keys)


def test_product_code_mapping_matches_vendored_spec(spec: dict[str, Any]) -> None:
    """PinVi의 product_key→product_code 표가 Map이 문서화한 코드 집합과 같다."""
    op = spec["paths"]["/v1/service/transport/fuel-stations/{feature_id}/price-history"]["get"]
    (param,) = [p for p in op["parameters"] if p["name"] == "product_code"]
    documented = set(re.findall(r"[A-Z]\d{3}", param["description"]))
    assert documented == set(PRODUCT_CODE_BY_KEY.values())


def test_client_module_requests_exactly_the_transport_paths(spec: dict[str, Any]) -> None:
    """client 소스의 경로 리터럴 = vendored transport 경로 전체(빠진 경로 = 검사 구멍, 남은 것 = 죽은 핀)."""
    source = Path(inspect.getsourcefile(kor_travel_map_transport) or "").read_text(encoding="utf-8")
    requested = set(re.findall(r'"(/v1/[^"]*)"', source))
    transport_paths = {p for p in spec["paths"] if p.startswith("/v1/service/transport")}
    assert requested == transport_paths


def test_pinvi_limit_matches_map_cap(spec: dict[str, Any]) -> None:
    for dataset in LAYER_DATASET_PATH.values():
        params = spec["paths"][f"/v1/service/transport/{dataset}"]["get"]["parameters"]
        limit = next(p for p in params if p["name"] == "limit")
        assert limit["schema"]["maximum"] == _MAX_LIMIT


def test_price_history_reasons_match_map_enum(spec: dict[str, Any]) -> None:
    """PinVi가 아는 이유 = Map `PriceHistoryBlock.reason` enum(모르는 값은 `upstream_contract`로 접힌다 — 새 이유가
    조용히 접히지 않게 exact로 핀한다)."""
    reason = spec["components"]["schemas"]["PriceHistoryBlock"]["properties"]["reason"]
    [enum] = [branch["enum"] for branch in reason["anyOf"] if "enum" in branch]
    assert set(PRICE_HISTORY_REASONS) == set(enum)
    assert len(PRICE_HISTORY_REASONS) == len(enum)


def test_status_dataset_names_are_pinned() -> None:
    """OpenAPI에서 `dataset`은 그냥 문자열이라 계약으로 검증할 수 없다 — Map
    `providers/kor_travel_transport_state.py`(e9d0e53c)의 이름을 여기 핀한다. Map이 이름을 바꾸면 상태가
    레이어마다 `UPSTREAM_CONTRACT`로 보이므로(조용한 오답은 아니다) 그때 이 표와 함께 고친다.
    """
    assert LAYER_MAP_DATASET == {
        "fuel_station": "transport.fuel_stations",
        "rest_area": "transport.rest_areas",
        "highway_incident": "transport.highway_incidents",
        "airport": "transport.airports",
    }


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
        # 타입: Map이 보낼 수 있는 JSON 타입 ⊆ PinVi가 받는 타입(null·number 확장 포함).
        ours = _json_types(model.model_json_schema(), model.model_json_schema()["properties"][name])
        theirs = _json_types(spec, properties_schema(schema, name))
        assert theirs <= ours, f"{schema_name}.{name}: Map {theirs} ⊄ PinVi {ours}"


def properties_schema(schema: dict[str, Any], name: str) -> dict[str, Any]:
    prop: dict[str, Any] = schema["properties"][name]
    return prop


def test_type_check_catches_a_narrowed_field(spec: dict[str, Any]) -> None:
    """타입 대조가 실제로 빨개지는지 — Map이 null을 허용하는데 PinVi가 str만 받는 경우."""
    nullable_map = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    assert not _json_types(spec, nullable_map) <= _json_types(spec, {"type": "string"})


# ── fixture 검증기(`tests/openapi_subset.py`) ───────────────────────────────


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
