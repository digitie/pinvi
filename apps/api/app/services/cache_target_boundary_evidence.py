"""cache-target canary의 canonical provenance/final evidence digest."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map_cache_target import CacheTargetStreamState
from app.core.cache_target_contract import (
    CacheTargetMerkleRow,
    CacheTargetSource,
    DeletedCacheTargetSource,
    cache_target_snapshot_merkle_root,
    cache_target_source_fingerprint,
    canonical_cache_target_source_bytes,
    normalize_active_cache_target_source,
)
from app.models.cache_target_sync import (
    KtmCacheTargetCanaryRun,
    KtmCacheTargetCommand,
    KtmCacheTargetConsumer,
    KtmCacheTargetEvent,
    KtmCacheTargetEventClaim,
    KtmCacheTargetEventClaimItem,
    KtmCacheTargetHead,
)
from app.services.cache_target_event_consumer import CacheTargetSnapshot

STABLE_TARGET_ID = uuid.UUID("15f98050-27d7-5f85-be21-dc53eded5d7d")
DELETED_SOURCE = DeletedCacheTargetSource()
ACTIVE_SOURCE = normalize_active_cache_target_source(
    lon=Decimal("127"),
    lat=Decimal("37"),
    radius_km=Decimal("5"),
    update_enabled=True,
)
_PUT_COMMAND_NAMESPACE = uuid.UUID("26ed64a8-1024-5cb1-aaed-185b507647c2")
_DELETE_COMMAND_NAMESPACE = uuid.UUID("34b214b2-b76f-53ef-b990-3742bcb1c998")
CANARY_PHASES = {
    "put_enqueued": 0,
    "put_applied": 1,
    "delete_enqueued": 2,
    "delete_applied": 3,
    "completed": 4,
}


class CacheTargetCanaryFailure(RuntimeError):
    """credential과 raw 응답을 포함하지 않는 typed terminal failure."""

    def __init__(self, code: str, phase: str) -> None:
        super().__init__(code)
        self.code = code
        self.phase = phase


def cache_target_source_payload(source: CacheTargetSource) -> dict[str, object]:
    decoded = json.loads(canonical_cache_target_source_bytes(source))
    if not isinstance(decoded, dict):
        raise AssertionError("canonical cache target source는 JSON object여야 합니다.")
    return decoded


def cache_target_canary_command_id(
    run_id: uuid.UUID,
    operation: Literal["put", "delete"],
) -> uuid.UUID:
    namespace = _PUT_COMMAND_NAMESPACE if operation == "put" else _DELETE_COMMAND_NAMESPACE
    return uuid.uuid5(namespace, str(run_id))


def validate_canary_command(
    command: KtmCacheTargetCommand | None,
    *,
    run_id: uuid.UUID,
    operation: Literal["put", "delete"],
    generation: int,
    phase: str,
) -> KtmCacheTargetCommand:
    source = ACTIVE_SOURCE if operation == "put" else DELETED_SOURCE
    expected_payload = cache_target_source_payload(source)
    expected_fingerprint = cache_target_source_fingerprint(source)
    if (
        command is None
        or command.command_id != cache_target_canary_command_id(run_id, operation)
        or command.poi_id != STABLE_TARGET_ID
        or command.operation != operation
        or command.source_generation != generation
        or command.payload != expected_payload
        or command.payload_fingerprint != expected_fingerprint
    ):
        raise CacheTargetCanaryFailure("command_identity_mismatch", phase)
    return command


def validate_canary_event_material(
    event: KtmCacheTargetEvent | None,
    *,
    command_id: uuid.UUID,
    operation: Literal["put", "delete"],
    generation: int,
    phase: str,
    event_id: uuid.UUID | None = None,
    relay_order: int | None = None,
) -> KtmCacheTargetEvent:
    source = ACTIVE_SOURCE if operation == "put" else DELETED_SOURCE
    expected_state = "active" if operation == "put" else "deleted"
    if (
        event is None
        or (event_id is not None and event.event_id != event_id)
        or event.event_type != "cache_target.state_applied"
        or event.external_system != "pinvi"
        or event.target_key != str(STABLE_TARGET_ID)
        or event.source_generation != generation
        or event.source_payload_fingerprint != cache_target_source_fingerprint(source)
        or event.payload.get("version") != "cache-target-event-v1"
        or event.payload.get("state") != expected_state
        or event.payload.get("source_event_id") != str(command_id)
        or event.restore_epoch <= 0
        or event.applied_at is None
        or (relay_order is not None and event.relay_order != relay_order)
    ):
        raise CacheTargetCanaryFailure("event_provenance_mismatch", phase)
    target = event.payload.get("target")
    if operation == "put":
        if not isinstance(target, dict) or target.get("target_id") != str(event.target_id):
            raise CacheTargetCanaryFailure("event_provenance_mismatch", phase)
        if (
            target.get("coord") != {"lon_e6": 127000000, "lat_e6": 37000000}
            or target.get("radius_m") != 5000
            or target.get("update_enabled") is not True
        ):
            raise CacheTargetCanaryFailure("event_provenance_mismatch", phase)
    elif target is not None:
        raise CacheTargetCanaryFailure("event_provenance_mismatch", phase)
    return event


async def _validate_stored_canary_observation(
    db: AsyncSession,
    run: KtmCacheTargetCanaryRun,
    *,
    consumer_id: str,
    operation: Literal["put", "delete"],
) -> None:
    event_id = run.put_event_id if operation == "put" else run.delete_event_id
    claim_id = run.put_claim_id if operation == "put" else run.delete_claim_id
    relay_order = run.put_relay_order if operation == "put" else run.delete_relay_order
    cursor = run.put_cursor if operation == "put" else run.delete_cursor
    command_id = run.put_command_id if operation == "put" else run.delete_command_id
    generation = run.put_generation if operation == "put" else run.delete_generation
    source_fingerprint = (
        run.put_source_payload_fingerprint
        if operation == "put"
        else run.delete_source_payload_fingerprint
    )
    event_payload_fingerprint = (
        run.put_event_payload_fingerprint
        if operation == "put"
        else run.delete_event_payload_fingerprint
    )
    claim_status = run.put_claim_status if operation == "put" else run.delete_claim_status
    acked_at = run.put_acked_at if operation == "put" else run.delete_acked_at
    claim_completed_at = (
        run.put_claim_completed_at if operation == "put" else run.delete_claim_completed_at
    )
    if None in (
        event_id,
        claim_id,
        relay_order,
        cursor,
        command_id,
        event_payload_fingerprint,
        claim_status,
        acked_at,
        claim_completed_at,
    ):
        raise CacheTargetCanaryFailure("run_material_mismatch", run.phase)
    assert event_id is not None
    assert claim_id is not None
    assert relay_order is not None
    assert cursor is not None
    assert command_id is not None
    assert event_payload_fingerprint is not None
    assert acked_at is not None
    assert claim_completed_at is not None
    event = validate_canary_event_material(
        await db.scalar(
            select(KtmCacheTargetEvent)
            .where(KtmCacheTargetEvent.event_id == event_id)
            .with_for_update()
        ),
        command_id=command_id,
        operation=operation,
        generation=generation,
        phase=run.phase,
        event_id=event_id,
        relay_order=relay_order,
    )
    if (
        event.source_event_id != command_id
        or event.source_payload_fingerprint != source_fingerprint
        or event.payload_fingerprint != event_payload_fingerprint
    ):
        raise CacheTargetCanaryFailure("event_provenance_mismatch", run.phase)
    item = await db.scalar(
        select(KtmCacheTargetEventClaimItem)
        .where(
            KtmCacheTargetEventClaimItem.claim_id == claim_id,
            KtmCacheTargetEventClaimItem.event_id == event_id,
        )
        .with_for_update()
    )
    claim = await db.scalar(
        select(KtmCacheTargetEventClaim)
        .where(KtmCacheTargetEventClaim.claim_id == claim_id)
        .with_for_update()
    )
    consumer = await db.scalar(
        select(KtmCacheTargetConsumer)
        .where(KtmCacheTargetConsumer.consumer_id == consumer_id)
        .with_for_update()
    )
    if consumer is None or consumer.active_restore_epoch != event.restore_epoch:
        raise CacheTargetCanaryFailure("event_provenance_mismatch", run.phase)
    if (
        item is None
        or item.acked_at != acked_at
        or item.delivery_cursor != cursor
        or item.payload_fingerprint != event_payload_fingerprint
        or claim is None
        or claim.consumer_id != consumer_id
        or claim.status != claim_status
        or claim_status != "acked"
        or claim.acked_through_cursor != cursor
        or claim.completed_at != claim_completed_at
    ):
        raise CacheTargetCanaryFailure("ack_provenance_mismatch", run.phase)


async def validate_stored_canary_run(
    db: AsyncSession,
    run: KtmCacheTargetCanaryRun,
    *,
    consumer_id: str,
) -> None:
    """저장된 canary command→event→terminal ACK provenance를 다시 검증한다."""
    if run.consumer_id != consumer_id:
        raise CacheTargetCanaryFailure("run_material_mismatch", run.phase)
    expected_put_fingerprint = cache_target_source_fingerprint(ACTIVE_SOURCE)
    expected_delete_fingerprint = cache_target_source_fingerprint(DELETED_SOURCE)
    if (
        run.put_source_payload_fingerprint != expected_put_fingerprint
        or run.delete_source_payload_fingerprint != expected_delete_fingerprint
    ):
        raise CacheTargetCanaryFailure("command_identity_mismatch", run.phase)
    put_command = validate_canary_command(
        await db.scalar(
            select(KtmCacheTargetCommand)
            .where(KtmCacheTargetCommand.command_id == run.put_command_id)
            .with_for_update()
        ),
        run_id=run.run_id,
        operation="put",
        generation=run.put_generation,
        phase=run.phase,
    )
    if (
        CANARY_PHASES[run.phase] >= CANARY_PHASES["put_applied"]
        and put_command.status != "succeeded"
    ):
        raise CacheTargetCanaryFailure("command_provenance_mismatch", run.phase)
    if CANARY_PHASES[run.phase] >= CANARY_PHASES["delete_enqueued"]:
        if run.delete_command_id is None:
            raise CacheTargetCanaryFailure("run_material_mismatch", run.phase)
        delete_command = validate_canary_command(
            await db.scalar(
                select(KtmCacheTargetCommand)
                .where(KtmCacheTargetCommand.command_id == run.delete_command_id)
                .with_for_update()
            ),
            run_id=run.run_id,
            operation="delete",
            generation=run.delete_generation,
            phase=run.phase,
        )
        if (
            CANARY_PHASES[run.phase] >= CANARY_PHASES["delete_applied"]
            and delete_command.status != "succeeded"
        ):
            raise CacheTargetCanaryFailure("command_provenance_mismatch", run.phase)
    if CANARY_PHASES[run.phase] >= CANARY_PHASES["put_applied"]:
        await _validate_stored_canary_observation(
            db,
            run,
            consumer_id=consumer_id,
            operation="put",
        )
    if CANARY_PHASES[run.phase] >= CANARY_PHASES["delete_applied"]:
        await _validate_stored_canary_observation(
            db,
            run,
            consumer_id=consumer_id,
            operation="delete",
        )


async def cache_target_command_backlog(db: AsyncSession) -> tuple[int, int, int]:
    counts: list[int] = []
    for status in ("pending", "leased", "dead_letter"):
        count = await db.scalar(
            select(func.count())
            .select_from(KtmCacheTargetCommand)
            .where(KtmCacheTargetCommand.status == status)
        )
        counts.append(int(count or 0))
    return counts[0], counts[1], counts[2]


def require_ready_cache_target_consumer(
    consumer: KtmCacheTargetConsumer | None,
    *,
    phase: str,
) -> KtmCacheTargetConsumer:
    if (
        consumer is None
        or not consumer.ready
        or consumer.reconcile_status != "matched"
        or consumer.active_restore_epoch is None
    ):
        raise CacheTargetCanaryFailure("consumer_not_ready", phase)
    return consumer


def cache_target_snapshot_identity(snapshot: CacheTargetSnapshot) -> tuple[int, bytes]:
    rows = [
        CacheTargetMerkleRow(
            external_system=item.external_system,
            target_key=item.target_key,
            state=item.state,
            source_generation=item.source_generation,
            source_payload_fingerprint=bytes.fromhex(item.source_payload_fingerprint),
        )
        for item in snapshot.items
    ]
    return len(rows), cache_target_snapshot_merkle_root(rows)


def cache_target_stream_control_identity(stream: CacheTargetStreamState) -> tuple[object, ...]:
    return (
        stream.external_system,
        stream.restore_epoch,
        stream.control_version,
        stream.entity_tag,
        stream.state,
        stream.consumer_id,
        stream.blocked_event_id,
        stream.active_reconciliation,
    )


def validate_canary_final_head(
    head: KtmCacheTargetHead | None,
    *,
    run: KtmCacheTargetCanaryRun,
    restore_epoch: int,
    failure_code: str = "final_head_mismatch",
) -> None:
    if (
        head is None
        or head.poi_id != STABLE_TARGET_ID
        or head.external_system != "pinvi"
        or head.target_key != str(STABLE_TARGET_ID)
        or head.desired_state != "deleted"
        or head.source_generation != run.delete_generation
        or head.source_payload_fingerprint != cache_target_source_fingerprint(DELETED_SOURCE)
        or head.lon is not None
        or head.lat is not None
        or head.radius_km != Decimal("5")
        or head.update_enabled is not False
        or head.remote_target_id is not None
        or head.remote_etag is not None
        or head.remote_restore_epoch != restore_epoch
        or head.remote_source_generation != run.delete_generation
        or head.remote_target_sequence is None
        or head.remote_status != "deleted"
    ):
        raise CacheTargetCanaryFailure(failure_code, run.phase)


def validate_initial_state_event(
    *,
    command: KtmCacheTargetCommand,
    event: KtmCacheTargetEvent | None,
    head: KtmCacheTargetHead | None,
    restore_epoch: int,
) -> None:
    payload = command.payload
    if (
        set(payload) != {"version", "state", "coord", "radius_m", "update_enabled"}
        or payload.get("version") != "cache-target-source-v1"
        or payload.get("state") != "active"
        or not isinstance(payload.get("coord"), dict)
        or not isinstance(payload.get("radius_m"), int)
        or not isinstance(payload.get("update_enabled"), bool)
        or canonical_sha256(payload) != command.payload_fingerprint
    ):
        raise ValueError("initial command payload is invalid")
    coord = payload["coord"]
    assert isinstance(coord, dict)
    lon_e6 = coord.get("lon_e6")
    lat_e6 = coord.get("lat_e6")
    radius_m = payload["radius_m"]
    update_enabled = payload["update_enabled"]
    if (
        isinstance(lon_e6, bool)
        or not isinstance(lon_e6, int)
        or isinstance(lat_e6, bool)
        or not isinstance(lat_e6, int)
        or head is None
        or head.poi_id != command.poi_id
        or head.external_system != "pinvi"
        or head.target_key != str(command.poi_id)
        or head.desired_state != "active"
        or head.source_generation != command.source_generation
        or head.source_payload_fingerprint != command.payload_fingerprint
        or head.lon != Decimal(lon_e6) / Decimal(1_000_000)
        or head.lat != Decimal(lat_e6) / Decimal(1_000_000)
        or head.radius_km != Decimal(radius_m) / Decimal(1_000)
        or head.update_enabled != update_enabled
        or head.remote_target_id is None
        or head.remote_etag is None
        or head.remote_restore_epoch != restore_epoch
        or head.remote_source_generation != command.source_generation
        or head.remote_target_sequence is None
        or head.remote_status != "active"
    ):
        raise ValueError("initial command head is invalid")
    event_payload = {
        "version": "cache-target-event-v1",
        "state": "active",
        "source_event_id": str(command.command_id),
        "target": {
            "target_id": str(head.remote_target_id),
            "entity_tag": head.remote_etag,
            "coord": {"lon_e6": lon_e6, "lat_e6": lat_e6},
            "radius_m": radius_m,
            "update_enabled": update_enabled,
        },
    }
    if (
        event is None
        or event.event_type != "cache_target.state_applied"
        or event.external_system != "pinvi"
        or event.target_key != str(command.poi_id)
        or event.target_id != head.remote_target_id
        or event.restore_epoch != restore_epoch
        or event.source_event_id != command.command_id
        or event.source_generation != command.source_generation
        or event.target_sequence != head.remote_target_sequence
        or event.source_payload_fingerprint != command.payload_fingerprint
        or event.payload != event_payload
        or event.payload_fingerprint != canonical_sha256(event_payload)
        or event.applied_at is None
    ):
        raise ValueError("initial event provenance is invalid")


def _required(value: Any, name: str) -> Any:
    if value is None:
        raise ValueError(f"{name} is missing")
    return value


def _hex(value: bytes | None, name: str) -> str:
    raw = _required(value, name)
    if not isinstance(raw, bytes) or len(raw) != 32:
        raise ValueError(f"{name} is invalid")
    return raw.hex()


def _datetime(value: datetime | None, name: str) -> str:
    observed = _required(value, name)
    if not isinstance(observed, datetime) or observed.tzinfo is None:
        raise ValueError(f"{name} is invalid")
    return observed.isoformat()


def canonical_sha256(value: object) -> bytes:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(payload).digest()


def canary_provenance_sha256(run: KtmCacheTargetCanaryRun) -> bytes:
    """command→event→terminal ACK의 저장된 exact provenance를 digest한다."""
    return canonical_sha256(
        {
            "consumer_id": run.consumer_id,
            "delete": {
                "acked_at": _datetime(run.delete_acked_at, "delete_acked_at"),
                "claim_completed_at": _datetime(
                    run.delete_claim_completed_at, "delete_claim_completed_at"
                ),
                "claim_id": str(_required(run.delete_claim_id, "delete_claim_id")),
                "claim_status": _required(run.delete_claim_status, "delete_claim_status"),
                "command_id": str(_required(run.delete_command_id, "delete_command_id")),
                "cursor": _required(run.delete_cursor, "delete_cursor"),
                "event_id": str(_required(run.delete_event_id, "delete_event_id")),
                "event_payload_fingerprint": _hex(
                    run.delete_event_payload_fingerprint,
                    "delete_event_payload_fingerprint",
                ),
                "generation": run.delete_generation,
                "relay_order": _required(run.delete_relay_order, "delete_relay_order"),
                "source_payload_fingerprint": _hex(
                    run.delete_source_payload_fingerprint,
                    "delete_source_payload_fingerprint",
                ),
            },
            "put": {
                "acked_at": _datetime(run.put_acked_at, "put_acked_at"),
                "claim_completed_at": _datetime(
                    run.put_claim_completed_at, "put_claim_completed_at"
                ),
                "claim_id": str(_required(run.put_claim_id, "put_claim_id")),
                "claim_status": _required(run.put_claim_status, "put_claim_status"),
                "command_id": str(run.put_command_id),
                "cursor": _required(run.put_cursor, "put_cursor"),
                "event_id": str(_required(run.put_event_id, "put_event_id")),
                "event_payload_fingerprint": _hex(
                    run.put_event_payload_fingerprint,
                    "put_event_payload_fingerprint",
                ),
                "generation": run.put_generation,
                "relay_order": _required(run.put_relay_order, "put_relay_order"),
                "source_payload_fingerprint": _hex(
                    run.put_source_payload_fingerprint,
                    "put_source_payload_fingerprint",
                ),
            },
            "run_id": str(run.run_id),
            "target_poi_id": str(run.target_poi_id),
            "version": "pinvi-cache-target-canary-provenance/v1",
        }
    )


def canary_final_evidence_sha256(run: KtmCacheTargetCanaryRun) -> bytes:
    """성공 transaction의 local/remote final evidence를 digest한다."""
    return canonical_sha256(
        {
            "cache_generation": _required(run.final_cache_generation, "final_cache_generation"),
            "command_backlog": {
                "dead_letter": _required(
                    run.final_dead_letter_commands, "final_dead_letter_commands"
                ),
                "leased": _required(run.final_leased_commands, "final_leased_commands"),
                "pending": _required(run.final_pending_commands, "final_pending_commands"),
            },
            "local": {
                "applied_cursor": _required(
                    run.final_local_applied_cursor, "final_local_applied_cursor"
                ),
                "count": _required(run.final_local_count, "final_local_count"),
                "merkle_root": _hex(run.final_local_merkle_root, "final_local_merkle_root"),
                "remote_acked_cursor": _required(
                    run.final_local_remote_acked_cursor,
                    "final_local_remote_acked_cursor",
                ),
            },
            "remote": {
                "count": _required(run.final_remote_count, "final_remote_count"),
                "merkle_root": _hex(run.final_remote_merkle_root, "final_remote_merkle_root"),
                "snapshot_high_watermark_cursor": _required(
                    run.final_remote_snapshot_high_watermark_cursor,
                    "final_remote_snapshot_high_watermark_cursor",
                ),
                "stream_control_etag": _required(
                    run.final_stream_control_etag, "final_stream_control_etag"
                ),
                "stream_control_version": _required(
                    run.final_stream_control_version, "final_stream_control_version"
                ),
            },
            "restore_epoch": _required(run.final_restore_epoch, "final_restore_epoch"),
            "run_id": str(run.run_id),
            "version": "pinvi-cache-target-canary-final-evidence/v1",
        }
    )
