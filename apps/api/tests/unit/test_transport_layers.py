"""Map transport → PinVi 레이어 투영·강등 (ADR-076 D4)."""

from __future__ import annotations

import asyncio
import json
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


def _near_page(items: list[tuple[str, float, float]], *, truncated: bool = False) -> dict[str, Any]:
    """Map 근처 검색 응답 — (feature_id, lon, lat) 주유소 목록."""
    body = fx.list_body("fuel-stations", truncated=truncated)
    template = body["data"]["items"][0]
    body["data"]["items"] = [
        {**template, "feature_id": fid, "coord": {"lon": lon, "lat": lat}}
        for fid, lon, lat in items
    ]
    return body


def _legacy_map(handler: Handler) -> Handler:
    """묶음 근처 route가 없는 옛 Map — ``POST …/near-batch``는 405(``GET /{feature_id}``가 경로를 잡는다)."""

    def wrapped(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(405, json={"detail": "Method Not Allowed"})
        return handler(request)

    return wrapped


async def test_near_points_calls_map_once_per_layer_with_every_point() -> None:
    """T-READ-04: 장소 60곳 x 레이어 2개 → Map 묶음 조회 2번(중심 묶기 없이 장소 전부, 레이어별 반경)."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        dataset = request.url.path.removeprefix("/v1/service/transport/").split("/")[0]
        return httpx.Response(200, json=fx.list_body(dataset))

    points = [(127.0, 34.0 + i * 0.05) for i in range(60)]
    results = await transport_layers.markers_near_points(
        _client(handler), points=points, layers=["fuel_station", "highway_incident"], limit=50
    )
    assert [(r.layer, r.status) for r in results] == [
        ("fuel_station", "ok"),
        ("highway_incident", "ok"),
    ]
    assert sorted((r.method, r.url.path) for r in seen) == [
        ("POST", "/v1/service/transport/fuel-stations/near-batch"),
        ("POST", "/v1/service/transport/highway-incidents/near-batch"),
    ]
    bodies = {r.url.path.split("/")[-2]: json.loads(r.content) for r in seen}
    slack = transport_layers.NEAR_BATCH_SLACK_M
    assert bodies["fuel-stations"]["radius_m"] == float(10_000 + slack)
    assert bodies["highway-incidents"]["radius_m"] == float(20_000 + slack)
    for body in bodies.values():
        assert body["limit"] == 50
        assert body["points"] == [{"lon": lon, "lat": lat} for lon, lat in points]
    assert all(not r.url.params for r in seen)


async def test_near_batch_refilters_exact_radius_and_recomputes_distance() -> None:
    """Map 묶음 응답(여유 반경·Map 거리)을 PinVi 거리로 다시 거르고 가까운 순으로 둔다."""
    page = _near_page(
        [
            ("f_x_place_far", 127.0, 37.595),  # 약 10.6 km — 반경 밖
            ("f_x_place_mid", 127.0, 37.58),
            ("f_x_place_near", 127.0, 37.501),
        ]
    )
    for raw in page["data"]["items"]:
        raw["distance_m"] = 1.0  # Map 거리는 쓰지 않는다

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=page)

    results = await transport_layers.markers_near_points(
        _client(handler),
        points=[(127.0, 37.5), (127.005, 37.505)],
        layers=["fuel_station"],
        limit=100,
    )
    fuel = results[0]
    assert fuel.status == "ok" and fuel.truncated is False
    assert [item.feature_id for item in fuel.items] == ["f_x_place_near", "f_x_place_mid"]
    assert fuel.items[0].distance_m is not None and 100 < fuel.items[0].distance_m < 200


async def test_near_batch_and_legacy_fallback_give_the_same_result() -> None:
    """같은 Map 데이터에서 묶음 경로와 옛 Map(405) fallback 경로의 결과가 같다."""
    stations = [
        ("f_x_place_shared", 127.0, 37.55),
        ("f_x_place_seoul", 127.0, 37.51),
        ("f_x_place_other", 127.0, 37.78),
        ("f_x_place_away", 127.0, 38.2),
    ]
    points = [(127.0, 37.5), (127.0, 37.7)]

    def within(lon: float, lat: float, radius: float) -> list[tuple[str, float, float]]:
        return [s for s in stations if transport_layers.haversine_m(s[1], s[2], lon, lat) <= radius]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = json.loads(request.content)
            hits = {s for p in body["points"] for s in within(p["lon"], p["lat"], body["radius_m"])}
            return httpx.Response(200, json=_near_page(sorted(hits)))
        q = request.url.params
        return httpx.Response(
            200, json=_near_page(within(float(q["lon"]), float(q["lat"]), float(q["radius_m"])))
        )

    batch = await transport_layers.markers_near_points(
        _client(handler), points=points, layers=["fuel_station"], limit=100
    )
    legacy = await transport_layers.markers_near_points(
        _client(_legacy_map(handler)), points=points, layers=["fuel_station"], limit=100
    )
    assert batch[0].status == legacy[0].status == "ok"
    assert [(i.feature_id, i.distance_m) for i in batch[0].items] == [
        (i.feature_id, i.distance_m) for i in legacy[0].items
    ]
    assert [i.feature_id for i in batch[0].items] == [
        "f_x_place_seoul",
        "f_x_place_shared",
        "f_x_place_other",
    ]


async def test_near_batch_failure_degrades_layer_without_fallback() -> None:
    """405가 아닌 Map 오류(503)는 옛 경로로 떨어지지 않고 그 레이어만 강등한다."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(503, json=fx.problem_body(503, "TRANSPORT_STATE_NOT_LOADED"))

    results = await transport_layers.markers_near_points(
        _client(handler), points=[(127.0, 37.5)], layers=["highway_incident"], limit=10
    )
    assert (results[0].status, results[0].reason) == ("unavailable", "NOT_LOADED")
    assert [r.method for r in seen] == ["POST"]


def test_cluster_points_merges_close_places_only() -> None:
    # 강남역 두 곳(약 300 m)은 한 중심, 부산은 따로.
    centers = transport_layers.cluster_points(
        [(127.0276, 37.4979), (127.0300, 37.4990), (129.0756, 35.1796)]
    )
    assert centers == [(127.0276, 37.4979), (129.0756, 35.1796)]


async def test_near_points_filters_exact_radius_and_dedupes() -> None:
    # 기준 장소 (127.0, 37.5). 위도 0.01도 ≈ 1.11 km → 0.08도 ≈ 8.9 km(안), 0.095도 ≈ 10.6 km(밖).
    page = _near_page(
        [
            ("f_x_place_far", 127.0, 37.595),
            ("f_x_place_mid", 127.0, 37.58),
            ("f_x_place_near", 127.0, 37.501),
        ]
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=page)

    results = await transport_layers.markers_near_points(
        _client(_legacy_map(handler)),
        # 두 기준 장소는 2 km 안이라 한 번만 조회한다.
        points=[(127.0, 37.5), (127.005, 37.505)],
        layers=["fuel_station"],
        limit=100,
    )
    assert len(seen) == 1
    params = seen[0].url.params
    assert seen[0].method == "GET"
    assert params["radius_m"] == str(float(10_000 + transport_layers.NEAR_MERGE_M))
    assert "min_lon" not in params
    fuel = results[0]
    assert fuel.status == "ok" and fuel.truncated is False
    assert [item.feature_id for item in fuel.items] == ["f_x_place_near", "f_x_place_mid"]
    assert fuel.items[0].distance_m is not None and fuel.items[0].distance_m < 200


async def test_near_points_unions_far_places_and_keeps_nearest_distance() -> None:
    seoul = _near_page([("f_x_place_shared", 127.0, 37.55), ("f_x_place_seoul", 127.0, 37.51)])
    other = _near_page([("f_x_place_shared", 127.0, 37.55), ("f_x_place_other", 127.0, 37.78)])
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        lat = float(request.url.params["lat"])
        return httpx.Response(200, json=seoul if lat < 37.6 else other)

    results = await transport_layers.markers_near_points(
        _client(_legacy_map(handler)),
        points=[(127.0, 37.5), (127.0, 37.7)],  # 약 22 km 떨어진 두 곳
        layers=["fuel_station"],
        limit=100,
    )
    assert len(seen) == 2
    ids = [item.feature_id for item in results[0].items]
    assert ids == ["f_x_place_seoul", "f_x_place_shared", "f_x_place_other"]
    shared = results[0].items[1]
    # 0.05도 ≈ 5.6 km(37.5 기준) — 37.7 기준(16.7 km)이 아니라 가까운 쪽 거리.
    assert shared.distance_m is not None and 5_000 < shared.distance_m < 6_000


async def test_near_points_limit_and_truncation() -> None:
    page = _near_page([(f"f_x_place_{i}", 127.0, 37.5 + i * 0.001) for i in range(5)])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=page)

    results = await transport_layers.markers_near_points(
        _client(_legacy_map(handler)), points=[(127.0, 37.5)], layers=["fuel_station"], limit=3
    )
    assert results[0].truncated is True
    assert [item.feature_id for item in results[0].items] == [
        "f_x_place_0",
        "f_x_place_1",
        "f_x_place_2",
    ]


async def test_near_points_one_failed_query_degrades_layer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if float(request.url.params["lat"]) > 37.6:
            return httpx.Response(503, json=fx.problem_body(503, "TRANSPORT_STATE_NOT_LOADED"))
        return httpx.Response(200, json=_near_page([]))

    results = await transport_layers.markers_near_points(
        _client(_legacy_map(handler)),
        points=[(127.0, 37.5), (127.0, 37.7)],
        layers=["highway_incident"],
        limit=10,
    )
    assert results[0].status == "unavailable"
    assert results[0].reason == "NOT_LOADED"


async def test_near_points_without_points_skips_map() -> None:
    handler, seen = _by_dataset({})
    results = await transport_layers.markers_near_points(
        _client(handler), points=[], layers=["fuel_station", "highway_incident"], limit=10
    )
    assert [(r.layer, r.status, r.items) for r in results] == [
        ("fuel_station", "ok", []),
        ("highway_incident", "ok", []),
    ]
    assert seen == []
