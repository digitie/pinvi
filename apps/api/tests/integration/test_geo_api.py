"""`/geo/*` + `/regions/*` 라우터 통합 테스트 (kor-travel-geo client는 stub 주입)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

pytestmark = pytest.mark.asyncio


class _FakeKorTravelGeoClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def reverse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("reverse", kwargs))
        return {
            "status": "ok",
            "candidates": [
                {
                    "address": "부산 수영구 광안동",
                    "region": {"region_name": "광안동", "sig_cd": "26500"},
                }
            ],
        }

    async def search(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("search", kwargs))
        return {"status": "ok", "total": 1, "candidates": [{"address": "테헤란로"}]}

    async def regions_within_radius(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("regions", kwargs))
        return {
            "status": "ok",
            "center": {"lon": 129.0, "lat": 35.0},
            "radius_km": 2.0,
            "sido": [],
            "sigungu": [{"code": "26500", "name": "수영구", "relation": "overlaps"}],
            "emd": [{"code": "2650053000", "name": "광안동", "relation": "contains"}],
        }

    async def geocode(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("geocode", kwargs))
        return {"status": "ok", "candidates": [{"point": {"x": 129.1, "y": 35.1}}]}


@pytest.fixture
def fake_geo_client() -> Iterator[_FakeKorTravelGeoClient]:
    from app.clients.kor_travel_geo import get_kor_travel_geo_client
    from app.main import app

    fake = _FakeKorTravelGeoClient()
    app.dependency_overrides[get_kor_travel_geo_client] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_kor_travel_geo_client, None)


async def test_geo_reverse_returns_candidates(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, fake_geo_client: Any
) -> None:
    user_id, _ = verified_user
    resp = await client.get(
        "/geo/reverse?lon=129.118&lat=35.155&radius_m=200",
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "ok"
    assert data["candidates"][0]["address"] == "부산 수영구 광안동"
    assert fake_geo_client.calls[0][0] == "reverse"
    assert fake_geo_client.calls[0][1] == {"lon": 129.118, "lat": 35.155, "radius_m": 200}


async def test_regions_within_radius_returns_grouped_levels(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, fake_geo_client: Any
) -> None:
    user_id, _ = verified_user
    resp = await client.get(
        "/regions/within-radius?lon=129.0&lat=35.0&radius_km=2.0",
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["radius_km"] == 2.0
    assert data["emd"][0]["code"] == "2650053000"
    assert data["emd"][0]["relation"] == "contains"
    assert data["sigungu"][0]["name"] == "수영구"
    # 라우터가 v2 계약(radius_km + levels[]) 그대로 전달하는지 확인.
    assert fake_geo_client.calls[-1] == (
        "regions",
        {"lon": 129.0, "lat": 35.0, "radius_km": 2.0, "levels": ["sigungu", "emd"]},
    )


async def test_geo_reverse_rejects_out_of_korea(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, fake_geo_client: Any
) -> None:
    user_id, _ = verified_user
    resp = await client.get(
        "/geo/reverse?lon=10.0&lat=50.0",
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 422, resp.text


async def test_geo_requires_auth(client: Any) -> None:
    resp = await client.get("/geo/reverse?lon=129.0&lat=35.0")
    assert resp.status_code == 401


async def test_geo_503_when_client_missing(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    # lifespan이 ASGITransport에서 실행되지 않아 app.state.kor_travel_geo_client = 미설정 → 503.
    user_id, _ = verified_user
    resp = await client.get(
        "/geo/search?query=테헤란로",
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "GEOCODING_SERVICE_UNAVAILABLE"


async def test_regions_covering_point_returns_region(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, fake_geo_client: Any
) -> None:
    user_id, _ = verified_user
    resp = await client.get(
        "/regions/covering-point?lon=129.118&lat=35.155",
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["boundary_level"] == "emd"
    assert data["region"]["region_name"] == "광안동"


async def test_regions_covering_point_404_when_no_region(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    from app.clients.kor_travel_geo import get_kor_travel_geo_client
    from app.main import app

    class _NoRegion:
        async def reverse(self, **kwargs: Any) -> dict[str, Any]:
            return {"status": "ok", "candidates": [{"address": "주소만"}]}

    app.dependency_overrides[get_kor_travel_geo_client] = lambda: _NoRegion()
    try:
        user_id, _ = verified_user
        resp = await client.get(
            "/regions/covering-point?lon=129.0&lat=35.0",
            cookies=auth_cookies(user_id),
        )
        assert resp.status_code == 404, resp.text
    finally:
        app.dependency_overrides.pop(get_kor_travel_geo_client, None)


class _FakeKorTravelMapClient:
    def __init__(self, *, raise_error: bool = False) -> None:
        self.raise_error = raise_error

    async def search_features(self, **kwargs: Any) -> dict[str, Any]:
        if self.raise_error:
            from app.clients.kor_travel_map import KorTravelMapUnavailable

            raise KorTravelMapUnavailable("down")
        return {"items": [{"feature_id": "f_1", "name": "광안리 해수욕장"}], "next_cursor": None}


def _override_search_clients(kor_travel_map: Any, kor_travel_geo: Any) -> None:
    from app.clients.kor_travel_geo import get_kor_travel_geo_client
    from app.clients.kor_travel_map import get_kor_travel_map_client
    from app.main import app

    app.dependency_overrides[get_kor_travel_map_client] = lambda: kor_travel_map
    app.dependency_overrides[get_kor_travel_geo_client] = lambda: kor_travel_geo


def _clear_search_clients() -> None:
    from app.clients.kor_travel_geo import get_kor_travel_geo_client
    from app.clients.kor_travel_map import get_kor_travel_map_client
    from app.main import app

    app.dependency_overrides.pop(get_kor_travel_map_client, None)
    app.dependency_overrides.pop(get_kor_travel_geo_client, None)


async def test_unified_search_merges_sources(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _ = verified_user
    _override_search_clients(_FakeKorTravelMapClient(), _FakeKorTravelGeoClient())
    try:
        resp = await client.get("/search?q=광안", cookies=auth_cookies(user_id))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["features"][0]["feature_id"] == "f_1"
        assert data["addresses"][0]["address"] == "테헤란로"
        assert data["my_pois"] == []
        assert data["degraded_sources"] == []
    finally:
        _clear_search_clients()


async def test_unified_search_degrades_on_feature_outage(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    user_id, _ = verified_user
    _override_search_clients(_FakeKorTravelMapClient(raise_error=True), _FakeKorTravelGeoClient())
    try:
        resp = await client.get("/search?q=광안", cookies=auth_cookies(user_id))
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["features"] == []
        assert "features" in data["degraded_sources"]
        assert data["addresses"][0]["address"] == "테헤란로"
    finally:
        _clear_search_clients()
