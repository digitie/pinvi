"""api_call_log httpx event hook 통합 테스트."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.middleware.api_call_logging import (
    ApiCallTracker,
    api_call_event_hooks,
    sanitize_api_call_endpoint,
)
from app.models.api_call_log import ApiCallLog

pytestmark = pytest.mark.asyncio


async def test_api_call_tracker_persists_httpx_response(session_factory) -> None:
    request_id = uuid.uuid4()
    tracker = ApiCallTracker(session_factory)

    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"ok": True}, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_handler),
        event_hooks={"request": [tracker.on_request], "response": [tracker.on_response]},
    ) as client:
        response = await client.get(
            "https://provider.pinvi.test/v1/items",
            extensions={
                "pinvi_provider": "resend",
                "pinvi_request_id": str(request_id),
            },
        )

    assert response.status_code == 202

    async with session_factory() as db:
        row = await db.scalar(select(ApiCallLog).where(ApiCallLog.provider == "resend"))
        assert row is not None
        assert row.endpoint == "https://provider.pinvi.test/v1/items"
        assert row.status_code == 202
        assert row.request_id == request_id
        assert row.latency_ms is not None


async def test_api_call_event_hooks_tag_provider_and_sanitize_endpoint(session_factory) -> None:
    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True}, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_handler),
        event_hooks=api_call_event_hooks(session_factory, provider="kor_travel_geo"),
    ) as client:
        await client.get("https://geo.example.test/v2/geocode?key=secret-key&q=서울")

    async with session_factory() as db:
        row = await db.scalar(select(ApiCallLog).where(ApiCallLog.provider == "kor_travel_geo"))
        assert row is not None
        assert (
            row.endpoint == "https://geo.example.test/v2/geocode?key=%2A%2A%2A&q=%EC%84%9C%EC%9A%B8"
        )
        assert "secret-key" not in row.endpoint


async def test_sanitize_api_call_endpoint_masks_telegram_token() -> None:
    assert (
        sanitize_api_call_endpoint(
            "https://api.telegram.org/bot123456:abcdefghiABCDEFGHI123456789/sendMessage"
        )
        == "https://api.telegram.org/bot123456:***/sendMessage"
    )
