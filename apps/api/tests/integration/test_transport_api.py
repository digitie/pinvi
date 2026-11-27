"""`/transport/*` — Map transport 레이어 (ADR-076).

핵심 단언: 플래그가 꺼져 있으면 Map을 부르지 않고, Map이 503이어도 `/transport/status`·
`/transport/markers-in-bounds`는 200(레이어별 강등)이다 — 지도·여행 화면 보호.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from app.clients.kor_travel_map import KorTravelMapClient, get_optional_kor_travel_map_client
from app.core.config import settings
from app.main import app
from tests import transport_map_fixtures as fx

pytestmark = pytest.mark.asyncio

_BBOX = "126.9,37.4,127.1,37.6"
Handler = Callable[[httpx.Request], httpx.Response]


class _Map:
    def __init__(self, handler: Handler) -> None:
        self.requests: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request)

        self.client = KorTravelMapClient(
            httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(record)),
            service_token="svc",
            max_attempts=1,
            backoff_base_seconds=0.0,
        )


def _install(handler: Handler) -> _Map:
    fake = _Map(handler)
    app.dependency_overrides[get_optional_kor_travel_map_client] = lambda: fake.client
    return fake


def _ok(request: httpx.Request) -> httpx.Response:
    path = request.url.path.removeprefix("/v1/service/transport/")
    parts = path.split("/")
    if parts[0] == "status":
        return httpx.Response(200, json=fx.status_body())
    if len(parts) == 1:
        return httpx.Response(200, json=fx.list_body(parts[0]))
    if parts[1:] == ["near-batch"] and request.method == "POST":
        return httpx.Response(200, json=fx.list_body(parts[0]))
    if len(parts) == 3:
        return httpx.Response(200, json=fx.history_body(available=False))
    if parts[1] in {v["feature_id"] for v in fx.ITEMS.values()}:
        return httpx.Response(200, json=fx.detail_body(parts[0]))
    return httpx.Response(404, json=fx.problem_body(404, "NOT_FOUND"))


@pytest.fixture(autouse=True)
def _restore() -> Iterator[None]:
    original = settings.pinvi_kor_travel_map_transport_enabled
    yield
    settings.pinvi_kor_travel_map_transport_enabled = original
    app.dependency_overrides.pop(get_optional_kor_travel_map_client, None)


async def _get(client: Any, auth_cookies: Any, user: tuple[str, str], url: str) -> httpx.Response:
    resp: httpx.Response = await client.get(url, cookies=auth_cookies(user[0]))
    return resp


async def test_flag_off_never_calls_map(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    settings.pinvi_kor_travel_map_transport_enabled = False
    fake = _install(_ok)
    status_resp = await _get(client, auth_cookies, verified_user, "/transport/status")
    markers = await _get(
        client, auth_cookies, verified_user, f"/transport/markers-in-bounds?bbox={_BBOX}&zoom=12"
    )
    detail = await _get(client, auth_cookies, verified_user, f"/transport/airports/{fx.AIRPORT_ID}")
    assert status_resp.status_code == 200
    assert status_resp.json()["data"] == {"enabled": False, "layers": []}
    assert markers.status_code == 200
    assert {layer["status"] for layer in markers.json()["data"]["layers"]} == {"disabled"}
    assert detail.status_code == 503
    assert detail.json()["error"]["code"] == "TRANSPORT_DISABLED"
    assert fake.requests == []


async def test_requires_login(client: Any) -> None:
    settings.pinvi_kor_travel_map_transport_enabled = True
    resp = await client.get("/transport/status")
    assert resp.status_code == 401


async def test_markers_and_status_when_enabled(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    settings.pinvi_kor_travel_map_transport_enabled = True
    fake = _install(_ok)
    resp = await _get(
        client,
        auth_cookies,
        verified_user,
        f"/transport/markers-in-bounds?bbox={_BBOX}&zoom=12&layers=airport,rest_area&limit=50",
    )
    assert resp.status_code == 200, resp.text
    layers = resp.json()["data"]["layers"]
    assert [layer["layer"] for layer in layers] == ["rest_area", "airport"]
    airport = layers[1]
    assert airport["status"] == "ok"
    assert airport["items"][0]["layer"] == "airport"
    assert airport["items"][0]["iata_code"] == "GMP"
    assert airport["freshness"]["age_seconds"] == 600
    assert all(r.headers["X-Kor-Travel-Map-Service-Token"] == "svc" for r in fake.requests)

    status_resp = await _get(client, auth_cookies, verified_user, "/transport/status")
    data = status_resp.json()["data"]
    assert data["enabled"] is True
    fuel = next(layer for layer in data["layers"] if layer["layer"] == "fuel_station")
    assert fuel == {
        "layer": "fuel_station",
        "available": False,
        "reason": "NOT_LOADED",
        "freshness": None,
    }


async def test_map_down_degrades_without_5xx(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    settings.pinvi_kor_travel_map_transport_enabled = True
    _install(
        lambda _r: httpx.Response(503, json=fx.problem_body(503, "TRANSPORT_STATE_UNAVAILABLE"))
    )
    markers = await _get(
        client, auth_cookies, verified_user, f"/transport/markers-in-bounds?bbox={_BBOX}&zoom=12"
    )
    assert markers.status_code == 200
    assert {(r["status"], r["reason"]) for r in markers.json()["data"]["layers"]} == {
        ("unavailable", "STORE_UNAVAILABLE")
    }
    status_resp = await _get(client, auth_cookies, verified_user, "/transport/status")
    assert status_resp.status_code == 200
    assert not any(layer["available"] for layer in status_resp.json()["data"]["layers"])
    detail = await _get(
        client, auth_cookies, verified_user, f"/transport/fuel-stations/{fx.FUEL_STATION_ID}"
    )
    assert detail.status_code == 503
    assert detail.json()["error"]["code"] == "TRANSPORT_UNAVAILABLE"


async def test_detail_history_and_not_found(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    settings.pinvi_kor_travel_map_transport_enabled = True
    fake = _install(_ok)
    detail = await _get(
        client, auth_cookies, verified_user, f"/transport/rest-areas/{fx.REST_AREA_ID}"
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["item"]["layer"] == "rest_area"

    # 주유소 상세는 transport식 표시(상표 로고·기준정보 반영)에 쓰는 Map 필드를 그대로 전한다.
    fuel = await _get(
        client, auth_cookies, verified_user, f"/transport/fuel-stations/{fx.FUEL_STATION_ID}"
    )
    assert fuel.status_code == 200, fuel.text
    fuel_item = fuel.json()["data"]["item"]
    assert fuel_item["brand_code"] == "SKE"
    assert fuel_item["source_last_seen_at"] is not None
    # 판매하지 않는 유종(price null)은 계약대로 그대로 오고, 숨기는 것은 표시 규칙이다.
    assert [p["price"] for p in fuel_item["prices"]] == [1689.0, None]

    history = await _get(
        client,
        auth_cookies,
        verified_user,
        f"/transport/fuel-stations/{fx.FUEL_STATION_ID}/price-history?days=7",
    )
    assert history.status_code == 200, history.text
    body = history.json()["data"]
    assert body["status"] == "unavailable" and body["reason"] == "disabled"

    missing = await _get(client, auth_cookies, verified_user, "/transport/airports/f_missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "TRANSPORT_FEATURE_NOT_FOUND"

    before = len(fake.requests)
    injected = await _get(client, auth_cookies, verified_user, "/transport/airports/..%2Fstatus")
    assert injected.status_code in (404, 422)
    assert len(fake.requests) == before


async def test_rejects_unknown_layer(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    settings.pinvi_kor_travel_map_transport_enabled = True
    _install(_ok)
    resp = await _get(
        client,
        auth_cookies,
        verified_user,
        f"/transport/markers-in-bounds?bbox={_BBOX}&zoom=12&layers=parking",
    )
    assert resp.status_code == 400


async def test_out_of_range_bbox_is_clamped_not_500(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    settings.pinvi_kor_travel_map_transport_enabled = True
    fake = _install(_ok)
    resp = await _get(
        client,
        auth_cookies,
        verified_user,
        "/transport/markers-in-bounds?bbox=100,10,140,50&zoom=6&layers=airport",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["bbox"] == {
        "lng_min": 124.0,
        "lat_min": 33.0,
        "lng_max": 132.0,
        "lat_max": 43.0,
    }
    # Map에는 국내 범위(위도 39 상한)와 교차한 상자가 간다.
    assert fake.requests[-1].url.params["max_lat"] == "39.0"
    bad = await _get(
        client, auth_cookies, verified_user, "/transport/markers-in-bounds?bbox=a,b,c,d&zoom=6"
    )
    assert bad.status_code == 400


async def test_markers_near_uses_map_near_search(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    settings.pinvi_kor_travel_map_transport_enabled = True
    fake = _install(_ok)
    # 픽스처 주유소(127.0276, 37.4979) 바로 옆 기준 장소.
    resp = await _get(
        client,
        auth_cookies,
        verified_user,
        "/transport/markers-near?points=127.03,37.5;127.03,37.5&layers=fuel_station",
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["radius_m"] == {"fuel_station": 10000}
    fuel = data["layers"][0]
    assert fuel["status"] == "ok"
    assert fuel["items"][0]["feature_id"] == fx.FUEL_STATION_ID
    assert fuel["items"][0]["distance_m"] < 1000
    # 레이어당 Map 묶음 근처 조회 한 번(T-READ-04), 같은 좌표 두 번은 한 점으로 보낸다.
    assert len(fake.requests) == 1
    sent = fake.requests[0]
    assert (sent.method, sent.url.path) == (
        "POST",
        "/v1/service/transport/fuel-stations/near-batch",
    )
    assert json.loads(sent.content) == {
        "points": [{"lon": 127.03, "lat": 37.5}],
        "radius_m": 10050.0,
        "limit": 200,
    }


async def test_markers_near_falls_back_on_a_map_without_near_batch(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    """옛 Map(묶음 route 없음 → 405)과 짝지어져도 중심마다 근처 조회로 같은 결과를 낸다."""
    settings.pinvi_kor_travel_map_transport_enabled = True

    def legacy(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(405, json={"detail": "Method Not Allowed"})
        return _ok(request)

    fake = _install(legacy)
    resp = await _get(
        client,
        auth_cookies,
        verified_user,
        "/transport/markers-near?points=127.03,37.5&layers=fuel_station",
    )
    assert resp.status_code == 200, resp.text
    fuel = resp.json()["data"]["layers"][0]
    assert fuel["status"] == "ok"
    assert fuel["items"][0]["feature_id"] == fx.FUEL_STATION_ID
    assert [r.method for r in fake.requests] == ["POST", "GET"]
    assert fake.requests[1].url.params["radius_m"] == "12000.0"


async def test_markers_near_defaults_and_validation(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    settings.pinvi_kor_travel_map_transport_enabled = True
    fake = _install(_ok)
    empty = await _get(client, auth_cookies, verified_user, "/transport/markers-near")
    assert empty.status_code == 200
    assert [(r["layer"], r["status"]) for r in empty.json()["data"]["layers"]] == [
        ("fuel_station", "ok"),
        ("highway_incident", "ok"),
    ]
    assert fake.requests == []
    for query in (
        "points=127.0,37.5&layers=airport",
        "points=127.0,37.5&layers=rest_area",
        "points=1.0,2.0",
        "points=abc",
        "points=" + ";".join(f"127.{i:03d},37.5" for i in range(61)),
    ):
        resp = await _get(client, auth_cookies, verified_user, f"/transport/markers-near?{query}")
        assert resp.status_code == 400, query
    assert fake.requests == []


async def test_markers_near_flag_off_never_calls_map(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    settings.pinvi_kor_travel_map_transport_enabled = False
    fake = _install(_ok)
    resp = await _get(
        client, auth_cookies, verified_user, "/transport/markers-near?points=127,37.5"
    )
    assert resp.status_code == 200
    assert {r["status"] for r in resp.json()["data"]["layers"]} == {"disabled"}
    assert fake.requests == []
