"""M05 paired worker의 permanent pairing fault 회귀."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.kor_travel_map_feature_reference_reconciliation import (
    FeatureReferenceReconciliationProblem,
    FeatureReferenceReconciliationServiceClient,
)
from app.core.config import Settings
from app.services.feature_reference_reconciliation_worker import _worker_loop


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
    assert faults == [f"Map pairing fault: HTTP {status_code} PAIRING_INVALID"]
