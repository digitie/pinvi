"""restore 전용 runner가 ordinary writer보다 먼저 stream CAS를 확정하는지 검증한다."""

from __future__ import annotations

import uuid

import pytest

from app.clients.kor_travel_map_cache_target import (
    CacheTargetRestoreFenceRecord,
    CacheTargetRestoreFenceResult,
    CacheTargetStreamState,
)
from app.services.cache_target_restore_fence import run_cache_target_restore_fence


def _stream(*, epoch: int, version: int, state: str) -> CacheTargetStreamState:
    return CacheTargetStreamState(
        external_system="pinvi",
        restore_epoch=epoch,
        control_version=version,
        entity_tag=f'"pinvi:{version}"',
        state=state,
        consumer_id="pinvi-cache-target-consumer",
        blocked_event_id=None,
        active_reconciliation=None,
    )


class _Consumer:
    def __init__(self) -> None:
        self.streams = [
            _stream(epoch=7, version=7, state="ready"),
            _stream(epoch=8, version=8, state="fenced"),
        ]
        self.calls = 0

    async def get_stream(self) -> CacheTargetStreamState:
        stream = self.streams[self.calls]
        self.calls += 1
        return stream


class _Restore:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None

    async def advance_restore_fence(self, **kwargs: object) -> CacheTargetRestoreFenceResult:
        self.kwargs = kwargs
        data = CacheTargetRestoreFenceRecord(
            **_stream(epoch=8, version=8, state="fenced").model_dump(),
            fence_id=uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            previous_restore_epoch=7,
            previous_control_version=7,
            invalidated_claim_count=0,
            superseded_delivery_count=0,
            superseded_reconciliation_count=0,
            superseded_reconciliation_request_id=None,
        )
        return CacheTargetRestoreFenceResult(status_code=201, data=data, etag='"pinvi:8"')


@pytest.mark.asyncio
async def test_restore_runner_binds_get_cas_post_fence_tuple_before_writer_resume() -> None:
    consumer = _Consumer()
    restore = _Restore()
    idempotency_key = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")

    result = await run_cache_target_restore_fence(
        consumer_client=consumer,  # type: ignore[arg-type]
        restore_client=restore,  # type: ignore[arg-type]
        consumer_id="pinvi-cache-target-consumer",
        expected_restore_epoch=7,
        idempotency_key=idempotency_key,
        reason="restore after verified snapshot",
    )

    assert consumer.calls == 2
    assert restore.kwargs == {
        "consumer_id": "pinvi-cache-target-consumer",
        "expected_restore_epoch": 7,
        "idempotency_key": idempotency_key,
        "reason": "restore after verified snapshot",
        "stream_etag": '"pinvi:7"',
    }
    assert result.receipt.status_code == 201
    assert result.receipt.data.restore_epoch == 8


@pytest.mark.asyncio
async def test_restore_runner_rejects_stale_epoch_before_restore_write() -> None:
    consumer = _Consumer()
    restore = _Restore()

    with pytest.raises(ValueError, match="expected 값"):
        await run_cache_target_restore_fence(
            consumer_client=consumer,  # type: ignore[arg-type]
            restore_client=restore,  # type: ignore[arg-type]
            consumer_id="pinvi-cache-target-consumer",
            expected_restore_epoch=6,
            idempotency_key=uuid.uuid4(),
            reason="restore after verified snapshot",
        )

    assert restore.kwargs is None
