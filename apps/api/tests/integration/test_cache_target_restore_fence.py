"""restore-fence response-loss receipt를 실제 PostgreSQL에서 검증한다."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.clients.kor_travel_map_cache_target import (
    CacheTargetContractError,
    CacheTargetNetworkError,
    CacheTargetRestoreFenceRecord,
    CacheTargetRestoreFenceResult,
    CacheTargetStreamState,
)
from app.models.cache_target_sync import (
    KtmCacheTargetConsumer,
    KtmCacheTargetRestoreFenceAttempt,
)
from app.services.cache_target_restore_fence import run_cache_target_restore_fence

pytestmark = pytest.mark.asyncio

CONSUMER_ID = "pinvi-cache-target-consumer"


def _stream(*, epoch: int, version: int, state: str) -> CacheTargetStreamState:
    return CacheTargetStreamState(
        external_system="pinvi",
        restore_epoch=epoch,
        control_version=version,
        entity_tag=f'"pinvi:{version}"',
        state=state,
        consumer_id=CONSUMER_ID,
        blocked_event_id=None,
        active_reconciliation=None,
    )


def _receipt(*, status_code: int) -> CacheTargetRestoreFenceResult:
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
    return CacheTargetRestoreFenceResult(status_code=status_code, data=data, etag='"pinvi:8"')


class _Consumer:
    def __init__(self) -> None:
        self.calls = 0

    async def get_stream(self) -> CacheTargetStreamState:
        self.calls += 1
        return (
            _stream(epoch=7, version=7, state="ready")
            if self.calls == 1
            else _stream(
                epoch=8,
                version=8,
                state="fenced",
            )
        )


class _ResponseLostRestore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def advance_restore_fence(self, **kwargs: object) -> CacheTargetRestoreFenceResult:
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            # Map은 CAS를 commit했지만 transport 응답만 잃은 상태를 재현한다.
            raise CacheTargetNetworkError("response lost after Map commit")
        return _receipt(status_code=200)


class _ConcurrentRestore:
    """동일 idempotency key의 최초 201과 Map exact-replay 200을 병렬 재현한다."""

    def __init__(self) -> None:
        self.barrier = asyncio.Barrier(2)
        self.calls: list[dict[str, object]] = []
        self._next_status = 201

    async def advance_restore_fence(self, **kwargs: object) -> CacheTargetRestoreFenceResult:
        self.calls.append(kwargs)
        await self.barrier.wait()
        status_code = self._next_status
        self._next_status = 200
        return _receipt(status_code=status_code)


class _ConcurrentConsumer:
    def __init__(self, restore: _ConcurrentRestore) -> None:
        self.calls = 0
        self._restore = restore

    async def get_stream(self) -> CacheTargetStreamState:
        self.calls += 1
        if len(self._restore.calls) < 2:
            return _stream(epoch=7, version=7, state="ready")
        return _stream(epoch=8, version=8, state="fenced")


async def _seed_consumer(session_factory) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        db.add(KtmCacheTargetConsumer(consumer_id=CONSUMER_ID, external_system="pinvi"))
        await db.commit()


async def test_response_loss_reuses_durable_pre_cas_tuple_and_receives_exact_replay(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    consumer = _Consumer()
    restore = _ResponseLostRestore()
    idempotency_key = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")

    with pytest.raises(CacheTargetNetworkError, match="response lost"):
        await run_cache_target_restore_fence(
            session_factory=session_factory,
            consumer_client=consumer,  # type: ignore[arg-type]
            restore_client=restore,  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            expected_restore_epoch=7,
            idempotency_key=idempotency_key,
            reason="restore after verified snapshot",
        )

    async with session_factory() as db:
        pending = await db.get(KtmCacheTargetRestoreFenceAttempt, idempotency_key)
        assert pending is not None
        assert pending.status == "pending"
        assert pending.expected_control_version == 7
        assert pending.stream_etag == '"pinvi:7"'
        with pytest.raises(DBAPIError, match="pre-CAS tuple is immutable"):
            await db.execute(
                text(
                    "UPDATE app.ktm_cache_target_restore_fence_attempts "
                    "SET reason = 'forged' WHERE idempotency_key = :key"
                ),
                {"key": idempotency_key},
            )
            await db.commit()
        await db.rollback()

    result = await run_cache_target_restore_fence(
        session_factory=session_factory,
        consumer_client=consumer,  # type: ignore[arg-type]
        restore_client=restore,  # type: ignore[arg-type]
        consumer_id=CONSUMER_ID,
        expected_restore_epoch=7,
        idempotency_key=idempotency_key,
        reason="restore after verified snapshot",
    )

    assert result.receipt.status_code == 200
    assert [call["stream_etag"] for call in restore.calls] == ['"pinvi:7"', '"pinvi:7"']
    assert consumer.calls == 2  # second run은 새 before GET 없이 post-fence 확인만 한다.

    async with session_factory() as db:
        completed = await db.get(KtmCacheTargetRestoreFenceAttempt, idempotency_key)
        assert completed is not None
        assert completed.status == "completed"
        assert completed.response_status == 200
        assert completed.response_etag == '"pinvi:8"'
        assert completed.response_body is not None

    replay = await run_cache_target_restore_fence(
        session_factory=session_factory,
        consumer_client=consumer,  # type: ignore[arg-type]
        restore_client=restore,  # type: ignore[arg-type]
        consumer_id=CONSUMER_ID,
        expected_restore_epoch=7,
        idempotency_key=idempotency_key,
        reason="restore after verified snapshot",
    )
    assert replay.receipt == result.receipt
    assert len(restore.calls) == 2


async def test_restore_receipt_rejects_mismatched_replay_input_before_network(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    consumer = _Consumer()
    restore = _ResponseLostRestore()
    idempotency_key = uuid.uuid4()

    with pytest.raises(CacheTargetNetworkError):
        await run_cache_target_restore_fence(
            session_factory=session_factory,
            consumer_client=consumer,  # type: ignore[arg-type]
            restore_client=restore,  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            expected_restore_epoch=7,
            idempotency_key=idempotency_key,
            reason="restore after verified snapshot",
        )

    with pytest.raises(CacheTargetContractError, match="다른 restore fence 입력"):
        await run_cache_target_restore_fence(
            session_factory=session_factory,
            consumer_client=consumer,  # type: ignore[arg-type]
            restore_client=restore,  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            expected_restore_epoch=7,
            idempotency_key=idempotency_key,
            reason="different reason",
        )
    assert len(restore.calls) == 1


async def test_restore_attempt_terminal_receipt_rejects_update_and_delete(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    consumer = _Consumer()
    restore = _ResponseLostRestore()
    idempotency_key = uuid.uuid4()

    with pytest.raises(CacheTargetNetworkError):
        await run_cache_target_restore_fence(
            session_factory=session_factory,
            consumer_client=consumer,  # type: ignore[arg-type]
            restore_client=restore,  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            expected_restore_epoch=7,
            idempotency_key=idempotency_key,
            reason="restore after verified snapshot",
        )
    await run_cache_target_restore_fence(
        session_factory=session_factory,
        consumer_client=consumer,  # type: ignore[arg-type]
        restore_client=restore,  # type: ignore[arg-type]
        consumer_id=CONSUMER_ID,
        expected_restore_epoch=7,
        idempotency_key=idempotency_key,
        reason="restore after verified snapshot",
    )

    async with session_factory() as db:
        for statement in (
            "UPDATE app.ktm_cache_target_restore_fence_attempts "
            "SET response_status = 201 WHERE idempotency_key = :key",
            "DELETE FROM app.ktm_cache_target_restore_fence_attempts WHERE idempotency_key = :key",
        ):
            with pytest.raises(DBAPIError, match=r"immutable|append-only"):
                await db.execute(text(statement), {"key": idempotency_key})
                await db.commit()
            await db.rollback()


async def test_concurrent_same_key_accepts_map_201_and_exact_replay_200(
    session_factory,
) -> None:  # type: ignore[no-untyped-def]
    await _seed_consumer(session_factory)
    restore = _ConcurrentRestore()
    consumer = _ConcurrentConsumer(restore)
    idempotency_key = uuid.uuid4()

    first, second = await asyncio.gather(
        run_cache_target_restore_fence(
            session_factory=session_factory,
            consumer_client=consumer,  # type: ignore[arg-type]
            restore_client=restore,  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            expected_restore_epoch=7,
            idempotency_key=idempotency_key,
            reason="restore after verified snapshot",
        ),
        run_cache_target_restore_fence(
            session_factory=session_factory,
            consumer_client=consumer,  # type: ignore[arg-type]
            restore_client=restore,  # type: ignore[arg-type]
            consumer_id=CONSUMER_ID,
            expected_restore_epoch=7,
            idempotency_key=idempotency_key,
            reason="restore after verified snapshot",
        ),
    )

    assert len(restore.calls) == 2
    assert {call["stream_etag"] for call in restore.calls} == {'"pinvi:7"'}
    assert first.receipt == second.receipt
    assert first.receipt.status_code in {200, 201}

    async with session_factory() as db:
        completed = await db.get(KtmCacheTargetRestoreFenceAttempt, idempotency_key)
        assert completed is not None
        assert completed.status == "completed"
        assert completed.response_status == first.receipt.status_code
