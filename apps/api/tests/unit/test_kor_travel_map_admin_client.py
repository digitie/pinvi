"""kor-travel-map admin HTTP client 계약 테스트 (httpx.MockTransport)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.api.v1.admin.ops_proxy import retry_after_headers
from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapConflict,
    KorTravelMapError,
    KorTravelMapFeatureNotFound,
    KorTravelMapPreconditionFailed,
    KorTravelMapUnavailable,
)
from app.clients.kor_travel_map_admin import KorTravelMapAdminClient

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.mark.parametrize("seconds", [1, 300])
def test_ops_proxy_relays_canonical_retry_after(seconds: int) -> None:
    assert retry_after_headers(seconds) == {"Retry-After": str(seconds)}


@pytest.mark.parametrize("seconds", [None, 0, -1, 301, True])
def test_ops_proxy_drops_noncanonical_retry_after(seconds: int | None) -> None:
    assert retry_after_headers(seconds) is None


def _client(handler: Handler, **kwargs: object) -> KorTravelMapAdminClient:
    http = httpx.AsyncClient(
        base_url="http://kor_travel_map-admin.test",
        transport=httpx.MockTransport(handler),
    )
    params: dict[str, object] = {
        "max_attempts": 2,
        "backoff_base_seconds": 0.0,
        "service_token": "svc-tok",
        "ops_read_token": "ops-read-tok",
        "ops_cancel_token": "ops-cancel-tok",
    }
    params.update(kwargs)
    return KorTravelMapAdminClient(http, **params)  # type: ignore[arg-type]


def _ops_meta(request_id: str = "") -> dict[str, object]:
    return {"duration_ms": 1, "request_id": request_id}


def _typed_cancellation_detail() -> dict[str, object]:
    error = {
        "code": "DAGSTER_UNAVAILABLE",
        "message": "Dagster is unavailable",
        "details": {"token": "must-not-leak"},
    }
    return {
        "cancellation_id": "22222222-2222-4222-8222-222222222222",
        "previous_cancellation_id": None,
        "root": {
            "kind": "import_job",
            "id": "11111111-1111-4111-8111-111111111111",
        },
        "status": "retryable",
        "requested_at": "2026-06-12T00:00:00+09:00",
        "requested_by": "service:pinvi",
        "reason": "operator request",
        "error": error,
        "updated_at": "2026-06-12T00:01:00+09:00",
        "finished_at": "2026-06-12T00:01:00+09:00",
        "retryable": True,
        "unresolved_member_count": 1,
        "members": [
            {
                "job_id": "11111111-1111-4111-8111-111111111111",
                "dagster_run_id": "run-1",
                "operation_kind": "provider_import",
                "requires_run_termination": True,
                "initial_status": "running",
                "result": "cancel_failed",
                "terminal_status": None,
                "error": error,
                "updated_at": "2026-06-12T00:01:00+09:00",
            }
        ],
        "dagster_runs": [
            {
                "dagster_run_id": "run-1",
                "initial_status": "STARTED",
                "termination_reserved_at": "2026-06-12T00:00:30+09:00",
                "result": "cancel_failed",
                "terminal_status": None,
                "error": error,
                "engine_started_at": None,
                "engine_finished_at": None,
                "updated_at": "2026-06-12T00:01:00+09:00",
            }
        ],
        "committed_data_rolled_back": False,
        "warnings": ["committed data is retained"],
    }


def _typed_cancellation_detail_for_code(code: str) -> dict[str, object]:
    details = _typed_cancellation_detail()
    if code == "PIPELINE_CANCELLATION_IN_PROGRESS":
        details.update(
            {
                "status": "in_progress",
                "retryable": False,
                "error": None,
                "finished_at": None,
            }
        )
    elif code == "PIPELINE_CANCELLATION_UNSAFE":
        details.update(
            {
                "status": "failed",
                "retryable": False,
                "error": {
                    "code": code,
                    "message": "cancellation invariant failed",
                    "details": {},
                },
            }
        )
    else:
        error = details["error"]
        assert isinstance(error, dict)
        error["code"] = code
    return details


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


async def test_request_id_header_is_sent_from_per_request_wrapper() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request_id"] = request.headers.get("X-Request-Id", "")
        seen["token"] = request.headers.get("X-Kor-Travel-Map-Service-Token", "")
        return httpx.Response(200, json={"data": {"items": []}, "meta": {}})

    client = _client(handler)
    scoped = client.with_request_id("00000000-0000-4000-8000-000000000123")
    await scoped.list_system_logs(page_size=10)
    assert seen == {
        "request_id": "00000000-0000-4000-8000-000000000123",
        "token": "svc-tok",
    }
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
    seen: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers.get("If-Match")))
        if request.method == "GET":
            return httpx.Response(
                200,
                headers={"ETag": '"7"'},
                json={"data": {"feature_id": "f_abc", "row_revision": 7}},
            )
        return httpx.Response(200, json=_change_response(action="update"))

    client = _client(handler)
    record = await client.patch_feature("f_abc", {"name": "수정", "reason": "correction"})
    assert seen == [
        ("GET", "/v1/admin/features/f_abc/revision", None),
        ("PATCH", "/v1/admin/features/f_abc", '"7"'),
    ]
    assert record["action"] == "update"
    await client.aclose()


async def test_delete_feature_sends_reason_and_operator_body() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                headers={"ETag": '"9"'},
                json={"data": {"feature_id": "f_abc", "row_revision": 9}},
            )
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        seen["if_match"] = request.headers.get("If-Match")
        return httpx.Response(200, json=_change_response(action="delete"))

    client = _client(handler)
    record = await client.delete_feature("f_abc", reason="영구 폐업", operator="tm-admin")
    assert seen["method"] == "DELETE"
    assert seen["path"] == "/v1/admin/features/f_abc"
    assert seen["body"] == {"reason": "영구 폐업", "operator": "tm-admin"}
    assert seen["if_match"] == '"9"'
    assert record["action"] == "delete"
    await client.aclose()


async def test_patch_feature_rejects_revision_response_without_canonical_etag() -> None:
    client = _client(
        lambda _request: httpx.Response(
            200,
            headers={"ETag": "7"},
            json={"data": {"feature_id": "f_abc", "row_revision": 7}},
        )
    )
    with pytest.raises(KorTravelMapError, match="canonical ETag"):
        await client.patch_feature("f_abc", {"reason": "correction"})
    await client.aclose()


async def test_approve_change_request_hits_action_subresource() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_change_response(state="applied"))

    client = _client(handler)
    record = await client.approve_change_request("req-9", operator="tm-admin", reason="ok")
    assert seen["path"] == "/v1/admin/features/change-requests/req-9/approve"
    assert seen["body"] == {"operator": "tm-admin", "reason": "ok"}
    assert record["status"] == "applied"
    await client.aclose()


async def test_list_change_requests_forwards_filters() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = list(request.url.params.multi_items())
        return httpx.Response(
            200,
            json={
                "data": {
                    "items": [
                        {
                            "feature_id": "f_x",
                            "request_id": "req-1",
                            "action": "add",
                            "status": "pending",
                            "review_mode": "require_review",
                            "payload": {},
                            "created_at": "2026-06-11T00:00:00+09:00",
                        }
                    ],
                    "review_mode": "require_review",
                },
                "meta": {},
            },
        )

    client = _client(handler)
    data = await client.list_change_requests(
        statuses=["pending", "applied"],
        actions=["add"],
        q="해운대",
        page_size=25,
    )
    assert seen["path"] == "/v1/admin/features/change-requests"
    assert ("status", "pending") in seen["query"]
    assert ("status", "applied") in seen["query"]
    assert ("action", "add") in seen["query"]
    assert ("q", "해운대") in seen["query"]
    assert ("page_size", "25") in seen["query"]
    assert data["items"][0]["request_id"] == "req-1"
    await client.aclose()


async def test_reject_change_request_hits_action_subresource() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_change_response(action="update", state="rejected"))

    client = _client(handler)
    record = await client.reject_change_request("req-10", operator="tm-admin", reason="dup")
    assert seen["path"] == "/v1/admin/features/change-requests/req-10/reject"
    assert seen["body"] == {"operator": "tm-admin", "reason": "dup"}
    assert record["status"] == "rejected"
    await client.aclose()


async def test_409_non_lock_busy_maps_to_conflict() -> None:
    client = _client(lambda r: httpx.Response(409, json={"code": "INVALID_STATE", "status": 409}))
    with pytest.raises(KorTravelMapConflict) as exc_info:
        await client.approve_change_request("req-1", operator="tm-admin", reason="ok")
    assert exc_info.value.code == "INVALID_STATE"
    await client.aclose()


async def test_409_lock_busy_keeps_conflict_code_and_retry_after() -> None:
    client = _client(
        lambda r: httpx.Response(
            409,
            headers={"Retry-After": "11"},
            json={"code": "LOCK_BUSY", "status": 409},
        )
    )
    with pytest.raises(KorTravelMapConflict) as exc_info:
        await client.approve_change_request("req-1", operator="tm-admin", reason="ok")
    assert exc_info.value.code == "LOCK_BUSY"
    assert exc_info.value.retry_after_seconds == 11
    await client.aclose()


async def test_412_maps_to_precondition_failed() -> None:
    client = _client(
        lambda _request: httpx.Response(
            412,
            json={"code": "PRECONDITION_FAILED", "status": 412},
        )
    )
    with pytest.raises(KorTravelMapPreconditionFailed) as exc_info:
        await client.approve_change_request("req-1", operator="tm-admin", reason="ok")
    assert exc_info.value.code == "PRECONDITION_FAILED"
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


async def test_ops_pipeline_overview_uses_read_principal_only() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = list(request.url.params.multi_items())
        seen["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "data": {
                    "checked_at": "2026-06-12T00:00:00+09:00",
                    "dagster": {
                        "status": "ok",
                        "schedule_count": 1,
                        "sensor_count": 0,
                        "run_counts": {"STARTED": 1},
                        "recent_runs": [],
                    },
                    "operations_by_status": {"running": 1},
                    "active_operations": 1,
                    "failed_operations_24h": 0,
                },
                "meta": _ops_meta("00000000-0000-4000-8000-000000000123"),
            },
        )

    client = _client(handler, admin_proxy_secret="must-not-leak")
    scoped = client.with_request_id("00000000-0000-4000-8000-000000000123")
    data = await scoped.get_ops_pipeline_overview(run_limit=7)
    assert seen["path"] == "/v1/ops/pipeline/overview"
    assert seen["query"] == [("run_limit", "7")]
    assert seen["headers"]["x-kor-travel-map-ops-token"] == "ops-read-tok"
    assert seen["headers"]["x-kor-travel-map-ops-scope"] == "ops:read"
    assert seen["headers"]["x-request-id"] == "00000000-0000-4000-8000-000000000123"
    assert "x-kor-travel-map-admin-proxy-secret" not in seen["headers"]
    assert "x-kor-travel-map-actor" not in seen["headers"]
    assert "x-kor-travel-map-service-token" not in seen["headers"]
    assert data["dagster"]["schedule_count"] == 1
    await client.aclose()


@pytest.mark.parametrize(
    "meta",
    [
        {},
        {"duration_ms": 1},
        {"duration_ms": -1, "request_id": "request-1"},
        {"duration_ms": True, "request_id": "request-1"},
        {"duration_ms": 1, "request_id": "different-request"},
    ],
)
async def test_ops_success_rejects_missing_or_unrelated_meta(
    meta: dict[str, object],
) -> None:
    client = _client(
        lambda _request: httpx.Response(200, json={"data": {}, "meta": meta})
    ).with_request_id("request-1")

    with pytest.raises(KorTravelMapError, match="meta"):
        await client.get_ops_pipeline_overview()

    await client.aclose()


async def test_list_ops_datasets_uses_canonical_grid() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = list(request.url.params.multi_items())
        return httpx.Response(
            200,
            json={
                "data": {
                    "items": [
                        {
                            "provider": "kma",
                            "dataset_key": "special_days",
                            "sync_scope": "daily",
                            "status": "healthy",
                            "last_success_at": "2026-06-12T00:00:00+09:00",
                            "last_failure_at": None,
                            "consecutive_failures": 0,
                            "eligible_after": "2026-06-13T00:00:00+09:00",
                        }
                    ]
                },
                "meta": _ops_meta(),
            },
        )

    client = _client(handler)
    data = await client.list_ops_datasets()
    assert seen["path"] == "/v1/ops/datasets"
    assert seen["query"] == []
    assert data["items"][0]["provider"] == "kma"
    await client.aclose()


async def test_list_ops_pipeline_executions_pins_import_job_kind() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = list(request.url.params.multi_items())
        return httpx.Response(
            200,
            json={
                "data": {
                    "items": [
                        {
                            "id": "11111111-1111-4111-8111-111111111111",
                            "kind": "import_job",
                            "status": "running",
                            "progress": 0.25,
                            "created_at": "2026-06-12T00:00:00+09:00",
                            "detail_url": (
                                "/v1/ops/pipeline/executions/import_job/"
                                "11111111-1111-4111-8111-111111111111"
                            ),
                            "projected_job": {"job_kind": "provider_import"},
                        }
                    ]
                },
                "meta": {
                    **_ops_meta(),
                    "page": {"next_cursor": "cursor-2"},
                },
            },
        )

    client = _client(handler)
    payload = await client.list_ops_pipeline_executions(
        status_filter="running",
        load_batch_id="22222222-2222-4222-8222-222222222222",
        page_size=25,
        cursor="cursor-1",
    )
    assert seen["path"] == "/v1/ops/pipeline/executions"
    assert ("status", "running") in seen["query"]
    assert ("kind", "import_job") in seen["query"]
    assert ("load_batch_id", "22222222-2222-4222-8222-222222222222") in seen["query"]
    assert ("page_size", "25") in seen["query"]
    assert ("cursor", "cursor-1") in seen["query"]
    assert payload["data"]["items"][0]["status"] == "running"
    assert payload["meta"]["page"]["next_cursor"] == "cursor-2"
    await client.aclose()


async def test_cancel_ops_pipeline_execution_uses_cancel_principal() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["json"] = json.loads(request.content)
        seen["scope"] = request.headers.get("X-Kor-Travel-Map-Ops-Scope")
        seen["token"] = request.headers.get("X-Kor-Travel-Map-Ops-Token")
        seen["request_id"] = request.headers.get("X-Request-Id")
        return httpx.Response(
            200,
            json={
                "data": {
                    "cancellation_id": "22222222-2222-4222-8222-222222222222",
                    "root": {
                        "kind": "import_job",
                        "id": "11111111-1111-4111-8111-111111111111",
                    },
                    "status": "completed",
                },
                "meta": _ops_meta("00000000-0000-4000-8000-000000000321"),
            },
        )

    client = _client(handler)
    scoped = client.with_request_id("00000000-0000-4000-8000-000000000321")
    data = await scoped.cancel_ops_pipeline_execution(
        "11111111-1111-4111-8111-111111111111",
        reason="duplicate run",
    )
    assert seen["method"] == "POST"
    assert seen["path"] == (
        "/v1/ops/pipeline/executions/import_job/11111111-1111-4111-8111-111111111111/cancel"
    )
    assert seen["json"] == {"reason": "duplicate run"}
    assert seen["scope"] == "ops:cancel"
    assert seen["token"] == "ops-cancel-tok"
    assert seen["request_id"] == "00000000-0000-4000-8000-000000000321"
    assert data["status"] == "completed"
    await client.aclose()


async def test_get_ops_pipeline_execution_uses_read_principal_for_reconciliation() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["scope"] = request.headers.get("X-Kor-Travel-Map-Ops-Scope")
        seen["token"] = request.headers.get("X-Kor-Travel-Map-Ops-Token")
        return httpx.Response(
            200,
            json={
                "data": {
                    "execution": {
                        "id": "11111111-1111-4111-8111-111111111111",
                        "kind": "import_job",
                        "status": "cancelled",
                    },
                    "root": {"kind": "import_job"},
                    "import_job": {"job_id": "11111111-1111-4111-8111-111111111111"},
                    "update_request": None,
                    "cancellation": {"status": "completed", "retryable": False},
                    "events": [],
                    "events_next_cursor": None,
                },
                "meta": _ops_meta(),
            },
        )

    client = _client(handler)
    data = await client.get_ops_pipeline_execution("11111111-1111-4111-8111-111111111111")
    assert seen == {
        "method": "GET",
        "path": ("/v1/ops/pipeline/executions/import_job/11111111-1111-4111-8111-111111111111"),
        "scope": "ops:read",
        "token": "ops-read-tok",
    }
    assert data["cancellation"] == {"status": "completed", "retryable": False}
    await client.aclose()


@pytest.mark.parametrize(
    ("status_code", "code", "error_type"),
    [
        (409, "PIPELINE_CANCELLATION_IN_PROGRESS", KorTravelMapConflict),
        (409, "PIPELINE_CANCELLATION_UNSAFE", KorTravelMapConflict),
        (502, "DAGSTER_TERMINATE_FAILED", KorTravelMapUnavailable),
        (503, "DAGSTER_UNAVAILABLE", KorTravelMapUnavailable),
        (503, "DAGSTER_TERMINATION_TIMEOUT", KorTravelMapUnavailable),
    ],
)
async def test_cancel_ops_pipeline_execution_preserves_typed_problem(
    status_code: int,
    code: str,
    error_type: type[Exception],
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            status_code,
            headers=({} if code == "PIPELINE_CANCELLATION_UNSAFE" else {"Retry-After": "7"}),
            json={
                "code": code,
                "details": _typed_cancellation_detail_for_code(code),
            },
        )

    client = _client(handler)
    with pytest.raises(error_type) as exc:
        await client.cancel_ops_pipeline_execution(
            "11111111-1111-4111-8111-111111111111",
            reason="typed failure must not duplicate cancellation",
        )
    assert calls == 1
    assert exc.value.code == code
    assert exc.value.retry_after_seconds == (None if code == "PIPELINE_CANCELLATION_UNSAFE" else 7)
    if isinstance(exc.value, KorTravelMapUnavailable):
        assert exc.value.status_code == status_code
    details = exc.value.details
    expected = _typed_cancellation_detail_for_code(code)
    expected["members"][0]["error"]["details"]["token"] = "***"  # type: ignore[index]
    assert details == expected
    assert details["previous_cancellation_id"] is None
    assert details["requested_at"] == "2026-06-12T00:00:00+09:00"
    assert details["dagster_runs"][0]["dagster_run_id"] == "run-1"
    assert details["committed_data_rolled_back"] is False
    await client.aclose()


@pytest.mark.parametrize(
    ("status_code", "outer_code", "detail_code"),
    [
        (502, "DAGSTER_TERMINATE_FAILED", "DAGSTER_UNAVAILABLE"),
        (503, "DAGSTER_UNAVAILABLE", "DAGSTER_TERMINATION_TIMEOUT"),
        (503, "DAGSTER_TERMINATION_TIMEOUT", "DAGSTER_UNAVAILABLE"),
        (503, "DAGSTER_UNAVAILABLE", "PIPELINE_CANCELLATION_UNSAFE"),
    ],
)
async def test_cancel_ops_pipeline_execution_rejects_mixed_typed_failure_evidence(
    status_code: int,
    outer_code: str,
    detail_code: str,
) -> None:
    client = _client(
        lambda _request: httpx.Response(
            status_code,
            headers={"Retry-After": "7"},
            json={
                "code": outer_code,
                "details": _typed_cancellation_detail_for_code(detail_code),
            },
        )
    )

    with pytest.raises(KorTravelMapUnavailable) as exc:
        await client.cancel_ops_pipeline_execution(
            "11111111-1111-4111-8111-111111111111",
            reason="outer and durable attempt evidence must match",
        )

    assert exc.value.code == "PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN"
    await client.aclose()


@pytest.mark.parametrize(
    ("status_code", "code"),
    [
        (409, "PIPELINE_CANCELLATION_IN_PROGRESS"),
        (502, "DAGSTER_TERMINATE_FAILED"),
        (503, "DAGSTER_UNAVAILABLE"),
        (503, "DAGSTER_TERMINATION_TIMEOUT"),
    ],
)
@pytest.mark.parametrize(
    "raw_retry_after",
    [None, "", "0", "-1", "301", "7junk", "7 ", " 7", "\uff17"],
)
async def test_cancel_ops_pipeline_execution_rejects_invalid_required_retry_after(
    status_code: int,
    code: str,
    raw_retry_after: str | None,
) -> None:
    client = _client(
        lambda _request: httpx.Response(
            status_code,
            headers=(
                []
                if raw_retry_after is None
                else [(b"Retry-After", raw_retry_after.encode("utf-8"))]
            ),
            json={
                "code": code,
                "details": _typed_cancellation_detail_for_code(code),
            },
        )
    )

    with pytest.raises(KorTravelMapUnavailable) as exc:
        await client.cancel_ops_pipeline_execution(
            "11111111-1111-4111-8111-111111111111",
            reason="invalid retry delay must reconcile",
        )

    assert exc.value.code == "PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN"
    await client.aclose()


@pytest.mark.parametrize("raw_retry_after", ["", "7", "garbage"])
async def test_cancel_ops_pipeline_execution_rejects_unsafe_retry_after_presence(
    raw_retry_after: str,
) -> None:
    client = _client(
        lambda _request: httpx.Response(
            409,
            headers={"Retry-After": raw_retry_after},
            json={
                "code": "PIPELINE_CANCELLATION_UNSAFE",
                "details": _typed_cancellation_detail_for_code("PIPELINE_CANCELLATION_UNSAFE"),
            },
        )
    )

    with pytest.raises(KorTravelMapUnavailable) as exc:
        await client.cancel_ops_pipeline_execution(
            "11111111-1111-4111-8111-111111111111",
            reason="definitive failure cannot advertise retry",
        )

    assert exc.value.code == "PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN"
    await client.aclose()


@pytest.mark.parametrize("raw_retry_after", ["1", "300"])
async def test_cancel_ops_pipeline_execution_accepts_retry_after_boundaries(
    raw_retry_after: str,
) -> None:
    client = _client(
        lambda _request: httpx.Response(
            503,
            headers={"Retry-After": raw_retry_after},
            json={
                "code": "DAGSTER_UNAVAILABLE",
                "details": _typed_cancellation_detail_for_code("DAGSTER_UNAVAILABLE"),
            },
        )
    )

    with pytest.raises(KorTravelMapUnavailable) as exc:
        await client.cancel_ops_pipeline_execution(
            "11111111-1111-4111-8111-111111111111",
            reason="canonical retry delay boundary",
        )

    assert exc.value.code == "DAGSTER_UNAVAILABLE"
    assert exc.value.retry_after_seconds == int(raw_retry_after)
    await client.aclose()


@pytest.mark.parametrize(
    ("code", "details"),
    [
        (
            "PIPELINE_CANCELLATION_IN_PROGRESS",
            {
                "root": {
                    "kind": "import_job",
                    "id": "11111111-1111-4111-8111-111111111111",
                },
                "cancellation": None,
            },
        ),
        (
            "PIPELINE_CANCELLATION_UNSAFE",
            {
                "root": {
                    "kind": "update_request",
                    "id": "22222222-2222-4222-8222-222222222222",
                },
                "cancellation": None,
            },
        ),
        ("PIPELINE_CANCELLATION_UNSAFE", None),
    ],
)
async def test_cancel_ops_pipeline_execution_preserves_typed_409_without_attempt(
    code: str,
    details: dict[str, object] | None,
) -> None:
    client = _client(
        lambda _request: httpx.Response(
            409,
            headers=({"Retry-After": "7"} if code == "PIPELINE_CANCELLATION_IN_PROGRESS" else {}),
            json={"code": code, "details": details},
        )
    )

    with pytest.raises(KorTravelMapConflict) as exc:
        await client.cancel_ops_pipeline_execution(
            "11111111-1111-4111-8111-111111111111",
            reason="canonical attempt-free conflict",
        )

    assert exc.value.code == code
    assert exc.value.details == details
    await client.aclose()


async def test_cancel_ops_pipeline_execution_preserves_typed_not_found_problem() -> None:
    client = _client(
        lambda _request: httpx.Response(
            404,
            json={
                "code": "PIPELINE_EXECUTION_NOT_FOUND",
                "details": {
                    "root": {
                        "kind": "import_job",
                        "id": "11111111-1111-4111-8111-111111111111",
                    },
                    "cancellation": None,
                },
            },
        )
    )

    with pytest.raises(KorTravelMapFeatureNotFound) as exc:
        await client.cancel_ops_pipeline_execution(
            "11111111-1111-4111-8111-111111111111",
            reason="missing execution",
        )

    assert exc.value.code == "PIPELINE_EXECUTION_NOT_FOUND"
    assert exc.value.details == {
        "root": {
            "kind": "import_job",
            "id": "11111111-1111-4111-8111-111111111111",
        },
        "cancellation": None,
    }
    await client.aclose()


async def test_cancel_ops_pipeline_execution_marks_transport_loss_uncertain() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("response lost after cancellation", request=request)

    client = _client(handler)
    with pytest.raises(KorTravelMapUnavailable) as exc:
        await client.cancel_ops_pipeline_execution(
            "11111111-1111-4111-8111-111111111111",
            reason="response loss must not duplicate cancellation",
        )
    assert calls == 1
    assert exc.value.code == "PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN"
    assert exc.value.details == {
        "outcome_certainty": "uncertain",
        "reconciliation": {
            "method": "GET",
            "path": ("/v1/ops/pipeline/executions/import_job/11111111-1111-4111-8111-111111111111"),
            "scope": "ops:read",
        },
    }
    await client.aclose()


@pytest.mark.parametrize(
    "response_factory",
    [
        pytest.param(
            lambda: httpx.Response(
                200,
                content=b"not-json",
                headers={"Content-Type": "application/json"},
            ),
            id="invalid-json",
        ),
        pytest.param(
            lambda: httpx.Response(200, json={"meta": {}}),
            id="missing-data-envelope",
        ),
        pytest.param(
            lambda: httpx.Response(200, json={"data": {"status": "completed"}}),
            id="missing-success-meta",
        ),
        pytest.param(
            lambda: httpx.Response(
                200,
                json={"data": {"status": "completed"}, "meta": None},
            ),
            id="null-success-meta",
        ),
        pytest.param(
            lambda: httpx.Response(
                200,
                json={"data": {"status": "completed"}, "meta": {}},
            ),
            id="missing-success-meta-duration",
        ),
        pytest.param(
            lambda: httpx.Response(
                500,
                json={"code": "INTERNAL_ERROR", "status": 500},
            ),
            id="unexpected-500",
        ),
        pytest.param(
            lambda: httpx.Response(
                502,
                json={"code": "ARBITRARY_BAD_GATEWAY", "status": 502},
            ),
            id="generic-502",
        ),
        pytest.param(
            lambda: httpx.Response(
                409,
                json={"code": "INVALID_STATE", "status": 409},
            ),
            id="generic-409",
        ),
        pytest.param(
            lambda: httpx.Response(
                409,
                json={"code": "LOCK_BUSY", "status": 409},
            ),
            id="non-cancellation-lock-busy-409",
        ),
        pytest.param(
            lambda: httpx.Response(
                409,
                json={"code": "PIPELINE_CANCELLATION_IN_PROGRESS", "status": 409},
            ),
            id="typed-409-without-detail",
        ),
        pytest.param(
            lambda: httpx.Response(
                503,
                json={
                    "code": "DAGSTER_UNAVAILABLE",
                    "status": 503,
                    "details": {"status": "retryable", "retryable": True},
                },
            ),
            id="typed-503-with-partial-detail",
        ),
        pytest.param(
            lambda: httpx.Response(
                409,
                json={
                    "code": "PIPELINE_CANCELLATION_UNSAFE",
                    "details": {
                        "root": {
                            "kind": "import_job",
                            "id": "11111111-1111-4111-8111-111111111111",
                        }
                    },
                },
            ),
            id="unsafe-409-with-malformed-root-only-detail",
        ),
        pytest.param(
            lambda: httpx.Response(
                404,
                json={"code": "ARBITRARY_NOT_FOUND", "status": 404},
            ),
            id="generic-404",
        ),
        pytest.param(
            lambda: httpx.Response(
                503,
                json={"code": "ARBITRARY_UNAVAILABLE", "status": 503},
            ),
            id="generic-503",
        ),
        pytest.param(
            lambda: httpx.Response(
                502,
                json={"code": "DAGSTER_UNAVAILABLE", "status": 502},
            ),
            id="known-code-wrong-502-pair",
        ),
        pytest.param(
            lambda: httpx.Response(
                503,
                json={"code": "DAGSTER_TERMINATE_FAILED", "status": 503},
            ),
            id="known-code-wrong-503-pair",
        ),
    ],
)
async def test_cancel_ops_pipeline_execution_marks_undecidable_response_uncertain(
    response_factory: Callable[[], httpx.Response],
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response_factory()

    client = _client(handler)
    with pytest.raises(KorTravelMapUnavailable) as exc:
        await client.cancel_ops_pipeline_execution(
            "11111111-1111-4111-8111-111111111111",
            reason="decode failure must reconcile",
        )

    assert calls == 1
    assert exc.value.code == "PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN"
    assert exc.value.details == {
        "outcome_certainty": "uncertain",
        "reconciliation": {
            "method": "GET",
            "path": ("/v1/ops/pipeline/executions/import_job/11111111-1111-4111-8111-111111111111"),
            "scope": "ops:read",
        },
    }
    await client.aclose()


async def test_list_dedup_reviews_forwards_filters() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = list(request.url.params.multi_items())
        return httpx.Response(
            200,
            json={
                "data": {
                    "items": [
                        {
                            "review_id": "dedup-1",
                            "status": "pending",
                            "total_score": 88,
                            "name_score": 90,
                            "spatial_score": 80,
                            "category_score": 95,
                            "distance_m": 12.5,
                            "feature_a": {
                                "feature_id": "f_a",
                                "name": "A",
                                "kind": "place",
                                "category": "01010100",
                            },
                            "feature_b": {
                                "feature_id": "f_b",
                                "name": "B",
                                "kind": "place",
                                "category": "01010100",
                            },
                            "created_at": "2026-06-12T00:00:00+09:00",
                        }
                    ]
                },
                "meta": {"page": {"next_cursor": "next"}},
            },
        )

    client = _client(handler)
    payload = await client.list_dedup_reviews(
        statuses=["pending"],
        providers=["kma"],
        dataset_keys=["places"],
        kinds=["place"],
        categories=["01010100"],
        min_score=70,
        max_score=95,
        q="해운대",
        page_size=20,
        cursor="cur",
    )
    assert seen["path"] == "/v1/admin/dedup-reviews"
    assert ("status", "pending") in seen["query"]
    assert ("provider", "kma") in seen["query"]
    assert ("dataset_key", "places") in seen["query"]
    assert ("min_score", "70") in seen["query"]
    assert ("max_score", "95") in seen["query"]
    assert payload["data"]["items"][0]["review_id"] == "dedup-1"
    await client.aclose()


async def test_decide_dedup_review_patches_decision_body() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": {
                    "review_id": "dedup-1",
                    "decision": "merged",
                    "changed": True,
                    "master_feature_id": "f_a",
                    "loser_feature_id": "f_b",
                    "merge_id": "merge-1",
                    "source_links_moved": 2,
                    "source_links_dropped": 0,
                },
                "meta": {},
            },
        )

    client = _client(handler)
    data = await client.decide_dedup_review(
        "dedup-1",
        decision="merged",
        decision_reason="동일 장소",
        master_feature_id="f_a",
        reviewed_by="pinvi-admin",
    )
    assert seen["method"] == "PATCH"
    assert seen["path"] == "/v1/admin/dedup-reviews/dedup-1"
    assert seen["body"] == {
        "decision": "merged",
        "decision_reason": "동일 장소",
        "master_feature_id": "f_a",
        "reviewed_by": "pinvi-admin",
    }
    assert data["merge_id"] == "merge-1"
    await client.aclose()


async def test_ops_consistency_and_log_methods_use_ops_paths() -> None:
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if request.url.path.endswith("issues"):
            data = {"items": []}
        elif request.url.path.endswith("reports"):
            data = {"items": []}
        elif request.url.path.endswith("system-logs"):
            data = {"items": []}
        else:
            data = {"items": []}
        return httpx.Response(200, json={"data": data, "meta": {"page": {"next_cursor": None}}})

    client = _client(handler)
    await client.list_integrity_issues(status_filter="open", severity="error", page_size=10)
    await client.list_consistency_reports(severity_max="WARN", page_size=10)
    await client.list_system_logs(level="error", source="api", q="timeout", page_size=10)
    await client.list_ops_api_call_logs(method="GET", min_status=500, path="/v1", page_size=10)
    assert seen_paths == [
        "/v1/ops/consistency/issues",
        "/v1/ops/consistency/reports",
        "/v1/ops/system-logs",
        "/v1/ops/api-call-logs",
    ]
    await client.aclose()


async def test_patch_admin_issue_uses_admin_issue_path_and_body() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": {
                    "issue": {
                        "issue_id": "iss-1",
                        "violation_type": "missing_coord",
                        "severity": "error",
                        "message": "좌표 없음",
                        "payload": {},
                        "status": "resolved",
                        "detected_at": "2026-06-12T00:00:00+09:00",
                        "provider": "kma",
                        "dataset_key": "places",
                        "feature_id": "f_a",
                        "source_record_key": "kma:places:1",
                        "resolved_at": "2026-06-12T00:03:00+09:00",
                    }
                },
                "meta": {},
            },
        )

    client = _client(handler)
    payload = await client.patch_admin_issue(
        "iss-1",
        action="resolve",
        reason="source verified",
        operator="pinvi-admin",
    )
    assert seen == {
        "method": "PATCH",
        "path": "/v1/admin/issues/iss-1",
        "body": {
            "action": "resolve",
            "reason": "source verified",
            "operator": "pinvi-admin",
        },
    }
    assert payload["data"]["issue"]["status"] == "resolved"
    await client.aclose()
