"""kor-travel-geo v2 REST client 계약 테스트 (httpx.MockTransport)."""

from __future__ import annotations

import json as _json
from collections.abc import Callable

import httpx
import pytest

from app.clients.kor_travel_geo import (
    KorTravelGeoBadRequest,
    KorTravelGeoClient,
    KorTravelGeoUnavailable,
)

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler, **kwargs: object) -> KorTravelGeoClient:
    http = httpx.AsyncClient(
        base_url="http://kor-travel-geo.test",
        transport=httpx.MockTransport(handler),
    )
    params: dict[str, object] = {"max_attempts": 2, "backoff_base_seconds": 0.0}
    params.update(kwargs)
    return KorTravelGeoClient(http, **params)  # type: ignore[arg-type]


async def test_reverse_posts_v2_and_passes_lon_lat() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"status": "ok", "candidates": [{"address": "광안동"}]})

    client = _client(handler)
    data = await client.reverse(lon=129.118, lat=35.155, radius_m=200)
    assert seen["path"] == "/v2/reverse"
    assert seen["body"] == {  # None은 제거, lon/lat 그대로
        "lon": 129.118,
        "lat": 35.155,
        "radius_m": 200,
        "include_region": True,
        "include_zipcode": True,
    }
    assert data["candidates"][0]["address"] == "광안동"
    await client.aclose()


async def test_search_uses_type_key() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"status": "ok", "total": 0, "candidates": []})

    client = _client(handler)
    await client.search(query="테헤란로", kind="road", sig_cd="11680", size=20)
    assert seen["path"] == "/v2/search"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["type"] == "road" and body["query"] == "테헤란로" and body["size"] == 20
    await client.aclose()


async def test_regions_within_radius_path() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"status": "ok", "candidates": []})

    client = _client(handler)
    await client.regions_within_radius(lon=129.0, lat=35.0, radius_m=2000)
    assert seen["path"] == "/v2/regions/within-radius"
    await client.aclose()


async def test_5xx_retries_then_unavailable() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503, json={"code": "UPSTREAM"})

    client = _client(handler, max_attempts=3)
    with pytest.raises(KorTravelGeoUnavailable):
        await client.geocode(query="서울시청")
    assert attempts["n"] == 3
    await client.aclose()


async def test_4xx_raises_bad_request_with_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"code": "INVALID_QUERY"})

    client = _client(handler)
    with pytest.raises(KorTravelGeoBadRequest) as exc:
        await client.geocode(query="")
    assert exc.value.code == "INVALID_QUERY"
    await client.aclose()


async def test_transport_error_raises_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = _client(handler)
    with pytest.raises(KorTravelGeoUnavailable):
        await client.reverse(lon=129.0, lat=35.0)
    await client.aclose()
