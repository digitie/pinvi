"""독립 CLI는 실제 runner 대신 fixture만 호출하고 관측 drain 뒤 engine을 닫는다."""

from __future__ import annotations

import argparse
import asyncio
import uuid

import httpx
import pytest
from pydantic import SecretStr

from app.clients.kor_travel_map_alias_map import AliasMapNetworkError
from app.clients.kor_travel_map_cache_target import CacheTargetNetworkError
from app.commands import (
    cache_target_causal_canary,
    cache_target_initial_cutover,
    cache_target_restore_fence,
    feature_uuid_cutover,
)
from app.core.config import (
    KOR_TRAVEL_MAP_CACHE_TARGET_CAPABILITY_GENERATION,
    KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256,
    KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
    settings,
)
from app.db import session as db_session
from app.middleware.api_call_logging import close_api_call_logs

MODULES = (
    cache_target_restore_fence,
    cache_target_initial_cutover,
    cache_target_causal_canary,
    feature_uuid_cutover,
)


class FixtureComplete(Exception):
    pass


class FixtureDatabase:
    def __init__(self):
        self.rows = []
        self.events = []
        self.fail = False

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        pass

    async def execute(self, _statement, rows=()):
        self.events.append("persist")
        if self.fail:
            raise RuntimeError("password=fixture-private")
        self.rows.extend(rows)

    async def commit(self):
        self.events.append("commit")

    async def dispose(self):
        self.events.append("dispose")


def configure(monkeypatch, module):
    monkeypatch.setattr(
        settings,
        "pinvi_kor_travel_map_cache_target_sync_enabled",
        module is cache_target_causal_canary,
    )
    for name, value in (
        (
            "pinvi_kor_travel_map_cache_target_expected_openapi_sha256",
            KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256,
        ),
        (
            "pinvi_kor_travel_map_cache_target_expected_source_revision",
            KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
        ),
        (
            "pinvi_kor_travel_map_cache_target_expected_contract_generation",
            KOR_TRAVEL_MAP_CACHE_TARGET_CAPABILITY_GENERATION,
        ),
    ):
        monkeypatch.setattr(settings, name, value)
    for role in ("command", "consumer", "restore_fence", "recovery"):
        monkeypatch.setattr(
            settings,
            f"pinvi_kor_travel_map_cache_target_{role}_token",
            SecretStr(f"{role}-" + "x" * 40),
        )
    monkeypatch.setattr(settings, "pinvi_kor_travel_map_service_token", "s" * 40)
    monkeypatch.setattr(settings, "pinvi_kor_travel_map_api_base_url", "http://fixture.invalid")


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__.rsplit(".", 1)[1])
@pytest.mark.parametrize("outcome", ["success", "connect", "cancel"])
@pytest.mark.parametrize("db_failed", [False, True])
async def test_standalone_factory_drains_observations_before_engine_dispose(
    monkeypatch,
    module,
    outcome,
    db_failed,
):
    # CLI main/실제 권한 runner를 실행하지 않는다. guards의 유효한 fixture 설정만 사용한다.
    configure(monkeypatch, module)
    database = FixtureDatabase()
    database.fail = db_failed
    monkeypatch.setattr(db_session, "async_session_factory", database)
    monkeypatch.setattr(db_session, "engine", database)
    requests = []
    original_init = httpx.AsyncClient.__init__

    entered = asyncio.Event()

    async def handler(request):
        requests.append(request)
        entered.set()
        if outcome == "connect":
            raise httpx.ConnectError("password=fixture-private", request=request)
        if outcome == "cancel":
            await asyncio.Event().wait()
        return httpx.Response(200, json={})

    def init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", init)

    async def transport_only(*_args, **kwargs):
        if module is feature_uuid_cutover:
            # signed alias DTO runner 자체는 교체했으며 SQL/이관은 절대 실행하지 않는다.
            client = _args[1]
            await client._get_json("/fixture?key=fixture-private")
        else:
            clients = [v for k, v in kwargs.items() if k.endswith("_client")]
            for client in clients:
                await client._send("GET", "/fixture?key=fixture-private")
        raise FixtureComplete()

    runner_name = {
        cache_target_restore_fence: "run_cache_target_restore_fence",
        cache_target_initial_cutover: "run_initial_cache_target_cutover",
        cache_target_causal_canary: "run_cache_target_causal_canary",
        feature_uuid_cutover: "run_feature_uuid_cutover",
    }[module]
    monkeypatch.setattr(module, runner_name, transport_only)
    args = argparse.Namespace(
        expected_restore_epoch=1,
        idempotency_key=uuid.uuid4(),
        reason="fixture",
        cutover_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        timeout_seconds=1,
        dry_run=True,
        accept_uuid_literals=False,
    )
    try:
        pending = asyncio.create_task(module._run(args))
        if outcome == "cancel":
            await asyncio.wait_for(entered.wait(), 1)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
        elif outcome == "connect":
            with pytest.raises((CacheTargetNetworkError, AliasMapNetworkError)):
                await pending
        else:
            with pytest.raises(FixtureComplete):
                await pending
        assert requests
        assert len(database.rows) == (0 if db_failed else len(requests))
        assert database.events[-1] == "dispose"
        assert database.events.index("persist") < database.events.index("dispose")
        assert "fixture-private" not in repr(database.rows)
        expected = {"success": None, "connect": "ConnectError", "cancel": "CancelledError"}[outcome]
        assert all(row["error_class"] == expected for row in database.rows)
    finally:
        await close_api_call_logs(database)


@pytest.mark.parametrize(
    "module",
    [cache_target_restore_fence, cache_target_initial_cutover, cache_target_causal_canary],
    ids=lambda m: m.__name__.rsplit(".", 1)[1],
)
async def test_m05_cli_contract_guard_still_precedes_client_creation(monkeypatch, module):
    configure(monkeypatch, module)
    monkeypatch.setattr(
        settings, "pinvi_kor_travel_map_cache_target_expected_openapi_sha256", "0" * 64
    )

    def forbidden_init(*_args, **_kwargs):
        raise AssertionError("invalid contract must not create any HTTP client")

    monkeypatch.setattr(httpx.AsyncClient, "__init__", forbidden_init)
    with pytest.raises((RuntimeError, cache_target_causal_canary.CacheTargetCanaryFailure)):
        await module._run(argparse.Namespace())
