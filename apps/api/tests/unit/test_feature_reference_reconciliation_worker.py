"""M05 paired worker의 permanent pairing fault 회귀."""

from __future__ import annotations

import asyncio
import logging
import traceback
import uuid
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.kor_travel_map_feature_reference_reconciliation import (
    FeatureReferenceReconciliationProblem,
    FeatureReferenceReconciliationServiceClient,
)
from app.core.config import Settings, settings
from app.services import feature_reference_reconciliation_worker as reconciliation_worker
from app.services.feature_reference_reconciliation_worker import (
    _worker_loop,
    feature_reference_reconciliation_worker_lifespan,
)


class _ReadAfterInitialEmpty:
    def __init__(self, problem: FeatureReferenceReconciliationProblem) -> None:
        self._problem = problem
        self.calls = 0

    async def lease(self, *, worker_id: uuid.UUID) -> None:
        del worker_id
        self.calls += 1
        if self.calls == 1:
            return None
        raise self._problem


class _AlwaysProblem:
    def __init__(self, problem: FeatureReferenceReconciliationProblem) -> None:
        self._problem = problem

    async def lease(self, *, worker_id: uuid.UUID) -> None:
        del worker_id
        raise self._problem


class _ClosingClient:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403, 422, 503])
async def test_worker_stops_after_initial_empty_when_pairing_becomes_permanently_invalid(
    status_code: int,
) -> None:
    """초기 204 뒤 permanent Map fault는 poll-rate 재시도로 숨기지 않는다."""

    read = _ReadAfterInitialEmpty(
        FeatureReferenceReconciliationProblem(status_code=status_code, code="PAIRING_INVALID")
    )
    faults: list[str] = []
    config = cast(
        Settings,
        SimpleNamespace(
            pinvi_kor_travel_map_feature_reference_reconciliation_poll_seconds=0,
            pinvi_kor_travel_map_feature_reference_reconciliation_blocked_recheck_seconds=0,
        ),
    )
    await _worker_loop(
        session_factory=cast(async_sessionmaker[AsyncSession], None),
        read_client=cast(FeatureReferenceReconciliationServiceClient, read),
        ack_client=cast(FeatureReferenceReconciliationServiceClient, object()),
        worker_id=uuid.uuid4(),
        config=config,
        on_permanent_fault=faults.append,
    )

    assert read.calls == 2
    assert faults == ["map_pairing_fault"]


@pytest.mark.asyncio
async def test_nonpermanent_problem_log_redacts_remote_error_code(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "M05_REMOTE_ERROR_CODE_SENTINEL"
    read = _AlwaysProblem(FeatureReferenceReconciliationProblem(status_code=400, code=sentinel))
    config = cast(
        Settings,
        SimpleNamespace(
            pinvi_kor_travel_map_feature_reference_reconciliation_poll_seconds=0,
            pinvi_kor_travel_map_feature_reference_reconciliation_blocked_recheck_seconds=0,
        ),
    )

    async def cancel_sleep(_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(
        "app.services.feature_reference_reconciliation_worker.asyncio.sleep", cancel_sleep
    )
    with caplog.at_level(logging.ERROR, logger=reconciliation_worker.logger.name):
        with pytest.raises(asyncio.CancelledError):
            await _worker_loop(
                session_factory=cast(async_sessionmaker[AsyncSession], None),
                read_client=cast(FeatureReferenceReconciliationServiceClient, read),
                ack_client=cast(FeatureReferenceReconciliationServiceClient, object()),
                worker_id=uuid.uuid4(),
                config=config,
                on_permanent_fault=lambda _fault: None,
            )

    assert "HTTP 400" in caplog.text
    assert sentinel not in caplog.text


@pytest.mark.asyncio
async def test_preflight_exception_redacts_remote_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "M05_REMOTE_ERROR_CODE_SENTINEL"
    created_clients = [_ClosingClient(), _ClosingClient()]
    clients = created_clients.copy()

    async def raise_problem(*_args: object, **_kwargs: object) -> None:
        raise FeatureReferenceReconciliationProblem(status_code=503, code=sentinel)

    monkeypatch.setattr(
        settings,
        "pinvi_kor_travel_map_feature_reference_reconciliation_enabled",
        True,
    )
    monkeypatch.setattr(
        settings,
        "pinvi_kor_travel_map_feature_reference_reconciliation_read_token",
        SecretStr("read-token"),
    )
    monkeypatch.setattr(
        settings,
        "pinvi_kor_travel_map_feature_reference_reconciliation_ack_token",
        SecretStr("ack-token"),
    )
    monkeypatch.setattr(reconciliation_worker, "_client", lambda **_kwargs: clients.pop(0))
    monkeypatch.setattr(
        reconciliation_worker,
        "consume_feature_reference_reconciliation_once",
        raise_problem,
    )

    with pytest.raises(RuntimeError) as raised:
        async with feature_reference_reconciliation_worker_lifespan(FastAPI()):
            pytest.fail("M05 preflight failure must not start the application")

    rendered = "".join(traceback.format_exception(raised.value))
    assert sentinel not in rendered
    assert raised.value.__cause__ is None
    assert all(client.closed for client in created_clients)
