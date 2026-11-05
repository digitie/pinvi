"""소유 TCP/UDS HTTP와 실제 PG에서 서비스 factory의 관측 계약을 검증한다."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from app.api.v1.admin import system
from app.clients.kor_travel_map_cache_target import CacheTargetNetworkError
from app.clients.kor_travel_map_feature_reference_reconciliation import (
    FeatureReferenceReconciliationUnavailable,
)
from app.clients.telegram import TelegramError
from app.core.config import settings
from app.middleware.api_call_logging import close_api_call_logs
from app.models.api_call_log import ApiCallLog
from app.services import admin_etl, oauth_google
from tests.plain_http_fixtures import CASES, FIXTURE_BOT, exercise


@asynccontextmanager
async def fixture_server(tmp_path, case, is_timeout):
    calls = []
    active = set()

    async def handle(reader, writer):
        task = asyncio.current_task()
        active.add(task)
        try:
            headers = await reader.readuntil(b"\r\n\r\n")
            first = headers.split(b"\r\n", 1)[0].decode()
            calls.append(first)
            if is_timeout:
                await reader.read()
                return
            if case == "oauth":
                payload = (
                    {"access_token": "fixture-private"}
                    if "/token?" in first
                    else {
                        "sub": "fixture-user",
                        "email": "fixture@example.test",
                        "email_verified": True,
                    }
                )
            elif case.startswith("telegram"):
                payload = {
                    "ok": True,
                    "result": {
                        "type": "private",
                        "first_name": "fixture",
                        "message_id": 1,
                    },
                }
            elif case == "system_uds":
                payload = []
            else:
                payload = {}
            body = json.dumps(payload).encode()
            status = "503 Service Unavailable" if case == "dagster" else "200 OK"
            writer.write(
                f"HTTP/1.1 {status}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
                + body
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            active.discard(task)

    tcp = await asyncio.start_server(handle, "127.0.0.1", 0)
    unix = await asyncio.start_unix_server(handle, str(tmp_path / "fixture-docker.sock"))
    base_url = f"http://127.0.0.1:{tcp.sockets[0].getsockname()[1]}"
    try:
        yield base_url, calls
    finally:
        for server in (tcp, unix):
            server.close()
            await server.wait_closed()
        if active:
            await asyncio.wait_for(asyncio.gather(*active), 2)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("is_timeout", [False, True], ids=["response", "timeout"])
async def test_owned_http_factory_observations_persist_in_pg(
    monkeypatch,
    tmp_path,
    session_factory,
    case,
    is_timeout,
):
    async with fixture_server(tmp_path, case, is_timeout) as (base_url, calls):
        for name in (
            "pinvi_telegram_api_base",
            "pinvi_kor_travel_map_api_base_url",
            "pinvi_web_base_url",
            "pinvi_dagster_base_url",
            "pinvi_rustfs_endpoint_url",
        ):
            monkeypatch.setattr(settings, name, base_url)
        for name in (
            "pinvi_telegram_timeout_seconds",
            "pinvi_kor_travel_map_timeout_seconds",
            "pinvi_oauth_http_timeout_seconds",
            "pinvi_docker_status_timeout_seconds",
        ):
            monkeypatch.setattr(settings, name, 0.08)
        monkeypatch.setattr(system, "SYSTEM_PROBE_TIMEOUT_SECONDS", 0.08)
        monkeypatch.setattr(admin_etl, "PINVI_DAGSTER_PROBE_TIMEOUT_SECONDS", 0.08)
        config = oauth_google.get_provider_config("google")
        monkeypatch.setattr(
            oauth_google,
            "get_provider_config",
            lambda _provider: SimpleNamespace(
                **{
                    **config.__dict__,
                    "token_url": f"{base_url}/token?key=fixture-private",
                    "userinfo_url": f"{base_url}/userinfo?key=fixture-private",
                }
            ),
        )
        started = asyncio.get_running_loop().time()
        try:
            try:
                result = await exercise(monkeypatch, tmp_path, case)
                if case == "oauth" and not is_timeout:
                    assert result.provider_user_id == "fixture-user"
            except TelegramError as exc:
                assert is_timeout
                assert exc.code == "network_error"
                assert isinstance(exc.__cause__, TimeoutError)
                assert isinstance(exc.__cause__.__cause__, asyncio.CancelledError)
                assert 0.04 <= asyncio.get_running_loop().time() - started < 1
            except (
                httpx.HTTPError,
                CacheTargetNetworkError,
                FeatureReferenceReconciliationUnavailable,
            ):
                assert is_timeout
        finally:
            await close_api_call_logs(session_factory)

    async with session_factory() as db:
        rows = list((await db.scalars(select(ApiCallLog).order_by(ApiCallLog.log_id))).all())
    assert calls
    assert len(rows) == len(calls)
    assert all(row.latency_ms is not None and row.occurred_at.tzinfo is not None for row in rows)
    assert all(row.provider != "unknown" for row in rows)
    if is_timeout:
        # Telegram은 기존 outer asyncio.timeout이 같은 read 상한보다 먼저 전송을 취소한다.
        # 관측은 그 취소를 기록하고 공개 TelegramError는 network_error로 유지한다.
        error_class = "CancelledError" if case.startswith("telegram") else "ReadTimeout"
        assert all(row.status_code is None and row.error_class == error_class for row in rows)
        if case.startswith("telegram"):
            assert all(row.latency_ms >= 40 for row in rows)
    else:
        assert all(row.status_code in {200, 503} for row in rows)
    content = repr([(row.endpoint, row.error_message) for row in rows])
    assert "fixture-private" not in content
    assert FIXTURE_BOT not in content
