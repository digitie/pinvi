"""범용 Feature 요청 service writer의 strict transport 회귀."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.clients.kor_travel_map_feature_request import (
    FeatureRequestQueueContractError,
    FeatureRequestQueueProblem,
    FeatureRequestQueueUnavailable,
    FeatureRequestServiceClient,
)

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> FeatureRequestServiceClient:
    return FeatureRequestServiceClient(
        httpx.AsyncClient(
            base_url="http://kor-travel-map.test",
            transport=httpx.MockTransport(handler),
        ),
        token="feature-request-token",
        max_attempts=1,
    )


def _response(
    request_id: uuid.UUID,
    *,
    status: str = "pending",
    meta_request_id: str = "m04-test",
) -> dict[str, Any]:
    return {
        "data": {
            "request_id": str(request_id),
            "status": status,
            "kind": "place",
            "name": "새 카페",
            "coord": {"lon": 129.0, "lat": 35.0},
            "categories": ["카페", "01070100"],
            "note": "좋은 곳",
            "submitted_at": "2026-08-20T09:00:00+09:00",
            "resolved_at": None,
            "resolved_by_actor": None,
            "feature_id": "01900000-0000-7000-8000-000000000001"
            if status == "exact_conflict"
            else None,
            "rejection_reason": None,
        },
        "meta": {"duration_ms": 1, "request_id": meta_request_id},
    }


@pytest.mark.asyncio
async def test_submit_uses_exact_service_path_headers_and_same_request_uuid() -> None:
    request_id = uuid.UUID("01900000-0000-7000-8000-000000000002")
    correlation_id = uuid.UUID("01900000-0000-7000-8000-000000000003")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/service/feature-requests"
        assert request.headers["X-Kor-Travel-Map-Service-Token"] == "feature-request-token"
        assert request.headers["Idempotency-Key"] == str(request_id)
        assert request.headers["X-Request-ID"] == str(correlation_id)
        assert request.extensions["request_id"] == str(correlation_id)
        assert json.loads(request.content) == {
            "request_id": str(request_id),
            "kind": "place",
            "name": "새 카페",
            "coord": {"lon": 129.0, "lat": 35.0},
            "categories": ["카페", "01070100"],
            "note": "좋은 곳",
        }
        return httpx.Response(
            201,
            json=_response(request_id, meta_request_id=str(correlation_id)),
            request=request,
        )

    client = _client(handler)
    try:
        receipt = await client.submit(
            request_id=request_id,
            kind="place",
            name="새 카페",
            lon=129.0,
            lat=35.0,
            categories=["카페", "01070100"],
            note="좋은 곳",
            correlation_id=correlation_id,
        )
    finally:
        await client.aclose()

    assert receipt.request_id == request_id
    assert receipt.status == "pending"
    assert receipt.feature_id is None


@pytest.mark.asyncio
async def test_submit_rejects_response_with_different_correlation_id() -> None:
    request_id = uuid.UUID("01900000-0000-7000-8000-000000000002")
    correlation_id = uuid.UUID("01900000-0000-7000-8000-000000000003")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json=_response(
                request_id,
                meta_request_id="01900000-0000-7000-8000-000000000004",
            ),
            request=request,
        )

    client = _client(handler)
    try:
        with pytest.raises(FeatureRequestQueueContractError, match="meta request_id"):
            await client.submit(
                request_id=request_id,
                kind="place",
                name="새 카페",
                lon=129.0,
                lat=35.0,
                categories=["카페", "01070100"],
                note="좋은 곳",
                correlation_id=correlation_id,
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["meta"].pop("duration_ms"),
        lambda payload: payload["meta"].update({"unexpected": True}),
        lambda payload: payload["data"].pop("rejection_reason"),
        lambda payload: payload["data"].update({"name": "다른 이름"}),
        lambda payload: payload["data"]["coord"].update({"lon": "129.0"}),
    ],
)
async def test_submit_rejects_malformed_or_nonmatching_success_receipt(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    request_id = uuid.UUID("01900000-0000-7000-8000-000000000002")

    def handler(request: httpx.Request) -> httpx.Response:
        payload = _response(request_id)
        mutate(payload)
        return httpx.Response(201, json=payload, request=request)

    client = _client(handler)
    try:
        with pytest.raises(FeatureRequestQueueContractError):
            await client.submit(
                request_id=request_id,
                kind="place",
                name="새 카페",
                lon=129.0,
                lat=35.0,
                categories=["카페", "01070100"],
                note="좋은 곳",
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_submit_rejects_response_for_another_request_id() -> None:
    request_id = uuid.UUID("01900000-0000-7000-8000-000000000002")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json=_response(uuid.UUID("01900000-0000-7000-8000-000000000003")),
            request=request,
        )

    client = _client(handler)
    try:
        with pytest.raises(FeatureRequestQueueContractError, match="request_id"):
            await client.submit(
                request_id=request_id,
                kind="place",
                name="새 카페",
                lon=129.0,
                lat=35.0,
                categories=[],
                note=None,
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_submit_preserves_conflict_and_fails_closed_for_unavailable() -> None:
    request_id = uuid.UUID("01900000-0000-7000-8000-000000000002")

    def conflict(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={"code": "IDEMPOTENCY_PAYLOAD_CONFLICT"},
            request=request,
        )

    client = _client(conflict)
    try:
        with pytest.raises(FeatureRequestQueueProblem) as raised:
            await client.submit(
                request_id=request_id,
                kind="place",
                name="새 카페",
                lon=129.0,
                lat=35.0,
                categories=[],
                note=None,
            )
        assert raised.value.status_code == 409
        assert raised.value.code == "IDEMPOTENCY_PAYLOAD_CONFLICT"
    finally:
        await client.aclose()

    def unavailable(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    client = _client(unavailable)
    try:
        with pytest.raises(FeatureRequestQueueUnavailable):
            await client.submit(
                request_id=request_id,
                kind="place",
                name="새 카페",
                lon=129.0,
                lat=35.0,
                categories=[],
                note=None,
            )
    finally:
        await client.aclose()
