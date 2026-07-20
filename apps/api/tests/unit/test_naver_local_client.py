"""Naver Local client 계약 테스트 (httpx.MockTransport) — ADR-054."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.clients.naver_local import NaverLocalClient, NaverLocalUnavailable

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler, **kwargs: object) -> NaverLocalClient:
    http = httpx.AsyncClient(
        base_url="http://openapi.naver.test",
        transport=httpx.MockTransport(handler),
    )
    params: dict[str, object] = {
        "client_id": "test-id",
        "client_secret": "test-secret",
        "max_attempts": 2,
        "backoff_base_seconds": 0.0,
    }
    params.update(kwargs)
    return NaverLocalClient(http, **params)  # type: ignore[arg-type]


async def test_search_local_sends_headers_and_clamps_display() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["id"] = request.headers.get("X-Naver-Client-Id")
        seen["secret"] = request.headers.get("X-Naver-Client-Secret")
        seen["display"] = request.url.params.get("display")
        return httpx.Response(200, json={"items": [{"title": "<b>경복궁</b>"}]})

    client = _client(handler)
    data = await client.search_local(query="경복궁", display=20)
    assert seen["path"] == "/v1/search/local.json"
    assert seen["id"] == "test-id"
    assert seen["secret"] == "test-secret"
    assert seen["display"] == "5"  # Naver 상한 5로 clamp
    assert data["items"][0]["title"] == "<b>경복궁</b>"
    await client.aclose()


async def test_missing_credential_raises_unavailable() -> None:
    client = _client(lambda r: httpx.Response(200, json={}), client_secret="")
    with pytest.raises(NaverLocalUnavailable):
        await client.search_local(query="x", display=5)
    await client.aclose()


async def test_4xx_fails_immediately() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"errorMessage": "quota"})

    client = _client(handler)
    with pytest.raises(NaverLocalUnavailable):
        await client.search_local(query="x", display=5)
    assert calls["n"] == 1
    await client.aclose()
