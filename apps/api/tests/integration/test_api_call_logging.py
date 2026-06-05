"""api_call_log httpx event hook 통합 테스트."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.middleware.api_call_logging import ApiCallTracker
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
            "https://provider.tripmate.test/v1/items",
            extensions={
                "tripmate_provider": "resend",
                "tripmate_request_id": str(request_id),
            },
        )

    assert response.status_code == 202

    async with session_factory() as db:
        row = await db.scalar(select(ApiCallLog).where(ApiCallLog.provider == "resend"))
        assert row is not None
        assert row.endpoint == "https://provider.tripmate.test/v1/items"
        assert row.status_code == 202
        assert row.request_id == request_id
        assert row.latency_ms is not None
