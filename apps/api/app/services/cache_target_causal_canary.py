"""ordinary worker의 PUT→apply/ACK→DELETE causal chain을 검증한다."""

from __future__ import annotations

import asyncio
import math
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from app.clients.kor_travel_map_cache_target import (
    CacheTargetContractError,
    CacheTargetNetworkError,
    CacheTargetServiceClient,
    CacheTargetServiceProblem,
)
from app.core.cache_target_contract import cache_target_source_fingerprint
from app.models.cache_target_sync import (
    KtmCacheTargetCanaryRun,
    KtmCacheTargetCommand,
    KtmCacheTargetConsumer,
    KtmCacheTargetEvent,
    KtmCacheTargetEventClaim,
    KtmCacheTargetEventClaimItem,
    KtmCacheTargetHead,
)
from app.services.cache_target_boundary_evidence import (
    ACTIVE_SOURCE as _ACTIVE_SOURCE,
)
from app.services.cache_target_boundary_evidence import (
    CANARY_PHASES as _PHASES,
)
from app.services.cache_target_boundary_evidence import (
    DELETED_SOURCE as _DELETED_SOURCE,
)
from app.services.cache_target_boundary_evidence import (
    STABLE_TARGET_ID,
    canary_final_evidence_sha256,
    canary_provenance_sha256,
)
from app.services.cache_target_boundary_evidence import (
    CacheTargetCanaryFailure as CacheTargetCanaryFailure,
)
from app.services.cache_target_boundary_evidence import (
    cache_target_canary_command_id as _command_id,
)
from app.services.cache_target_boundary_evidence import (
    cache_target_command_backlog as _command_backlog,
)
from app.services.cache_target_boundary_evidence import (
    cache_target_snapshot_identity as _snapshot_identity,
)
from app.services.cache_target_boundary_evidence import (
    cache_target_source_payload as _source_payload,
)
from app.services.cache_target_boundary_evidence import (
    cache_target_stream_control_identity as _stream_control_identity,
)
from app.services.cache_target_boundary_evidence import (
    require_ready_cache_target_consumer as _require_ready_consumer,
)
from app.services.cache_target_boundary_evidence import (
    validate_canary_command as _validate_command,
)
from app.services.cache_target_boundary_evidence import (
    validate_canary_event_material as _validate_event_material,
)
from app.services.cache_target_boundary_evidence import (
    validate_canary_final_head as _validate_final_head,
)
from app.services.cache_target_boundary_evidence import (
    validate_stored_canary_run as _validate_existing_run,
)
from app.services.cache_target_initial_cutover import read_cache_target_source_identity

_LOCK_NAMESPACE = 1263816009
_LOCK_RESOURCE = 42
_RESUMABLE_FAILURES = frozenset(
    {
        "active_run_conflict",
        "canary_lock_busy",
        "causal_wait_timeout",
        "final_convergence_timeout",
        "final_snapshot_unavailable",
        "run_already_failed",
    }
)
_FINALIZATION_TABLE_LOCK = text(
    "LOCK TABLE "
    "app.ktm_cache_target_consumers, "
    "app.ktm_cache_target_commands, "
    "app.ktm_cache_target_heads, "
    "app.ktm_cache_target_events, "
    "app.ktm_cache_target_event_claims, "
    "app.ktm_cache_target_event_claim_items "
    "IN SHARE MODE"
)


@dataclass(frozen=True, slots=True)
class CacheTargetCanaryReceipt:
    status: Literal["succeeded"]
    run_id: uuid.UUID
    target_poi_id: uuid.UUID
    put_command_id: uuid.UUID
    delete_command_id: uuid.UUID
    put_event_id: uuid.UUID
    delete_event_id: uuid.UUID
    put_generation: int
    delete_generation: int
    put_relay_order: int
    delete_relay_order: int
    baseline_cache_generation: int
    put_cache_generation: int
    final_cache_generation: int
    final_restore_epoch: int
    final_stream_control_version: int
    final_stream_control_etag: str
    pending_commands: int
    leased_commands: int
    dead_letter_commands: int
    local_applied_cursor: str
    local_remote_acked_cursor: str
    remote_snapshot_high_watermark_cursor: str
    local_count: int
    remote_count: int
    local_merkle_root: str
    remote_merkle_root: str

    def json_object(self) -> dict[str, int | str]:
        return {
            "status": self.status,
            "run_id": str(self.run_id),
            "target_poi_id": str(self.target_poi_id),
            "put_command_id": str(self.put_command_id),
            "delete_command_id": str(self.delete_command_id),
            "put_event_id": str(self.put_event_id),
            "delete_event_id": str(self.delete_event_id),
            "put_generation": self.put_generation,
            "delete_generation": self.delete_generation,
            "put_relay_order": self.put_relay_order,
            "delete_relay_order": self.delete_relay_order,
            "baseline_cache_generation": self.baseline_cache_generation,
            "put_cache_generation": self.put_cache_generation,
            "final_cache_generation": self.final_cache_generation,
            "final_restore_epoch": self.final_restore_epoch,
            "final_stream_control_version": self.final_stream_control_version,
            "final_stream_control_etag": self.final_stream_control_etag,
            "pending_commands": self.pending_commands,
            "leased_commands": self.leased_commands,
            "dead_letter_commands": self.dead_letter_commands,
            "local_applied_cursor": self.local_applied_cursor,
            "local_remote_acked_cursor": self.local_remote_acked_cursor,
            "remote_snapshot_high_watermark_cursor": (self.remote_snapshot_high_watermark_cursor),
            "local_count": self.local_count,
            "remote_count": self.remote_count,
            "local_merkle_root": self.local_merkle_root,
            "remote_merkle_root": self.remote_merkle_root,
        }


@dataclass(frozen=True, slots=True)
class _AppliedObservation:
    event_id: uuid.UUID
    claim_id: uuid.UUID
    relay_order: int
    cache_generation: int
    cursor: str
    event_payload_fingerprint: bytes
    acked_at: datetime
    claim_status: Literal["acked"]
    claim_completed_at: datetime


@asynccontextmanager
async def _canary_lock(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """고정 target 실행을 process 경계를 넘어 하나로 직렬화한다."""
    connection = engine.connect()
    started = False
    try:
        await connection.start()
        started = True
        acquired = await connection.scalar(
            text("SELECT pg_try_advisory_lock(:namespace, :resource)"),
            {"namespace": _LOCK_NAMESPACE, "resource": _LOCK_RESOURCE},
        )
        if acquired is not True:
            raise CacheTargetCanaryFailure("canary_lock_busy", "startup")
        await connection.commit()
        yield connection
    finally:
        if started:

            async def discard_connection() -> None:
                try:
                    await connection.invalidate()
                finally:
                    await connection.close()

            discard = asyncio.create_task(discard_connection())
            try:
                await asyncio.shield(discard)
            except asyncio.CancelledError:
                await discard
                raise


async def _bootstrap_run(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    consumer_id: str,
    run_id: uuid.UUID,
) -> KtmCacheTargetCanaryRun:
    async with session_factory() as db:
        active = await db.scalar(
            select(KtmCacheTargetCanaryRun)
            .where(KtmCacheTargetCanaryRun.status == "running")
            .with_for_update()
        )
        if active is not None and active.run_id != run_id:
            raise CacheTargetCanaryFailure("active_run_conflict", "startup")
        existing = await db.scalar(
            select(KtmCacheTargetCanaryRun)
            .where(KtmCacheTargetCanaryRun.run_id == run_id)
            .with_for_update()
        )
        if existing is not None:
            if existing.status == "failed":
                raise CacheTargetCanaryFailure("run_already_failed", existing.phase)
            await _validate_existing_run(db, existing, consumer_id=consumer_id)
            return existing

        consumer = _require_ready_consumer(
            await db.scalar(
                select(KtmCacheTargetConsumer)
                .where(KtmCacheTargetConsumer.consumer_id == consumer_id)
                .with_for_update()
            ),
            phase="startup",
        )
        if (
            not consumer.local_applied_cursor
            or consumer.local_applied_cursor != consumer.remote_acked_cursor
        ):
            raise CacheTargetCanaryFailure("consumer_cursor_not_converged", "startup")
        if await _command_backlog(db) != (0, 0, 0):
            raise CacheTargetCanaryFailure("command_backlog_not_empty", "startup")

        latest = await db.scalar(
            select(KtmCacheTargetCanaryRun)
            .order_by(KtmCacheTargetCanaryRun.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        head = await db.scalar(
            select(KtmCacheTargetHead)
            .where(KtmCacheTargetHead.poi_id == STABLE_TARGET_ID)
            .with_for_update()
        )
        deleted_fingerprint = cache_target_source_fingerprint(_DELETED_SOURCE)
        if latest is None:
            if head is not None:
                raise CacheTargetCanaryFailure("foreign_stable_target", "startup")
        elif (
            latest.status != "succeeded"
            or head is None
            or head.desired_state != "deleted"
            or head.source_generation != latest.delete_generation
            or head.source_payload_fingerprint != deleted_fingerprint
            or head.remote_status != "deleted"
            or head.remote_source_generation != latest.delete_generation
            or head.remote_etag is not None
        ):
            raise CacheTargetCanaryFailure("previous_run_not_clean", "startup")

        baseline = await read_cache_target_source_identity(db)
        generation = 1 if head is None else head.source_generation + 1
        active_fingerprint = cache_target_source_fingerprint(_ACTIVE_SOURCE)
        if head is None:
            head = KtmCacheTargetHead(
                poi_id=STABLE_TARGET_ID,
                external_system="pinvi",
                target_key=str(STABLE_TARGET_ID),
                desired_state="active",
                source_generation=generation,
                source_payload_fingerprint=active_fingerprint,
                lon=Decimal("127"),
                lat=Decimal("37"),
                radius_km=Decimal("5"),
                update_enabled=True,
            )
            db.add(head)
            await db.flush()
        else:
            head.desired_state = "active"
            head.source_generation = generation
            head.source_payload_fingerprint = active_fingerprint
            head.lon = Decimal("127")
            head.lat = Decimal("37")
            head.radius_km = Decimal("5")
            head.update_enabled = True

        put_command_id = _command_id(run_id, "put")
        command = KtmCacheTargetCommand(
            command_id=put_command_id,
            poi_id=STABLE_TARGET_ID,
            operation="put",
            source_generation=generation,
            payload=_source_payload(_ACTIVE_SOURCE),
            payload_fingerprint=active_fingerprint,
            status="pending",
        )
        db.add(command)
        await db.flush()
        run = KtmCacheTargetCanaryRun(
            run_id=run_id,
            target_poi_id=STABLE_TARGET_ID,
            consumer_id=consumer_id,
            status="running",
            phase="put_enqueued",
            put_command_id=put_command_id,
            put_generation=generation,
            delete_generation=generation + 1,
            put_source_payload_fingerprint=active_fingerprint,
            delete_source_payload_fingerprint=deleted_fingerprint,
            baseline_cache_generation=consumer.feature_cache_generation,
            baseline_cursor=consumer.local_applied_cursor,
            baseline_count=baseline.count,
            baseline_merkle_root=bytes.fromhex(baseline.merkle_root),
        )
        db.add(run)
        await db.commit()
        return run


async def _observe_acknowledged_event(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    consumer_id: str,
    run_id: uuid.UUID,
    operation: Literal["put", "delete"],
) -> _AppliedObservation | None:
    async with session_factory() as db:
        run = await db.get(KtmCacheTargetCanaryRun, run_id)
        if run is None or run.status != "running":
            raise CacheTargetCanaryFailure("run_not_running", "poll")
        generation = run.put_generation if operation == "put" else run.delete_generation
        command_id = run.put_command_id if operation == "put" else run.delete_command_id
        if command_id is None:
            raise CacheTargetCanaryFailure("run_material_mismatch", run.phase)
        command = _validate_command(
            await db.get(KtmCacheTargetCommand, command_id),
            run_id=run_id,
            operation=operation,
            generation=generation,
            phase=run.phase,
        )
        if command.status in {"dead_letter", "superseded"}:
            raise CacheTargetCanaryFailure(f"command_{command.status}", run.phase)

        events = list(
            await db.scalars(
                select(KtmCacheTargetEvent)
                .where(
                    KtmCacheTargetEvent.event_type == "cache_target.state_applied",
                    KtmCacheTargetEvent.target_key == str(STABLE_TARGET_ID),
                    KtmCacheTargetEvent.source_generation == generation,
                    KtmCacheTargetEvent.payload.contains({"source_event_id": str(command_id)}),
                )
                .order_by(KtmCacheTargetEvent.relay_order)
                .limit(2)
            )
        )
        if not events:
            return None
        if len(events) != 1:
            raise CacheTargetCanaryFailure("event_identity_not_unique", run.phase)
        event = _validate_event_material(
            events[0],
            command_id=command_id,
            operation=operation,
            generation=generation,
            phase=run.phase,
        )
        claim_item = await db.scalar(
            select(KtmCacheTargetEventClaimItem)
            .where(
                KtmCacheTargetEventClaimItem.event_id == event.event_id,
                KtmCacheTargetEventClaimItem.acked_at.is_not(None),
            )
            .order_by(KtmCacheTargetEventClaimItem.acked_at.desc())
            .limit(1)
        )
        if claim_item is None:
            return None
        claim = await db.get(KtmCacheTargetEventClaim, claim_item.claim_id)
        if (
            claim is None
            or claim.consumer_id != consumer_id
            or claim.status != "acked"
            or not claim.acked_through_cursor
            or claim.completed_at is None
            or claim_item.payload_fingerprint != event.payload_fingerprint
        ):
            raise CacheTargetCanaryFailure("ack_provenance_mismatch", run.phase)
        consumer = _require_ready_consumer(
            await db.get(KtmCacheTargetConsumer, consumer_id),
            phase=run.phase,
        )
        if (
            consumer.active_restore_epoch != event.restore_epoch
            or not consumer.local_applied_cursor
            or consumer.local_applied_cursor != consumer.remote_acked_cursor
        ):
            return None
        minimum_generation = (
            run.baseline_cache_generation
            if operation == "put"
            else (run.put_cache_generation or run.baseline_cache_generation)
        )
        if consumer.feature_cache_generation <= minimum_generation:
            return None
        if command.status != "succeeded":
            return None
        assert claim_item.acked_at is not None
        assert claim.completed_at is not None
        return _AppliedObservation(
            event_id=event.event_id,
            claim_id=claim_item.claim_id,
            relay_order=event.relay_order,
            cache_generation=consumer.feature_cache_generation,
            cursor=claim_item.delivery_cursor,
            event_payload_fingerprint=event.payload_fingerprint,
            acked_at=claim_item.acked_at,
            claim_status="acked",
            claim_completed_at=claim.completed_at,
        )


async def _wait_for_event(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    consumer_id: str,
    run_id: uuid.UUID,
    operation: Literal["put", "delete"],
    deadline: float,
    poll_seconds: float,
) -> _AppliedObservation:
    while True:
        observation = await _observe_acknowledged_event(
            session_factory,
            consumer_id=consumer_id,
            run_id=run_id,
            operation=operation,
        )
        if observation is not None:
            return observation
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            phase = "put_enqueued" if operation == "put" else "delete_enqueued"
            raise CacheTargetCanaryFailure("causal_wait_timeout", phase)
        await asyncio.sleep(min(poll_seconds, remaining))


async def _record_observation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    operation: Literal["put", "delete"],
    observation: _AppliedObservation,
) -> None:
    expected_phase = "put_enqueued" if operation == "put" else "delete_enqueued"
    next_phase = "put_applied" if operation == "put" else "delete_applied"
    async with session_factory() as db:
        run = await db.scalar(
            select(KtmCacheTargetCanaryRun)
            .where(KtmCacheTargetCanaryRun.run_id == run_id)
            .with_for_update()
        )
        if run is None or run.status != "running":
            raise CacheTargetCanaryFailure("run_not_running", expected_phase)
        if _PHASES[run.phase] >= _PHASES[next_phase]:
            return
        if run.phase != expected_phase:
            raise CacheTargetCanaryFailure("phase_transition_mismatch", run.phase)
        if operation == "put":
            run.put_event_id = observation.event_id
            run.put_claim_id = observation.claim_id
            run.put_relay_order = observation.relay_order
            run.put_cache_generation = observation.cache_generation
            run.put_cursor = observation.cursor
            run.put_event_payload_fingerprint = observation.event_payload_fingerprint
            run.put_claim_status = observation.claim_status
            run.put_acked_at = observation.acked_at
            run.put_claim_completed_at = observation.claim_completed_at
        else:
            run.delete_event_id = observation.event_id
            run.delete_claim_id = observation.claim_id
            run.delete_relay_order = observation.relay_order
            run.delete_cursor = observation.cursor
            run.delete_event_payload_fingerprint = observation.event_payload_fingerprint
            run.delete_claim_status = observation.claim_status
            run.delete_acked_at = observation.acked_at
            run.delete_claim_completed_at = observation.claim_completed_at
        run.phase = next_phase
        await db.commit()


async def _enqueue_delete(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
) -> None:
    async with session_factory() as db:
        run = await db.scalar(
            select(KtmCacheTargetCanaryRun)
            .where(KtmCacheTargetCanaryRun.run_id == run_id)
            .with_for_update()
        )
        if run is None or run.status != "running":
            raise CacheTargetCanaryFailure("run_not_running", "put_applied")
        if _PHASES[run.phase] >= _PHASES["delete_enqueued"]:
            return
        if run.phase != "put_applied":
            raise CacheTargetCanaryFailure("phase_transition_mismatch", run.phase)
        head = await db.scalar(
            select(KtmCacheTargetHead)
            .where(KtmCacheTargetHead.poi_id == STABLE_TARGET_ID)
            .with_for_update()
        )
        if (
            head is None
            or head.desired_state != "active"
            or head.source_generation != run.put_generation
            or head.remote_status != "active"
            or head.remote_source_generation != run.put_generation
            or head.remote_etag is None
        ):
            raise CacheTargetCanaryFailure("put_head_not_applied", run.phase)
        deleted_fingerprint = cache_target_source_fingerprint(_DELETED_SOURCE)
        head.desired_state = "deleted"
        head.source_generation = run.delete_generation
        head.source_payload_fingerprint = deleted_fingerprint
        head.lon = None
        head.lat = None
        head.radius_km = Decimal("5")
        head.update_enabled = False
        delete_command_id = _command_id(run_id, "delete")
        command = KtmCacheTargetCommand(
            command_id=delete_command_id,
            poi_id=STABLE_TARGET_ID,
            operation="delete",
            source_generation=run.delete_generation,
            payload=_source_payload(_DELETED_SOURCE),
            payload_fingerprint=deleted_fingerprint,
            status="pending",
        )
        db.add(command)
        # ORM relationship을 의도적으로 두지 않으므로 command FK owner를 먼저 고정한다.
        await db.flush()
        run.delete_command_id = delete_command_id
        run.phase = "delete_enqueued"
        await db.commit()


def _receipt(run: KtmCacheTargetCanaryRun) -> CacheTargetCanaryReceipt:
    required = (
        run.delete_command_id,
        run.put_event_id,
        run.delete_event_id,
        run.put_relay_order,
        run.delete_relay_order,
        run.put_cache_generation,
        run.final_cache_generation,
        run.final_restore_epoch,
        run.final_stream_control_version,
        run.final_stream_control_etag,
        run.final_local_applied_cursor,
        run.final_local_remote_acked_cursor,
        run.final_remote_snapshot_high_watermark_cursor,
        run.final_local_count,
        run.final_remote_count,
        run.final_local_merkle_root,
        run.final_remote_merkle_root,
        run.final_pending_commands,
        run.final_leased_commands,
        run.final_dead_letter_commands,
    )
    if any(value is None for value in required):
        raise CacheTargetCanaryFailure("receipt_material_incomplete", run.phase)
    assert run.delete_command_id is not None
    assert run.put_event_id is not None
    assert run.delete_event_id is not None
    assert run.put_relay_order is not None
    assert run.delete_relay_order is not None
    assert run.put_cache_generation is not None
    assert run.final_cache_generation is not None
    assert run.final_restore_epoch is not None
    assert run.final_stream_control_version is not None
    assert run.final_stream_control_etag is not None
    assert run.final_local_applied_cursor is not None
    assert run.final_local_remote_acked_cursor is not None
    assert run.final_remote_snapshot_high_watermark_cursor is not None
    assert run.final_local_count is not None
    assert run.final_remote_count is not None
    assert run.final_local_merkle_root is not None
    assert run.final_remote_merkle_root is not None
    assert run.final_pending_commands is not None
    assert run.final_leased_commands is not None
    assert run.final_dead_letter_commands is not None
    return CacheTargetCanaryReceipt(
        status="succeeded",
        run_id=run.run_id,
        target_poi_id=run.target_poi_id,
        put_command_id=run.put_command_id,
        delete_command_id=run.delete_command_id,
        put_event_id=run.put_event_id,
        delete_event_id=run.delete_event_id,
        put_generation=run.put_generation,
        delete_generation=run.delete_generation,
        put_relay_order=run.put_relay_order,
        delete_relay_order=run.delete_relay_order,
        baseline_cache_generation=run.baseline_cache_generation,
        put_cache_generation=run.put_cache_generation,
        final_cache_generation=run.final_cache_generation,
        final_restore_epoch=run.final_restore_epoch,
        final_stream_control_version=run.final_stream_control_version,
        final_stream_control_etag=run.final_stream_control_etag,
        pending_commands=run.final_pending_commands,
        leased_commands=run.final_leased_commands,
        dead_letter_commands=run.final_dead_letter_commands,
        local_applied_cursor=run.final_local_applied_cursor,
        local_remote_acked_cursor=run.final_local_remote_acked_cursor,
        remote_snapshot_high_watermark_cursor=(run.final_remote_snapshot_high_watermark_cursor),
        local_count=run.final_local_count,
        remote_count=run.final_remote_count,
        local_merkle_root=run.final_local_merkle_root.hex(),
        remote_merkle_root=run.final_remote_merkle_root.hex(),
    )


async def _finish_run(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    consumer_id: str,
    run_id: uuid.UUID,
    consumer_client: CacheTargetServiceClient,
    deadline: float,
) -> CacheTargetCanaryReceipt | None:
    async with session_factory() as db:
        remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
        if deadline <= time.monotonic():
            return None
        await db.execute(
            text("SELECT set_config('lock_timeout', :timeout, true)"),
            {"timeout": f"{remaining_ms}ms"},
        )
        await db.execute(_FINALIZATION_TABLE_LOCK)
        run = await db.scalar(
            select(KtmCacheTargetCanaryRun)
            .where(KtmCacheTargetCanaryRun.run_id == run_id)
            .with_for_update()
        )
        if run is None:
            raise CacheTargetCanaryFailure("run_not_found", "delete_applied")
        completed_replay = run.status == "succeeded" and run.phase == "completed"
        if not completed_replay and (run.status != "running" or run.phase != "delete_applied"):
            raise CacheTargetCanaryFailure("phase_transition_mismatch", run.phase)
        failure_code = "completed_run_drift" if completed_replay else None
        try:
            consumer = _require_ready_consumer(
                await db.scalar(
                    select(KtmCacheTargetConsumer)
                    .where(KtmCacheTargetConsumer.consumer_id == consumer_id)
                    .with_for_update()
                ),
                phase=run.phase,
            )
            await _validate_existing_run(db, run, consumer_id=consumer_id)
        except CacheTargetCanaryFailure:
            if completed_replay:
                raise CacheTargetCanaryFailure("completed_run_drift", run.phase) from None
            raise
        assert consumer.active_restore_epoch is not None
        _validate_final_head(
            await db.scalar(
                select(KtmCacheTargetHead)
                .where(KtmCacheTargetHead.poi_id == STABLE_TARGET_ID)
                .with_for_update()
            ),
            run=run,
            restore_epoch=consumer.active_restore_epoch,
            failure_code=failure_code or "final_head_mismatch",
        )
        if (
            not consumer.local_applied_cursor
            or consumer.local_applied_cursor != consumer.remote_acked_cursor
        ):
            if completed_replay:
                raise CacheTargetCanaryFailure("completed_run_drift", run.phase)
            return None
        backlog = await _command_backlog(db)
        if backlog != (0, 0, 0):
            if completed_replay:
                raise CacheTargetCanaryFailure("completed_run_drift", run.phase)
            return None
        local = await read_cache_target_source_identity(db)
        try:
            stream_before = await consumer_client.get_stream()
            snapshot = await consumer_client.get_snapshot()
            stream_after = await consumer_client.get_stream()
        except (
            CacheTargetContractError,
            CacheTargetNetworkError,
            CacheTargetServiceProblem,
        ) as exc:
            raise CacheTargetCanaryFailure("final_snapshot_unavailable", run.phase) from exc
        except ValidationError:
            raise CacheTargetCanaryFailure("final_snapshot_invalid", run.phase) from None
        try:
            remote_count, remote_root = _snapshot_identity(snapshot)
        except (TypeError, ValueError):
            raise CacheTargetCanaryFailure("final_snapshot_invalid", run.phase) from None
        if remote_count != snapshot.count or remote_root.hex() != snapshot.merkle_root:
            raise CacheTargetCanaryFailure("remote_snapshot_merkle_mismatch", run.phase)
        if stream_before.consumer_id not in {None, consumer_id} or stream_after.consumer_id not in {
            None,
            consumer_id,
        }:
            code = failure_code or "remote_stream_identity_mismatch"
            raise CacheTargetCanaryFailure(code, run.phase)
        remote_control_stable = _stream_control_identity(stream_before) == _stream_control_identity(
            stream_after
        )
        remote_ready = (
            stream_after.state in {"active", "ready"}
            and stream_after.blocked_event_id is None
            and stream_after.active_reconciliation is None
        )
        if not remote_control_stable or not remote_ready:
            if completed_replay:
                raise CacheTargetCanaryFailure("completed_run_drift", run.phase)
            return None
        if snapshot.restore_epoch != stream_after.restore_epoch:
            raise CacheTargetCanaryFailure(
                failure_code or "final_snapshot_invalid",
                run.phase,
            )
        if consumer.active_restore_epoch != stream_after.restore_epoch:
            code = failure_code or "restore_epoch_changed"
            raise CacheTargetCanaryFailure(code, run.phase)
        if consumer.stream_control_etag != stream_after.entity_tag:
            if completed_replay:
                raise CacheTargetCanaryFailure("completed_run_drift", run.phase)
            return None
        if (
            not snapshot.high_watermark_cursor
            or snapshot.high_watermark_cursor != consumer.local_applied_cursor
            or snapshot.high_watermark_cursor != consumer.remote_acked_cursor
        ):
            if completed_replay:
                raise CacheTargetCanaryFailure("completed_run_drift", run.phase)
            return None
        if local.count != remote_count or bytes.fromhex(local.merkle_root) != remote_root:
            if completed_replay:
                raise CacheTargetCanaryFailure("completed_run_drift", run.phase)
            return None
        if completed_replay:
            receipt = _receipt(run)
            if (
                run.canary_provenance_sha256 != canary_provenance_sha256(run)
                or run.final_evidence_sha256 != canary_final_evidence_sha256(run)
                or consumer.feature_cache_generation != run.final_cache_generation
                or stream_after.restore_epoch != run.final_restore_epoch
                or stream_after.control_version != run.final_stream_control_version
                or stream_after.entity_tag != run.final_stream_control_etag
                or consumer.local_applied_cursor != run.final_local_applied_cursor
                or consumer.remote_acked_cursor != run.final_local_remote_acked_cursor
                or snapshot.high_watermark_cursor != run.final_remote_snapshot_high_watermark_cursor
                or local.count != run.final_local_count
                or remote_count != run.final_remote_count
                or bytes.fromhex(local.merkle_root) != run.final_local_merkle_root
                or remote_root != run.final_remote_merkle_root
                or backlog
                != (
                    run.final_pending_commands,
                    run.final_leased_commands,
                    run.final_dead_letter_commands,
                )
            ):
                raise CacheTargetCanaryFailure("completed_run_drift", run.phase)
            return receipt
        if run.put_cache_generation is None:
            raise CacheTargetCanaryFailure("run_material_mismatch", run.phase)
        if consumer.feature_cache_generation <= run.put_cache_generation:
            return None
        run.status = "succeeded"
        run.phase = "completed"
        run.final_cache_generation = consumer.feature_cache_generation
        run.final_restore_epoch = stream_after.restore_epoch
        run.final_stream_control_version = stream_after.control_version
        run.final_stream_control_etag = stream_after.entity_tag
        run.final_local_applied_cursor = consumer.local_applied_cursor
        run.final_local_remote_acked_cursor = consumer.remote_acked_cursor
        run.final_remote_snapshot_high_watermark_cursor = snapshot.high_watermark_cursor
        run.final_local_count = local.count
        run.final_remote_count = remote_count
        run.final_local_merkle_root = bytes.fromhex(local.merkle_root)
        run.final_remote_merkle_root = remote_root
        (
            run.final_pending_commands,
            run.final_leased_commands,
            run.final_dead_letter_commands,
        ) = backlog
        run.completed_at = datetime.now(UTC)
        run.canary_provenance_sha256 = canary_provenance_sha256(run)
        run.final_evidence_sha256 = canary_final_evidence_sha256(run)
        await db.commit()
        return _receipt(run)


async def _wait_for_final_convergence(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    consumer_id: str,
    run_id: uuid.UUID,
    consumer_client: CacheTargetServiceClient,
    deadline: float,
    poll_seconds: float,
) -> CacheTargetCanaryReceipt:
    while True:
        try:
            receipt = await _finish_run(
                session_factory,
                consumer_id=consumer_id,
                run_id=run_id,
                consumer_client=consumer_client,
                deadline=deadline,
            )
        except CacheTargetCanaryFailure as exc:
            if exc.code != "final_snapshot_unavailable":
                raise
            receipt = None
        if receipt is not None:
            return receipt
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CacheTargetCanaryFailure("final_convergence_timeout", "delete_applied")
        await asyncio.sleep(min(poll_seconds, remaining))


async def _mark_failed(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    code: str,
) -> None:
    async with session_factory() as db:
        run = await db.scalar(
            select(KtmCacheTargetCanaryRun)
            .where(KtmCacheTargetCanaryRun.run_id == run_id)
            .with_for_update()
        )
        if run is not None and run.status == "running":
            run.status = "failed"
            run.terminal_error_code = code
            run.failed_at = datetime.now(UTC)
            await db.commit()


async def _run_locked(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    consumer_client: CacheTargetServiceClient,
    consumer_id: str,
    run_id: uuid.UUID,
    deadline: float,
    poll_seconds: float,
) -> CacheTargetCanaryReceipt:
    run = await _bootstrap_run(session_factory, consumer_id=consumer_id, run_id=run_id)
    if run.status == "succeeded":
        receipt = await _finish_run(
            session_factory,
            consumer_id=consumer_id,
            run_id=run_id,
            consumer_client=consumer_client,
            deadline=deadline,
        )
        if receipt is None:
            raise CacheTargetCanaryFailure("completed_run_drift", run.phase)
        return receipt
    if run.phase == "put_enqueued":
        observation = await _wait_for_event(
            session_factory,
            consumer_id=consumer_id,
            run_id=run_id,
            operation="put",
            deadline=deadline,
            poll_seconds=poll_seconds,
        )
        await _record_observation(
            session_factory,
            run_id=run_id,
            operation="put",
            observation=observation,
        )
        run.phase = "put_applied"
    if run.phase == "put_applied":
        await _enqueue_delete(session_factory, run_id=run_id)
        run.phase = "delete_enqueued"
    if run.phase == "delete_enqueued":
        observation = await _wait_for_event(
            session_factory,
            consumer_id=consumer_id,
            run_id=run_id,
            operation="delete",
            deadline=deadline,
            poll_seconds=poll_seconds,
        )
        await _record_observation(
            session_factory,
            run_id=run_id,
            operation="delete",
            observation=observation,
        )
        run.phase = "delete_applied"
    if run.phase != "delete_applied":
        raise CacheTargetCanaryFailure("phase_transition_mismatch", run.phase)
    return await _wait_for_final_convergence(
        session_factory,
        consumer_id=consumer_id,
        run_id=run_id,
        consumer_client=consumer_client,
        deadline=deadline,
        poll_seconds=poll_seconds,
    )


async def run_cache_target_causal_canary(
    session_factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    *,
    consumer_client: CacheTargetServiceClient,
    consumer_id: str,
    run_id: uuid.UUID,
    timeout_seconds: float,
    poll_seconds: float = 0.5,
) -> CacheTargetCanaryReceipt:
    """같은 run ID를 crash-safe하게 재개하고 secret-free receipt를 반환한다."""
    if (
        not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
        or not math.isfinite(poll_seconds)
        or poll_seconds <= 0
    ):
        raise ValueError("canary timeout/poll은 finite 양수여야 합니다.")
    deadline = time.monotonic() + timeout_seconds
    async with _canary_lock(engine):
        try:
            return await _run_locked(
                session_factory,
                consumer_client=consumer_client,
                consumer_id=consumer_id,
                run_id=run_id,
                deadline=deadline,
                poll_seconds=poll_seconds,
            )
        except CacheTargetCanaryFailure as exc:
            if exc.code not in _RESUMABLE_FAILURES:
                await _mark_failed(session_factory, run_id=run_id, code=exc.code)
            raise
