"""Map transport → PinVi 레이어 투영·강등 (ADR-076 D4)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
import pytest

from app.clients.kor_travel_map import KorTravelMapClient, KorTravelMapFeatureNotFound
from app.clients.kor_travel_map_transport import KorTravelMapTransportClient
from app.core.time import KST
from app.schemas.transport import FuelStationItem, RestAreaItem
from app.services import transport_layers
from tests import transport_map_fixtures as fx

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> KorTravelMapTransportClient:
    http = httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler))
    return KorTravelMapTransportClient(
        KorTravelMapClient(http, service_token="t", max_attempts=1, backoff_base_seconds=0.0)
    )


def _by_dataset(responses: dict[str, httpx.Response]) -> tuple[Handler, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        dataset = request.url.path.removeprefix("/v1/service/transport/").split("/")[0]
        return responses[dataset]

    return handler, seen


def test_clip_to_korea() -> None:
    assert transport_layers.clip_to_korea((120.0, 30.0, 140.0, 45.0)) == (124.0, 33.0, 132.0, 39.0)
    assert transport_layers.clip_to_korea((126.9, 37.4, 127.1, 37.6)) == (126.9, 37.4, 127.1, 37.6)
    assert transport_layers.clip_to_korea((100.0, 10.0, 110.0, 20.0)) is None


async def test_layers_degrade_independently() -> None:
    handler, seen = _by_dataset(
        {
            "fuel-stations": httpx.Response(
                503, json=fx.problem_body(503, "TRANSPORT_STATE_NOT_LOADED")
            ),
            "rest-areas": httpx.Response(200, json=fx.list_body("rest-areas", truncated=True)),
            "highway-incidents": httpx.Response(404, json=fx.problem_body(404, "NOT_FOUND")),
            "airports": httpx.Response(200, json={"data": {"items": "x"}, "meta": {}}),
        }
    )
    results = await transport_layers.markers_in_bounds(
        _client(handler),
        bbox=(126.0, 36.0, 128.0, 38.0),
        layers=["fuel_station", "rest_area", "highway_incident", "airport"],
        limit=100,
    )
    by_layer = {r.layer: r for r in results}
    assert by_layer["fuel_station"].status == "unavailable"
    assert by_layer["fuel_station"].reason == "NOT_LOADED"
    assert by_layer["highway_incident"].reason == "UPSTREAM_REJECTED"
    assert by_layer["airport"].reason == "UPSTREAM_CONTRACT"
    rest = by_layer["rest_area"]
    assert rest.status == "ok" and rest.truncated is True
    assert rest.fuel_price_freshness is not None
    item = rest.items[0]
    assert isinstance(item, RestAreaItem)
    assert item.fuel_prices is not None and item.fuel_prices.gasoline_price == 1650
    assert all(r.url.params["limit"] == "100" for r in seen)


async def test_bbox_outside_korea_skips_map() -> None:
    handler, seen = _by_dataset({})
    results = await transport_layers.markers_in_bounds(
        _client(handler), bbox=(100.0, 10.0, 110.0, 20.0), layers=["airport"], limit=10
    )
    assert results[0].status == "ok" and results[0].items == []
    assert seen == []


async def test_slow_layer_hits_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transport_layers, "LAYER_DEADLINE_SECONDS", 0.01)

    class _Slow(KorTravelMapTransportClient):
        async def list_items(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            await asyncio.sleep(1)
            return {}

    slow = _Slow(KorTravelMapClient(httpx.AsyncClient()))
    results = await transport_layers.markers_in_bounds(
        slow, bbox=(126.0, 37.0, 127.0, 38.0), layers=["airport"], limit=10
    )
    assert results[0].status == "unavailable"
    assert results[0].reason == "UPSTREAM_UNAVAILABLE"


async def test_status_maps_datasets_to_layers() -> None:
    handler, _ = _by_dataset({"status": httpx.Response(200, json=fx.status_body())})
    statuses = {s.layer: s for s in await transport_layers.layer_status(_client(handler))}
    assert set(statuses) == {"fuel_station", "rest_area", "highway_incident", "airport"}
    assert statuses["fuel_station"].available is False
    assert statuses["fuel_station"].reason == "NOT_LOADED"
    assert statuses["airport"].available is True
    assert statuses["airport"].freshness is not None


async def test_status_store_down_marks_every_layer() -> None:
    handler, _ = _by_dataset(
        {"status": httpx.Response(503, json=fx.problem_body(503, "TRANSPORT_STATE_UNAVAILABLE"))}
    )
    statuses = await transport_layers.layer_status(_client(handler))
    assert {s.reason for s in statuses} == {"STORE_UNAVAILABLE"}
    assert not any(s.available for s in statuses)


async def test_status_dataset_error_is_store_unavailable_without_message() -> None:
    body = fx.status_body(fuel_loaded=False)
    body["data"]["datasets"][0]["error"] = "redis: secret internal detail"
    handler, _ = _by_dataset({"status": httpx.Response(200, json=body)})
    statuses = {s.layer: s for s in await transport_layers.layer_status(_client(handler))}
    assert statuses["fuel_station"].reason == "STORE_UNAVAILABLE"
    assert "secret" not in statuses["fuel_station"].model_dump_json()


async def test_detail_and_mismatched_id() -> None:
    handler, _ = _by_dataset(
        {"fuel-stations": httpx.Response(200, json=fx.detail_body("fuel-stations"))}
    )
    detail = await transport_layers.detail(_client(handler), "fuel_station", fx.FUEL_STATION_ID)
    assert isinstance(detail.item, FuelStationItem)
    assert [p.price for p in detail.item.prices] == [1689.0, None]
    with pytest.raises(transport_layers.TransportContractError):
        await transport_layers.detail(_client(handler), "fuel_station", "other-id")


async def test_detail_404_propagates() -> None:
    handler, _ = _by_dataset(
        {"airports": httpx.Response(404, json=fx.problem_body(404, "NOT_FOUND"))}
    )
    with pytest.raises(KorTravelMapFeatureNotFound):
        await transport_layers.detail(_client(handler), "airport", fx.AIRPORT_ID)


async def test_price_history_filters_product_and_uses_since() -> None:
    handler, seen = _by_dataset(
        {"fuel-stations": httpx.Response(200, json=fx.history_body(available=True))}
    )
    now = datetime(2026, 10, 23, 12, 0, tzinfo=KST)
    out = await transport_layers.fuel_price_history(
        _client(handler), fx.FUEL_STATION_ID, product_key="diesel", days=7, now=now
    )
    assert out.status == "available"
    assert [p.product_key for p in out.items] == ["diesel"]
    assert [p.product_key for p in out.current_prices] == ["diesel"]
    assert seen[0].url.params["since"] == "2026-10-16T12:00:00+09:00"
    # limit은 유종 합계 행 수라 한 유종만 볼 때는 Map이 서버에서 거르게 한다(+ 상한 1000).
    assert seen[0].url.params["product_code"] == "D047"
    assert seen[0].url.params["limit"] == "1000"

    unknown = await transport_layers.fuel_price_history(
        _client(handler), fx.FUEL_STATION_ID, product_key="hydrogen", days=7, now=now
    )
    assert unknown.items == [] and unknown.current_prices == []
    assert "product_code" not in seen[1].url.params
    assert seen[1].url.params["limit"] == "1000"


async def test_price_history_without_product_sends_no_product_code() -> None:
    handler, seen = _by_dataset(
        {"fuel-stations": httpx.Response(200, json=fx.history_body(available=True))}
    )
    await transport_layers.fuel_price_history(
        _client(handler),
        fx.FUEL_STATION_ID,
        product_key=None,
        days=90,
        now=datetime(2026, 10, 23, 12, 0, tzinfo=KST),
    )
    assert "product_code" not in seen[0].url.params
    assert seen[0].url.params["limit"] == "1000"
    assert seen[0].url.params["since"] == "2026-07-25T12:00:00+09:00"


async def test_price_history_unavailable_is_not_an_error() -> None:
    handler, _ = _by_dataset(
        {"fuel-stations": httpx.Response(200, json=fx.history_body(available=False))}
    )
    out = await transport_layers.fuel_price_history(
        _client(handler),
        fx.FUEL_STATION_ID,
        product_key=None,
        days=30,
        now=datetime(2026, 10, 23, tzinfo=KST),
    )
    assert out.status == "unavailable" and out.reason == "disabled"
    assert len(out.current_prices) == 2


async def test_status_one_broken_freshness_degrades_only_that_layer() -> None:
    body = fx.status_body(fuel_loaded=True)
    body["data"]["datasets"][3]["freshness"] = {"broken": True}  # highway_incidents
    handler, _ = _by_dataset({"status": httpx.Response(200, json=body)})
    statuses = {s.layer: s for s in await transport_layers.layer_status(_client(handler))}
    assert statuses["highway_incident"].reason == "UPSTREAM_CONTRACT"
    assert statuses["airport"].available is True
    assert statuses["fuel_station"].available is True


async def test_one_bad_item_does_not_drop_the_layer() -> None:
    body = fx.list_body("airports")
    body["data"]["items"].append({"feature_id": "x" * 200})
    handler, _ = _by_dataset({"airports": httpx.Response(200, json=body)})
    [result] = await transport_layers.markers_in_bounds(
        _client(handler), bbox=(126.0, 37.0, 127.0, 38.0), layers=["airport"], limit=10
    )
    assert result.status == "ok"
    assert [i.feature_id for i in result.items] == [fx.AIRPORT_ID]


async def test_utc_and_naive_datetimes() -> None:
    body = fx.list_body("airports")
    body["data"]["freshness"]["loaded_at"] = "2026-10-23T00:05:00Z"
    handler, _ = _by_dataset({"airports": httpx.Response(200, json=body)})
    [ok] = await transport_layers.markers_in_bounds(
        _client(handler), bbox=(126.0, 37.0, 127.0, 38.0), layers=["airport"], limit=10
    )
    assert ok.status == "ok" and ok.freshness is not None
    assert ok.freshness.loaded_at.utcoffset() is not None

    body["data"]["freshness"]["loaded_at"] = "2026-10-23T09:05:00"  # naive — 계약 위반
    handler, _ = _by_dataset({"airports": httpx.Response(200, json=body)})
    [bad] = await transport_layers.markers_in_bounds(
        _client(handler), bbox=(126.0, 37.0, 127.0, 38.0), layers=["airport"], limit=10
    )
    assert bad.status == "unavailable" and bad.reason == "UPSTREAM_CONTRACT"


@pytest.mark.parametrize(
    "reason",
    ["upstream_unsupported", "request_rejected", "upstream_no_collection", "upstream_timeout"],
)
async def test_price_history_t4_reasons_pass_through(reason: str) -> None:
    """Map ADR-114 D6 T4 정렬로 늘어난 이유는 `upstream_contract`로 접지 않고 그대로 전한다."""
    body = fx.history_body(available=False)
    body["data"]["history"]["reason"] = reason
    handler, _ = _by_dataset({"fuel-stations": httpx.Response(200, json=body)})
    out = await transport_layers.fuel_price_history(
        _client(handler),
        fx.FUEL_STATION_ID,
        product_key=None,
        days=7,
        now=datetime(2026, 10, 23, tzinfo=KST),
    )
    assert out.status == "unavailable" and out.reason == reason


async def test_price_history_unknown_reason_is_folded_and_id_checked() -> None:
    body = fx.history_body(available=False)
    body["data"]["history"]["reason"] = "some new internal reason"
    handler, _ = _by_dataset({"fuel-stations": httpx.Response(200, json=body)})
    out = await transport_layers.fuel_price_history(
        _client(handler),
        fx.FUEL_STATION_ID,
        product_key=None,
        days=7,
        now=datetime(2026, 10, 23, tzinfo=KST),
    )
    assert out.reason == "upstream_contract"
    with pytest.raises(transport_layers.TransportContractError):
        await transport_layers.fuel_price_history(
            _client(handler),
            "other-id",
            product_key=None,
            days=7,
            now=datetime(2026, 10, 23, tzinfo=KST),
        )
