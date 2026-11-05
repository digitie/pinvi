"""실제 서비스 factory가 소유 MockTransport의 실패·취소를 안전하게 관측한다."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
from fastapi import FastAPI
from pydantic import SecretStr

from app.api.v1 import telegram_targets
from app.api.v1.admin import system
from app.core.config import settings
from app.db import session as db_session
from app.services import (
    admin_etl,
    cache_target_sync_worker,
    feature_reference_reconciliation_worker,
    oauth_google,
    telegram_notify,
)

CASES = (
    "oauth",
    "telegram_route",
    "telegram_notify",
    "reconciliation",
    "cache_command",
    "cache_consumer",
    "system_tcp",
    "system_uds",
    "dagster",
)
FIXTURE_BOT = "123456:fixturePRIVATEabcdefghijklmnop"


class RecordingFactory:
    def __init__(self) -> None:
        self.rows = []
        self.fail = False

    def __call__(self):
        return self

    async def __aenter__(self):
        if self.fail:
            raise RuntimeError("password=private-log-database")
        return self

    async def __aexit__(self, *_args):
        pass

    async def execute(self, _statement, rows=()):
        self.rows.extend(rows)

    async def commit(self):
        pass


class Scenario:
    def __init__(self, case: str, mode: str):
        self.case = case
        self.mode = mode
        self.entered = asyncio.Event()
        self.requests = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.entered.set()
        if self.mode == "connect":
            raise httpx.ConnectError("Authorization: Bearer fixture-private", request=request)
        if self.mode == "timeout":
            raise httpx.ReadTimeout("key=fixture-private", request=request)
        if self.mode == "cancel":
            await asyncio.Event().wait()
        if self.mode == "body":

            class Broken(httpx.AsyncByteStream):
                async def __aiter__(self):
                    yield b"{"
                    raise httpx.ReadError("password=fixture-private")

            return httpx.Response(200, stream=Broken())
        if self.case == "oauth":
            payload = (
                {"access_token": "fixture-private"}
                if request.url.path == "/token"
                else {
                    "sub": "fixture-user",
                    "email": "fixture@example.test",
                    "email_verified": True,
                }
            )
        elif self.case.startswith("telegram"):
            payload = {
                "ok": True,
                "result": {
                    "type": "private",
                    "first_name": "fixture",
                    "message_id": 1,
                },
            }
        elif self.case == "system_uds":
            payload = []
        else:
            payload = {}
        # HTTP transport 성공/실패와 probe 도메인 상태를 섞지 않는다.
        return httpx.Response(503 if self.case == "dagster" else 200, json=payload)


def install_transport(monkeypatch, scenario, factory):
    original_init = httpx.AsyncClient.__init__

    def init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(scenario)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", init)
    monkeypatch.setattr(db_session, "async_session_factory", factory)
    for name in (
        "pinvi_telegram_api_base",
        "pinvi_kor_travel_map_api_base_url",
        "pinvi_web_base_url",
        "pinvi_dagster_base_url",
        "pinvi_rustfs_endpoint_url",
    ):
        monkeypatch.setattr(settings, name, "http://fixture.invalid?key=fixture-private")
    monkeypatch.setattr(settings, "pinvi_telegram_api_base", "http://fixture.invalid")
    monkeypatch.setattr(settings, "pinvi_kor_travel_map_api_base_url", "http://fixture.invalid")
    monkeypatch.setattr(settings, "pinvi_dagster_base_url", "http://fixture.invalid")
    config = oauth_google.get_provider_config("google")
    monkeypatch.setattr(
        oauth_google,
        "get_provider_config",
        lambda _provider: SimpleNamespace(
            **{
                **config.__dict__,
                "token_url": "http://fixture.invalid/token?key=fixture-private",
                "userinfo_url": "http://fixture.invalid/userinfo?key=fixture-private",
            }
        ),
    )


@asynccontextmanager
async def cache_client(monkeypatch, role):
    captured = {}
    ready = asyncio.Event()

    async def bootstrap(*_args, consumer_client, **_kwargs):
        captured["consumer"] = consumer_client

    async def command(client, _settings):
        captured["command"] = client
        ready.set()
        await asyncio.Event().wait()

    async def consumer(*_args, **_kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(settings, "pinvi_kor_travel_map_cache_target_sync_enabled", True)
    monkeypatch.setattr(
        settings, "pinvi_kor_travel_map_cache_target_command_token", SecretStr("c" * 40)
    )
    monkeypatch.setattr(
        settings, "pinvi_kor_travel_map_cache_target_consumer_token", SecretStr("r" * 40)
    )
    monkeypatch.setattr(cache_target_sync_worker, "bootstrap_cache_target_sync", bootstrap)
    monkeypatch.setattr(cache_target_sync_worker, "_command_loop", command)
    monkeypatch.setattr(cache_target_sync_worker, "_consumer_loop", consumer)
    async with cache_target_sync_worker.cache_target_sync_worker_lifespan(FastAPI()):
        await asyncio.wait_for(ready.wait(), 1)
        yield captured[role]


async def exercise(monkeypatch, tmp_path, case):
    if case == "oauth":
        return await oauth_google.exchange_code_for_claims(
            code="fixture-private",
            code_verifier="fixture-private",
        )
    if case == "telegram_route":
        iterator = telegram_targets.get_telegram_client()
        client = await anext(iterator)
        try:
            return await client.verify_target(FIXTURE_BOT, "fixture-chat")
        finally:
            await iterator.aclose()
    if case == "telegram_notify":
        client = telegram_notify._make_client()
        try:
            return await client.send_to_target(FIXTURE_BOT, "fixture-chat", "fixture-private")
        finally:
            await client.aclose()
    if case == "reconciliation":
        client = feature_reference_reconciliation_worker._client(
            role="read", token="r" * 40, config=settings
        )
        try:
            return await client._send("GET", "/fixture?key=fixture-private", headers={})
        finally:
            await client.aclose()
    if case.startswith("cache_"):
        role = case.removeprefix("cache_")
        async with cache_client(monkeypatch, role) as client:
            return await client._send(
                "POST" if role == "command" else "GET",
                "/fixture?key=fixture-private",
            )
    if case == "system_tcp":
        return await system._probe_dependency_services(RecordingFactory())
    if case == "system_uds":
        socket = tmp_path / "fixture-docker.sock"
        socket.touch()
        monkeypatch.setattr(settings, "pinvi_docker_socket_path", str(socket))
        return await system._collect_docker_status()
    return await admin_etl._probe_pinvi_dagster()
