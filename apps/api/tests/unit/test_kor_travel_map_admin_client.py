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


async def test_admin_proxy_headers_are_sent_when_configured() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["proxy_secret"] = request.headers.get("X-Kor-Travel-Map-Admin-Proxy-Secret", "")
        seen["actor"] = request.headers.get("X-Kor-Travel-Map-Actor", "")
        return httpx.Response(201, json=_change_response(action="create"))

    client = _client(
        handler,
        admin_proxy_secret="proxy-secret",
        admin_actor="pinvi-operator",
    )
    await client.create_feature({"reason": "x"})
    assert seen == {"proxy_secret": "proxy-secret", "actor": "pinvi-operator"}
    await client.aclose()


async def test_list_features_uses_admin_read_path_filters_and_returns_payload() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["query"] = list(request.url.params.multi_items())
        return httpx.Response(
            200,
            json={
                "data": {
                    "items": [
                        {
                            "feature_id": "f_1",
                            "kind": "place",
                            "name": "해운대 카페",
                            "category": "01070100",
                            "status": "active",
                            "lon": 129.16,
                            "lat": 35.16,
                            "address_label": "부산",
                            "primary_provider": "visitkorea",
                            "primary_dataset_key": "places",
                            "issue_count": 0,
                            "issues": [],
                            "created_at": "2026-06-11T00:00:00+09:00",
                            "updated_at": "2026-06-12T00:00:00+09:00",
                        }
                    ]
                },
                "meta": {"page": {"next_cursor": "next-1"}, "duration_ms": 12},
            },
        )

    client = _client(handler)
    payload = await client.list_features(
        q="해운대",
        kinds=["place", "event"],
        categories=["01070100"],
        statuses=["active"],
        providers=["visitkorea"],
        dataset_keys=["places"],
        has_coord=True,
        has_issue=False,
        issue_types=["missing_coord"],
        page_size=100,
        cursor="cur-1",
        sort="updated_at",
        order="desc",
    )
    assert seen["method"] == "GET"
    assert seen["path"] == "/v1/admin/features"
    assert ("kind", "place") in seen["query"]
    assert ("kind", "event") in seen["query"]
    assert ("provider", "visitkorea") in seen["query"]
    assert ("dataset_key", "places") in seen["query"]
    assert ("has_coord", "true") in seen["query"]
    assert ("has_issue", "false") in seen["query"]
    assert ("sort", "updated_at") in seen["query"]
    assert payload["data"]["items"][0]["feature_id"] == "f_1"
    assert payload["meta"]["page"]["next_cursor"] == "next-1"
    await client.aclose()


async def test_get_feature_detail_uses_admin_detail_path() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(
            200,
            json={
                "data": {
                    "feature": {
                        "feature_id": "f_1",
                        "kind": "place",
                        "name": "해운대 카페",
                        "category": "01070100",
                        "status": "active",
                        "address": {},
                        "detail": {},
                        "urls": {},
                        "raw_refs": [],
                        "created_at": "2026-06-11T00:00:00+09:00",
                        "updated_at": "2026-06-12T00:00:00+09:00",
                    },
                    "sources": [],
                    "issues": [],
                    "overrides": [],
                    "versions": [],
                    "change_requests": [],
                    "files": [],
                },
                "meta": {},
            },
        )

    client = _client(handler)
    data = await client.get_feature_detail("f_1")
    assert seen["method"] == "GET"
    assert seen["path"] == "/v1/admin/features/f_1"
    assert data["feature"]["feature_id"] == "f_1"
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


async def test_curated_detail_snapshot_uses_admin_path_and_token() -> None:
    """ADR-049: 큐레이션 import snapshot은 admin detail-snapshot 표면(서비스 토큰)에서 온다."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["token"] = request.headers.get("X-Kor-Travel-Map-Service-Token", "")
        return httpx.Response(
            200,
            json={
                "data": {
                    "curated_feature_id": "cf_1",
                    "version": 3,
                    "etag": "sha256:abc",
                    "updated_at": "2026-06-12T00:00:00+09:00",
                    "theme": {},
                    "content": {"title": "부산 코스"},
                    "source": {},
                    "items": [],
                },
                "meta": {},
            },
        )

    client = _client(handler)
    snapshot = await client.get_curated_detail_snapshot("cf_1")
    assert seen["method"] == "GET"
    assert seen["path"] == "/v1/admin/curated-features/cf_1/detail-snapshot"
    assert seen["token"] == "svc-tok"
    assert snapshot["curated_feature_id"] == "cf_1"
    assert snapshot["content"] == {"title": "부산 코스"}
    await client.aclose()
