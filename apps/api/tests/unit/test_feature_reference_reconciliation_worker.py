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
from app.services.feature_reference_reconciliation import ReconciliationApplied
from app.services.feature_reference_reconciliation_worker import (
    FeatureReferenceReconciliationRuntimeLeaseError,
    _worker_loop,
    consume_feature_reference_reconciliation_once,
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


class _Session:
    async def commit(self) -> None:
        return None


class _SessionContext:
    async def __aenter__(self) -> _Session:
        return _Session()

    async def __aexit__(self, *_args: object) -> None:
        return None


class _SessionFactory:
    def __call__(self) -> _SessionContext:
        return _SessionContext()


class _LeaseClient:
    def __init__(self) -> None:
        event_id = uuid.uuid4()
        self.calls = 0
        self.lease_value = SimpleNamespace(
            event=SimpleNamespace(event_id=event_id, event_sequence=1),
            event_sha256="a" * 64,
            lease_epoch=1,
        )

    async def lease(self, *, worker_id: uuid.UUID) -> SimpleNamespace:
        del worker_id
        self.calls += 1
        return self.lease_value


class _AckClient:
    def __init__(self) -> None:
        self.calls = 0

    async def acknowledge(self, **_kwargs: object) -> None:
        self.calls += 1


@pytest.mark.asyncio
async def test_consume_rejects_revoked_runtime_lease_before_map_read() -> None:
    read = _LeaseClient()

    with pytest.raises(FeatureReferenceReconciliationRuntimeLeaseError):
        await consume_feature_reference_reconciliation_once(
            cast(async_sessionmaker[AsyncSession], _SessionFactory()),
            read_client=cast(FeatureReferenceReconciliationServiceClient, read),
            ack_client=cast(FeatureReferenceReconciliationServiceClient, _AckClient()),
            worker_id=uuid.uuid4(),
            runtime_lease_validator=lambda: (_ for _ in ()).throw(RuntimeError("revoked")),
        )

    assert read.calls == 0


@pytest.mark.asyncio
async def test_consume_rejects_revoked_runtime_lease_between_commit_and_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = _LeaseClient()
    ack = _AckClient()
    checks = 0

    def validate_runtime_lease() -> None:
        nonlocal checks
        checks += 1
        if checks == 2:
            raise RuntimeError("revoked")

    async def applied(*_args: object, **_kwargs: object) -> ReconciliationApplied:
        return ReconciliationApplied(
            event_id=read.lease_value.event.event_id,
            local_receipt_sha256="b" * 64,
            replayed_local_receipt=False,
        )

    monkeypatch.setattr(
        reconciliation_worker,
        "apply_feature_reference_reconciliation_event",
        applied,
    )
    with pytest.raises(FeatureReferenceReconciliationRuntimeLeaseError):
        await consume_feature_reference_reconciliation_once(
            cast(async_sessionmaker[AsyncSession], _SessionFactory()),
            read_client=cast(FeatureReferenceReconciliationServiceClient, read),
            ack_client=cast(FeatureReferenceReconciliationServiceClient, ack),
            worker_id=uuid.uuid4(),
            runtime_lease_validator=validate_runtime_lease,
        )

    assert checks == 2
    assert read.calls == 1
    assert ack.calls == 0


@pytest.mark.asyncio
async def test_worker_stops_with_runtime_lease_fault_before_map_read() -> None:
    read = _LeaseClient()
    faults: list[str] = []
    config = cast(
        Settings,
        SimpleNamespace(
            pinvi_kor_travel_map_feature_reference_reconciliation_poll_seconds=0,
            pinvi_kor_travel_map_feature_reference_reconciliation_blocked_recheck_seconds=0,
            validate_m05_runtime_lease=lambda: (_ for _ in ()).throw(RuntimeError("revoked")),
        ),
    )

    await _worker_loop(
        session_factory=cast(async_sessionmaker[AsyncSession], _SessionFactory()),
        read_client=cast(FeatureReferenceReconciliationServiceClient, read),
        ack_client=cast(FeatureReferenceReconciliationServiceClient, _AckClient()),
        worker_id=uuid.uuid4(),
        config=config,
        on_permanent_fault=faults.append,
    )

    assert faults == ["runtime_lease_fault"]
    assert read.calls == 0


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
