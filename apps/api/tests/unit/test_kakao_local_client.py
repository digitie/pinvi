"""Kakao Local client 계약 테스트 (httpx.MockTransport) — ADR-054."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.clients.kakao_local import KakaoLocalClient, KakaoLocalUnavailable

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler, **kwargs: object) -> KakaoLocalClient:
    http = httpx.AsyncClient(
        base_url="http://dapi.kakao.test",
        transport=httpx.MockTransport(handler),
    )
    params: dict[str, object] = {
        "rest_api_key": "test-kakao-key",
        "max_attempts": 2,
        "backoff_base_seconds": 0.0,
    }
    params.update(kwargs)
    return KakaoLocalClient(http, **params)  # type: ignore[arg-type]


async def test_search_keyword_sends_auth_header_and_query() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("Authorization")
        seen["query"] = request.url.params.get("query")
        seen["x"] = request.url.params.get("x")
        return httpx.Response(200, json={"documents": [{"id": "1", "place_name": "카페"}]})

    client = _client(handler)
    data = await client.search_keyword(query="카페", size=8)
    assert seen["path"] == "/v2/local/search/keyword.json"
    assert seen["auth"] == "KakaoAK test-kakao-key"
    assert seen["query"] == "카페"
    assert seen["x"] is None  # 좌표 미전달(내 주변 아님)
    assert data["documents"][0]["place_name"] == "카페"
    await client.aclose()


async def test_search_keyword_passes_coord_when_near_me() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["x"] = request.url.params.get("x")
        seen["y"] = request.url.params.get("y")
        seen["sort"] = request.url.params.get("sort")
        return httpx.Response(200, json={"documents": []})

    client = _client(handler)
    await client.search_keyword(query="카페", size=5, x=127.0, y=37.5, radius=1000)
    assert seen["x"] == "127.0"
    assert seen["y"] == "37.5"
    assert seen["sort"] == "distance"
    await client.aclose()


async def test_missing_key_raises_unavailable() -> None:
    client = _client(lambda r: httpx.Response(200, json={}), rest_api_key="")
    with pytest.raises(KakaoLocalUnavailable):
        await client.search_keyword(query="x", size=5)
    await client.aclose()


async def test_4xx_fails_immediately_without_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"message": "invalid key"})

    client = _client(handler)
    with pytest.raises(KakaoLocalUnavailable):
        await client.search_keyword(query="x", size=5)
    assert calls["n"] == 1  # 4xx는 재시도하지 않음
    await client.aclose()


async def test_5xx_retries_then_fails() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={})

    client = _client(handler, max_attempts=2)
    with pytest.raises(KakaoLocalUnavailable):
        await client.search_keyword(query="x", size=5)
    assert calls["n"] == 2  # 5xx는 max_attempts만큼 재시도
    await client.aclose()
