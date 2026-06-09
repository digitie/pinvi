"""`/geo/*` + `/regions/*` 라우터 통합 테스트 (kraddr-geo client는 stub 주입)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

pytestmark = pytest.mark.asyncio


class _FakeKraddrGeoClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def reverse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("reverse", kwargs))
        return {"status": "ok", "candidates": [{"address": "부산 수영구 광안동"}]}

    async def search(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("search", kwargs))
        return {"status": "ok", "total": 1, "candidates": [{"address": "테헤란로"}]}

    async def regions_within_radius(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("regions", kwargs))
        return {"status": "ok", "candidates": [{"region_name": "광안동"}]}

    async def geocode(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("geocode", kwargs))
        return {"status": "ok", "candidates": [{"point": {"x": 129.1, "y": 35.1}}]}


@pytest.fixture
def fake_geo_client() -> Iterator[_FakeKraddrGeoClient]:
    from app.clients.kraddr_geo import get_kraddr_geo_client
    from app.main import app

    fake = _FakeKraddrGeoClient()
    app.dependency_overrides[get_kraddr_geo_client] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_kraddr_geo_client, None)


async def test_geo_reverse_returns_candidates(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, fake_geo_client: Any
) -> None:
    user_id, _ = verified_user
    resp = await client.get(
        "/geo/reverse?longitude=129.118&latitude=35.155&radius_m=200",
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "ok"
    assert data["candidates"][0]["address"] == "부산 수영구 광안동"
    assert fake_geo_client.calls[0][0] == "reverse"
    assert fake_geo_client.calls[0][1] == {"lon": 129.118, "lat": 35.155, "radius_m": 200}


async def test_regions_within_radius_returns_candidates(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, fake_geo_client: Any
) -> None:
    user_id, _ = verified_user
    resp = await client.get(
        "/regions/within-radius?longitude=129.0&latitude=35.0&radius_m=2000",
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["candidates"][0]["region_name"] == "광안동"


async def test_geo_reverse_rejects_out_of_korea(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, fake_geo_client: Any
) -> None:
    user_id, _ = verified_user
    resp = await client.get(
        "/geo/reverse?longitude=10.0&latitude=50.0",
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 422, resp.text


async def test_geo_requires_auth(client: Any) -> None:
    resp = await client.get("/geo/reverse?longitude=129.0&latitude=35.0")
    assert resp.status_code == 401


async def test_geo_503_when_client_missing(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any
) -> None:
    # lifespan이 ASGITransport에서 실행되지 않아 app.state.kraddr_geo_client = 미설정 → 503.
    user_id, _ = verified_user
    resp = await client.get(
        "/geo/search?query=테헤란로",
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "GEOCODING_SERVICE_UNAVAILABLE"
