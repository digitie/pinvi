"""kor-travel-map admin HTTP client 계약 테스트 (httpx.MockTransport)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapFeatureNotFound,
    KorTravelMapUnavailable,
)
from app.clients.kor_travel_map_admin import KorTravelMapAdminClient

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler, **kwargs: object) -> KorTravelMapAdminClient:
    http = httpx.AsyncClient(
        base_url="http://kor_travel_map-admin.test",
        transport=httpx.MockTransport(handler),
    )
    params: dict[str, object] = {
        "max_attempts": 2,
        "backoff_base_seconds": 0.0,
        "service_token": "svc-tok",
    }
    params.update(kwargs)
    return KorTravelMapAdminClient(http, **params)  # type: ignore[arg-type]


def _change_response(*, action: str = "create", state: str = "pending") -> dict[str, Any]:
    return {
        "data": {
            "request": {
                "feature_id": "f_x",
                "request_id": "req-1",
                "action": action,
                "status": state,
                "review_mode": "require_review",
                "payload": {},
                "created_at": "2026-06-11T00:00:00+09:00",
            }
        },
        "meta": {},
    }


async def test_create_feature_posts_with_token_and_returns_record() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["token"] = request.headers.get("X-Kor-Travel-Map-Service-Token", "")
        return httpx.Response(201, json=_change_response(action="create"))

    client = _client(handler)
    record = await client.create_feature(
        {
            "kind": "place",
            "name": "새 장소",
            "category": "01070100",
            "marker_color": "P-13",
            "marker_icon": "marker",
            "reason": "user suggestion 123",
        }
    )
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/admin/features"
    assert seen["token"] == "svc-tok"
    assert record["request_id"] == "req-1"
    assert record["action"] == "create"
    await client.aclose()


async def test_patch_feature_targets_feature_id() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(200, json=_change_response(action="update"))

    client = _client(handler)
    record = await client.patch_feature("f_abc", {"name": "수정", "reason": "correction"})
    assert seen["method"] == "PATCH"
    assert seen["path"] == "/v1/admin/features/f_abc"
    assert record["action"] == "update"
    await client.aclose()


async def test_delete_feature_sends_reason_and_operator_body() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_change_response(action="delete"))

    client = _client(handler)
    record = await client.delete_feature("f_abc", reason="영구 폐업", operator="tm-admin")
    assert seen["method"] == "DELETE"
    assert seen["path"] == "/v1/admin/features/f_abc"
    assert seen["body"] == {"reason": "영구 폐업", "operator": "tm-admin"}
    assert record["action"] == "delete"
    await client.aclose()


async def test_approve_change_request_hits_action_subresource() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json=_change_response(state="applied"))

    client = _client(handler)
    record = await client.approve_change_request("req-9", operator="tm-admin", reason="ok")
    assert seen["path"] == "/v1/admin/features/change-requests/req-9/approve"
    assert record["status"] == "applied"
    await client.aclose()


async def test_404_maps_to_feature_not_found() -> None:
    client = _client(
        lambda r: httpx.Response(404, json={"code": "FEATURE_NOT_FOUND", "status": 404})
    )
    with pytest.raises(KorTravelMapFeatureNotFound):
        await client.patch_feature("f_x", {"reason": "x"})
    await client.aclose()


async def test_422_maps_to_bad_request_with_code() -> None:
    client = _client(
        lambda r: httpx.Response(422, json={"code": "VALIDATION_ERROR", "status": 422})
    )
    with pytest.raises(KorTravelMapBadRequest) as exc_info:
        await client.create_feature({"reason": "x"})
    assert exc_info.value.code == "VALIDATION_ERROR"
    await client.aclose()


async def test_5xx_retries_then_raises_unavailable() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={})

    client = _client(handler)  # max_attempts=2
    with pytest.raises(KorTravelMapUnavailable):
        await client.create_feature({"reason": "x"})
    assert calls["n"] == 2
    await client.aclose()
