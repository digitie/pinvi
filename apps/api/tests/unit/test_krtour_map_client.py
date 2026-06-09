"""krtour-map HTTP client 계약 테스트 (httpx.MockTransport)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.clients.krtour_map import (
    KrtourMapBadRequest,
    KrtourMapClient,
    KrtourMapFeatureNotFound,
    KrtourMapRateLimited,
    KrtourMapUnavailable,
)

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler, **kwargs: object) -> KrtourMapClient:
    http = httpx.AsyncClient(
        base_url="http://krtour.test",
        transport=httpx.MockTransport(handler),
    )
    params: dict[str, object] = {"max_attempts": 2, "backoff_base_seconds": 0.0}
    params.update(kwargs)
    return KrtourMapClient(http, **params)  # type: ignore[arg-type]


async def test_features_in_bounds_unwraps_data_and_repeats_kind() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = str(request.url.query, "utf-8")
        return httpx.Response(200, json={"data": {"count": 1, "items": []}, "meta": {}})

    client = _client(handler)
    data = await client.features_in_bounds(
        min_lon=129.0, min_lat=35.0, max_lon=129.2, max_lat=35.2, kinds=["place", "event"]
    )
    assert data == {"count": 1, "items": []}
    assert seen["path"] == "/v1/features/in-bounds"
    assert "kind=place" in seen["query"] and "kind=event" in seen["query"]
    await client.aclose()


async def test_search_features_uses_v1_path_and_split_bbox() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = str(request.url.query, "utf-8")
        return httpx.Response(200, json={"data": {"items": [], "next_cursor": None}})

    client = _client(handler)
    await client.search_features(
        q="광안리",
        min_lon=129.0,
        min_lat=35.0,
        max_lon=129.2,
        max_lat=35.2,
        page_size=20,
    )
    assert seen["path"] == "/v1/features/search"
    # ADR-048 clean cut: bbox는 분리 float 4개, pagination은 page_size.
    for token in ("min_lon=129", "min_lat=35", "max_lon=129.2", "max_lat=35.2", "page_size=20"):
        assert token in seen["query"], seen["query"]
    assert "bbox=" not in seen["query"]
    await client.aclose()


async def test_get_feature_404_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "FEATURE_NOT_FOUND"}})

    client = _client(handler)
    assert await client.get_feature("f_x") is None
    await client.aclose()


async def test_get_feature_returns_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"feature_id": "f_x", "name": "광안리"}})

    client = _client(handler)
    feature = await client.get_feature("f_x")
    assert feature is not None
    assert feature["name"] == "광안리"
    await client.aclose()


async def test_get_features_chunks_and_merges() -> None:
    calls: list[list[str]] = []

    seen_path: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        seen_path["path"] = request.url.path
        body = _json.loads(request.content)
        ids = body["feature_ids"]
        calls.append(ids)
        items = {fid: {"feature_id": fid} for fid in ids if fid != "f_missing"}
        missing = [fid for fid in ids if fid == "f_missing"]
        return httpx.Response(200, json={"data": {"items": items, "missing": missing}})

    client = _client(handler, batch_chunk_size=2)
    data = await client.get_features(["f_1", "f_2", "f_missing"])
    assert seen_path["path"] == "/v1/features/batch"  # #318: /tripmate 제거
    assert len(calls) == 2  # 2 + 1 청크
    assert set(data["items"]) == {"f_1", "f_2"}
    assert data["missing"] == ["f_missing"]
    await client.aclose()


async def test_5xx_retries_then_unavailable() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503, json={"error": {"code": "UPSTREAM_UNAVAILABLE"}})

    client = _client(handler, max_attempts=3)
    with pytest.raises(KrtourMapUnavailable):
        await client.get_feature("f_x")
    assert attempts["n"] == 3
    await client.aclose()


async def test_transport_error_raises_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = _client(handler)
    with pytest.raises(KrtourMapUnavailable):
        await client.healthz()
    await client.aclose()


async def test_rate_limited_429_with_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, headers={"Retry-After": "15"}, json={"error": {"code": "RATE_LIMITED"}}
        )

    client = _client(handler)
    with pytest.raises(KrtourMapRateLimited) as exc:
        await client.features_in_bounds(min_lon=129.0, min_lat=35.0, max_lon=129.2, max_lat=35.2)
    assert exc.value.retry_after_seconds == 15
    await client.aclose()


async def test_422_raises_bad_request_with_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": {"code": "INVALID_BBOX"}})

    client = _client(handler)
    with pytest.raises(KrtourMapBadRequest) as exc:
        await client.features_in_bounds(min_lon=129.0, min_lat=35.0, max_lon=129.2, max_lat=35.2)
    assert exc.value.code == "INVALID_BBOX"
    await client.aclose()


async def test_batch_404_path_raises_not_found() -> None:
    # batch는 get_feature와 달리 404를 도메인 예외로 올린다(셰입 보장).
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "FEATURE_NOT_FOUND"}})

    client = _client(handler)
    with pytest.raises(KrtourMapFeatureNotFound):
        await client.get_features(["f_1"])
    await client.aclose()


async def test_service_token_header() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["token"] = request.headers.get("X-Krtour-Service-Token")
        return httpx.Response(200, json={"data": {"count": 0, "items": []}})

    with_token = _client(handler, service_token="secret-abc")
    await with_token.features_in_bounds(min_lon=129.0, min_lat=35.0, max_lon=129.2, max_lat=35.2)
    assert seen["token"] == "secret-abc"
    await with_token.aclose()

    without = _client(handler)
    await without.features_in_bounds(min_lon=129.0, min_lat=35.0, max_lon=129.2, max_lat=35.2)
    assert seen["token"] is None
    await without.aclose()
