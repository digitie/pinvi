"""api_call_log httpx event hook 통합 테스트."""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
from sqlalchemy import select, text

from app.clients.resend import create_resend_client
from app.core.config import settings
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
                "request_id": str(request_id),
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
        # 가린 자리만 바꾸고 나머지는 원래 인코딩 그대로(stdout 로그와 같은 모양, #620)
        assert row.endpoint == "https://geo.example.test/v2/geocode?key=***&q=%EC%84%9C%EC%9A%B8"
        assert "secret-key" not in row.endpoint


async def test_resend_client_persists_provider_log(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
) -> None:
    monkeypatch.setattr(settings, "pinvi_resend_api_key", "re_test")
    monkeypatch.setattr(settings, "pinvi_resend_api_base_url", "https://api.resend.com")

    async def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/emails"
        assert request.headers["authorization"] == "Bearer re_test"
        return httpx.Response(200, json={"id": "email_mocked"}, request=request)

    async with create_resend_client(transport=httpx.MockTransport(_handler)) as client:
        resend_id = await client.send_email(
            {
                "from": "Pinvi <noreply@send.pinvi.test>",
                "to": ["user@pinvi.test"],
                "subject": "테스트",
                "html": "<p>ok</p>",
            }
        )

    assert resend_id == "email_mocked"
    async with session_factory() as db:
        row = await db.scalar(select(ApiCallLog).where(ApiCallLog.provider == "resend"))
        assert row is not None
        assert row.endpoint == "https://api.resend.com/emails"
        assert row.status_code == 200


async def test_sanitize_api_call_endpoint_masks_telegram_token() -> None:
    assert (
        sanitize_api_call_endpoint(
            "https://api.telegram.org/bot123456:abcdefghiABCDEFGHI123456789/sendMessage"
        )
        == "https://api.telegram.org/bot123456:***/sendMessage"
    )


async def test_cancelled_log_insert_releases_session_and_pool(session_factory) -> None:
    """실제 PG INSERT 잠금 대기 중 취소해도 이후 요청이 같은 pool을 사용한다."""
    tracker = ApiCallTracker(session_factory)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True}, request=request)

    async with session_factory() as blocker:
        await blocker.execute(text("LOCK TABLE app.api_call_log IN SHARE MODE"))
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            event_hooks={"request": [tracker.on_request], "response": [tracker.on_response]},
        ) as client:
            pending = asyncio.create_task(client.get("https://provider.pinvi.test/cancelled"))
            try:
                async with session_factory() as observer:
                    for _ in range(200):
                        waiting = await observer.scalar(
                            text("""
                            SELECT EXISTS (
                                SELECT 1 FROM pg_catalog.pg_locks
                                WHERE relation = 'app.api_call_log'::regclass
                                  AND database = (SELECT oid FROM pg_database
                                                  WHERE datname = current_database())
                                  AND NOT granted
                            )
                        """)
                        )
                        if waiting:
                            break
                        await asyncio.sleep(0.01)
                    else:
                        pytest.fail("owned PG insert did not reach lock wait")
                pending.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(pending, 2)
            finally:
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
                await blocker.rollback()
            response = await asyncio.wait_for(
                client.get("https://provider.pinvi.test/after-cancellation"), 2
            )
            assert response.status_code == 200
    async with session_factory() as db:
        assert await db.scalar(text("SELECT 1")) == 1
        assert (
            await db.scalar(
                select(ApiCallLog).where(
                    ApiCallLog.endpoint == "https://provider.pinvi.test/after-cancellation"
                )
            )
            is not None
        )
