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
    ApiCallLoggingClient,
    ApiCallTracker,
    api_call_event_hooks,
    close_api_call_logs,
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

    await close_api_call_logs(session_factory)
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

    await close_api_call_logs(session_factory)
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

    await close_api_call_logs(session_factory)
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
    """실제 PG 로그 잠금이 HTTP를 막지 않고 flush 취소 뒤에도 기록을 계속한다."""
    tracker = ApiCallTracker(session_factory)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True}, request=request)

    async with session_factory() as blocker:
        await blocker.execute(text("LOCK TABLE app.api_call_log IN SHARE MODE"))
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            event_hooks={"request": [tracker.on_request], "response": [tracker.on_response]},
        ) as client:
            response = await asyncio.wait_for(
                client.get("https://provider.pinvi.test/cancelled"), 1
            )
            assert response.status_code == 200
            pending = asyncio.create_task(tracker.outbox.flush())
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
    await close_api_call_logs(session_factory)
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


async def test_real_loopback_http_failures_are_batched_in_owned_postgres(session_factory) -> None:
    """실제 TCP HTTP response·read timeout·연결 실패와 요청 ID·비밀 제거를 함께 확인한다."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fixture_server():
        connections = set()

        async def handle(reader, writer):
            task = asyncio.current_task()
            connections.add(task)
            try:
                data = await reader.readuntil(b"\r\n\r\n")
                if b"/hang" in data.split(b"\r\n", 1)[0]:
                    await reader.read()  # client timeout/close 때 종료한다.
                else:
                    writer.write(
                        b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}"
                    )
                    await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
                connections.discard(task)

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        try:
            port = server.sockets[0].getsockname()[1]
            yield f"http://127.0.0.1:{port}"
        finally:
            server.close()
            await server.wait_closed()
            if connections:
                await asyncio.wait_for(asyncio.gather(*connections), 2)

    request_id = uuid.uuid4()
    async with fixture_server() as base:
        async with ApiCallLoggingClient(
            timeout=0.05,
            event_hooks=api_call_event_hooks(session_factory, provider="owned_http"),
        ) as client:
            response = await client.get(
                f"{base}/response?key=fixture-secret",
                extensions={"request_id": str(request_id)},
            )
            assert response.status_code == 503
            with pytest.raises(httpx.ReadTimeout):
                await client.get(f"{base}/hang")
    # 명시적으로 닫힌 같은 소유 loopback listener에 연결한다. 실제 provider가 아니다.
    async with ApiCallLoggingClient(
        timeout=0.2,
        event_hooks=api_call_event_hooks(session_factory, provider="owned_http"),
    ) as client:
        with pytest.raises(httpx.ConnectError):
            await client.get(f"{base}/closed")
    await close_api_call_logs(session_factory)
    async with session_factory() as db:
        rows = list(
            (
                await db.scalars(
                    select(ApiCallLog)
                    .where(ApiCallLog.provider == "owned_http")
                    .order_by(ApiCallLog.log_id)
                )
            ).all()
        )
    assert [row.error_class for row in rows] == ["HTTPStatusError", "ReadTimeout", "ConnectError"]
    assert rows[0].request_id == request_id
    assert all(row.latency_ms is not None for row in rows)
    assert "fixture-secret" not in repr([row.endpoint for row in rows])
