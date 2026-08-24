"""generation 7 preflight와 append-only final boundary evidence."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.cache_target_sync import (
    KtmCacheTargetBoundaryAudit,
    KtmCacheTargetCanaryRun,
    KtmCacheTargetCommand,
    KtmCacheTargetConsumer,
    KtmCacheTargetEvent,
    KtmCacheTargetEventClaim,
    KtmCacheTargetEventClaimItem,
    KtmCacheTargetHead,
    KtmCacheTargetReconciliationExpectation,
)
from app.services.cache_target_boundary_evidence import (
    STABLE_TARGET_ID,
    CacheTargetCanaryFailure,
    cache_target_command_backlog,
    canary_final_evidence_sha256,
    canary_provenance_sha256,
    canonical_sha256,
    require_ready_cache_target_consumer,
    validate_canary_final_head,
    validate_initial_state_event,
    validate_stored_canary_run,
)
from app.services.cache_target_initial_cutover import read_cache_target_source_identity

CONTRACT_VERSION: Literal["pinvi-cache-target-final-boundary/v1"] = (
    "pinvi-cache-target-final-boundary/v1"
)
PREFLIGHT_SCHEMA_REVISION = "20260801_0047"
# 20260821_0061은 Feature 참조 조정 evidence의 append-only trigger를 replication
# bypass에도 강제한다. 이 pin과 DB CHECK (ck_ktm_ct_boundary_contract)는 head
# migration마다 함께 갱신해야 finalize가 열린다 — fail-close by design.
FINALIZE_SCHEMA_REVISION = "20260824_0064"
WRITER_REGISTRY_SHA256 = "526240609e2919357699b90244eb8cc8b9505f37db6c60552a98c7a37ed22d7c"
_APPLICATION_NAME = "pinvi-cache-target-final-boundary"

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_DATABASE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_COMMON_TABLE_LOCK = text(
    "LOCK TABLE app.ktm_cache_target_heads, app.ktm_cache_target_commands, "
    "app.ktm_cache_target_consumers, app.ktm_cache_target_events, "
    "app.ktm_cache_target_event_claims, app.ktm_cache_target_event_claim_items, "
    "app.ktm_cache_target_reconciliation_expectations IN SHARE MODE"
)
_FINALIZE_TABLE_LOCK = text(
    "LOCK TABLE app.ktm_cache_target_heads, app.ktm_cache_target_commands, "
    "app.ktm_cache_target_consumers, app.ktm_cache_target_events, "
    "app.ktm_cache_target_event_claims, app.ktm_cache_target_event_claim_items, "
    "app.ktm_cache_target_reconciliation_expectations, "
    "app.ktm_cache_target_canary_runs IN SHARE MODE"
)
_AUDIT_SERIALIZE_LOCK = text(
    "LOCK TABLE app.ktm_cache_target_boundary_audits IN SHARE ROW EXCLUSIVE MODE"
)


class CacheTargetBoundaryFailure(RuntimeError):
    def __init__(self, code: str, phase: Literal["preflight", "finalize"]) -> None:
        super().__init__(code)
        self.code = code
        self.phase = phase


@dataclass(frozen=True, slots=True)
class MapFinalEvidence:
    contract_version: Literal["ktm-cache-target-final-evidence/v1"]
    external_system: Literal["pinvi"]
    stream_state: Literal["ready"]
    consumer_id: str
    restore_epoch: int
    control_version: int
    stream_control_etag: str
    high_watermark_cursor: str
    snapshot_count: int
    snapshot_merkle_root: str
    reconciliation_backlog_count: Literal[0]
    outbox_backlog_count: Literal[0]
    claim_backlog_count: Literal[0]
    delivery_backlog_count: Literal[0]

    @classmethod
    def parse(cls, value: object) -> MapFinalEvidence:
        if not isinstance(value, dict) or set(value) != {
            "contract_version",
            "external_system",
            "stream_state",
            "consumer_id",
            "restore_epoch",
            "control_version",
            "stream_control_etag",
            "high_watermark_cursor",
            "snapshot_count",
            "snapshot_merkle_root",
            "reconciliation_backlog_count",
            "outbox_backlog_count",
            "claim_backlog_count",
            "delivery_backlog_count",
        }:
            raise ValueError("map final evidence fields are invalid")
        if (
            value["contract_version"] != "ktm-cache-target-final-evidence/v1"
            or value["external_system"] != "pinvi"
            or value["stream_state"] != "ready"
        ):
            raise ValueError("map final evidence contract is invalid")
        for field in ("consumer_id", "stream_control_etag", "high_watermark_cursor"):
            if not isinstance(value[field], str) or not value[field]:
                raise ValueError("map final evidence string is invalid")
        for field in ("restore_epoch", "control_version"):
            observed = value[field]
            if isinstance(observed, bool) or not isinstance(observed, int) or observed <= 0:
                raise ValueError("map final evidence control is invalid")
        count = value["snapshot_count"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("map final evidence count is invalid")
        for field in (
            "reconciliation_backlog_count",
            "outbox_backlog_count",
            "claim_backlog_count",
            "delivery_backlog_count",
        ):
            if isinstance(value[field], bool) or value[field] != 0:
                raise ValueError("map final evidence backlog is invalid")
        return cls(
            contract_version="ktm-cache-target-final-evidence/v1",
            external_system="pinvi",
            stream_state="ready",
            consumer_id=value["consumer_id"],
            restore_epoch=value["restore_epoch"],
            control_version=value["control_version"],
            stream_control_etag=value["stream_control_etag"],
            high_watermark_cursor=value["high_watermark_cursor"],
            snapshot_count=count,
            snapshot_merkle_root=_hex(value["snapshot_merkle_root"], 64, "snapshot_merkle_root"),
            reconciliation_backlog_count=0,
            outbox_backlog_count=0,
            claim_backlog_count=0,
            delivery_backlog_count=0,
        )

    def json_object(self) -> dict[str, int | str]:
        return {
            "contract_version": self.contract_version,
            "external_system": self.external_system,
            "stream_state": self.stream_state,
            "consumer_id": self.consumer_id,
            "restore_epoch": self.restore_epoch,
            "control_version": self.control_version,
            "stream_control_etag": self.stream_control_etag,
            "high_watermark_cursor": self.high_watermark_cursor,
            "snapshot_count": self.snapshot_count,
            "snapshot_merkle_root": self.snapshot_merkle_root,
            "reconciliation_backlog_count": self.reconciliation_backlog_count,
            "outbox_backlog_count": self.outbox_backlog_count,
            "claim_backlog_count": self.claim_backlog_count,
            "delivery_backlog_count": self.delivery_backlog_count,
        }


def _canonical_uuid(value: object, name: str) -> uuid.UUID:
    if not isinstance(value, str) or _UUID.fullmatch(value) is None:
        raise ValueError(f"{name} is invalid")
    parsed = uuid.UUID(value)
    if str(parsed) != value:
        raise ValueError(f"{name} is invalid")
    return parsed


def _hex(value: object, length: Literal[40, 64], name: str) -> str:
    pattern = _HEX40 if length == 40 else _HEX64
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ValueError(f"{name} is invalid")
    return value


@dataclass(frozen=True, slots=True)
class CacheTargetBoundaryRequest:
    contract_version: Literal["pinvi-cache-target-final-boundary/v1"]
    operation: Literal["preflight", "finalize"]
    transaction_id: uuid.UUID
    cutover_id: uuid.UUID
    source_revision: str
    database_identity: str
    writer_registry_sha256: str
    initial_writer_fence_sha256: str
    final_writer_fence_sha256: str | None
    prior_receipt_sha256: str | None
    canary_run_id: uuid.UUID | None
    map_final_evidence: MapFinalEvidence | None
    map_final_evidence_sha256: str | None

    @classmethod
    def parse(cls, value: object) -> CacheTargetBoundaryRequest:
        if not isinstance(value, dict) or set(value) != {
            "contract_version",
            "operation",
            "transaction_id",
            "cutover_id",
            "source_revision",
            "database_identity",
            "writer_registry_sha256",
            "initial_writer_fence_sha256",
            "final_writer_fence_sha256",
            "prior_receipt_sha256",
            "canary_run_id",
            "map_final_evidence",
            "map_final_evidence_sha256",
        }:
            raise ValueError("request fields are invalid")
        contract = value["contract_version"]
        operation = value["operation"]
        if contract != CONTRACT_VERSION or operation not in {"preflight", "finalize"}:
            raise ValueError("request contract is invalid")
        prior = value["prior_receipt_sha256"]
        canary = value["canary_run_id"]
        final_fence = value["final_writer_fence_sha256"]
        initial_fence_sha = _hex(
            value["initial_writer_fence_sha256"], 64, "initial_writer_fence_sha256"
        )
        map_value = value["map_final_evidence"]
        map_sha_value = value["map_final_evidence_sha256"]
        if operation == "preflight":
            if (
                prior is not None
                or canary is not None
                or final_fence is not None
                or map_value is not None
                or map_sha_value is not None
            ):
                raise ValueError("preflight binding is invalid")
            prior_sha = None
            canary_id = None
            final_fence_sha = None
            map_evidence = None
            map_evidence_sha = None
        else:
            prior_sha = _hex(prior, 64, "prior_receipt_sha256")
            canary_id = _canonical_uuid(canary, "canary_run_id")
            final_fence_sha = _hex(final_fence, 64, "final_writer_fence_sha256")
            map_evidence = MapFinalEvidence.parse(map_value)
            map_evidence_sha = _hex(map_sha_value, 64, "map_final_evidence_sha256")
            if final_fence_sha == initial_fence_sha:
                raise ValueError("writer fences must differ")
            if canonical_sha256(map_evidence.json_object()).hex() != map_evidence_sha:
                raise ValueError("map final evidence digest is invalid")
        registry = _hex(value["writer_registry_sha256"], 64, "writer_registry_sha256")
        if registry != WRITER_REGISTRY_SHA256:
            raise ValueError("writer registry is invalid")
        return cls(
            contract_version=CONTRACT_VERSION,
            operation=operation,
            transaction_id=_canonical_uuid(value["transaction_id"], "transaction_id"),
            cutover_id=_canonical_uuid(value["cutover_id"], "cutover_id"),
            source_revision=_hex(value["source_revision"], 40, "source_revision"),
            database_identity=_hex(value["database_identity"], 64, "database_identity"),
            writer_registry_sha256=registry,
            initial_writer_fence_sha256=initial_fence_sha,
            final_writer_fence_sha256=final_fence_sha,
            prior_receipt_sha256=prior_sha,
            canary_run_id=canary_id,
            map_final_evidence=map_evidence,
            map_final_evidence_sha256=map_evidence_sha,
        )

    def json_object(self) -> dict[str, object]:
        """Manager와 audit row가 공유하는 exact canonical request material."""
        return {
            "contract_version": self.contract_version,
            "operation": self.operation,
            "transaction_id": str(self.transaction_id),
            "cutover_id": str(self.cutover_id),
            "source_revision": self.source_revision,
            "database_identity": self.database_identity,
            "writer_registry_sha256": self.writer_registry_sha256,
            "initial_writer_fence_sha256": self.initial_writer_fence_sha256,
            "final_writer_fence_sha256": self.final_writer_fence_sha256,
            "prior_receipt_sha256": self.prior_receipt_sha256,
            "canary_run_id": str(self.canary_run_id) if self.canary_run_id else None,
            "map_final_evidence": (
                self.map_final_evidence.json_object()
                if self.map_final_evidence is not None
                else None
            ),
            "map_final_evidence_sha256": self.map_final_evidence_sha256,
        }


BoundaryJson = dict[str, int | str | dict[str, int | str] | None]


async def _schema_revision(db: AsyncSession) -> str:
    revision = await db.scalar(text("SELECT version_num FROM app.alembic_version"))
    if not isinstance(revision, str):
        raise RuntimeError("schema revision is unavailable")
    return revision


def _database_identity_v1(
    *, transaction_id: uuid.UUID, database_name: str, system_identifier: str
) -> str:
    if _DATABASE_NAME.fullmatch(database_name) is None:
        raise ValueError("database name is invalid")
    if (
        not system_identifier.isascii()
        or not system_identifier.isdigit()
        or len(system_identifier) > 32
    ):
        raise ValueError("system identifier is invalid")
    payload = (
        b"h35-db-identity-v1\0"
        + str(transaction_id).encode("ascii")
        + b"\0pinvi\0"
        + database_name.encode("ascii")
        + b"\0"
        + system_identifier.encode("ascii")
        + b"\0"
    )
    return hashlib.sha256(payload).hexdigest()


async def _validate_database_identity(db: AsyncSession, request: CacheTargetBoundaryRequest) -> int:
    row = (
        await db.execute(
            text(
                "SELECT current_database(), (pg_control_system()).system_identifier::text, "
                "(SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                "AND pid <> pg_backend_pid() AND state <> 'idle' "
                "AND application_name <> :application_name)"
            ),
            {"application_name": _APPLICATION_NAME},
        )
    ).one()
    database_name, system_identifier, in_flight = row
    if (
        not isinstance(database_name, str)
        or not isinstance(system_identifier, str)
        or not isinstance(in_flight, int)
        or _database_identity_v1(
            transaction_id=request.transaction_id,
            database_name=database_name,
            system_identifier=system_identifier,
        )
        != request.database_identity
    ):
        raise CacheTargetBoundaryFailure("database_identity_mismatch", request.operation)
    if in_flight != 0:
        raise CacheTargetBoundaryFailure("database_not_quiescent", request.operation)
    return in_flight


async def _table_count(db: AsyncSession, table: str) -> int:
    value = await db.scalar(text(f"SELECT count(*) FROM app.{table}"))  # noqa: S608
    return int(value or 0)


async def _application_queue_counts(db: AsyncSession) -> tuple[int, int, int]:
    email = int(
        await db.scalar(text("SELECT count(*) FROM app.email_queue WHERE status = 'pending'")) or 0
    )
    telegram = int(
        await db.scalar(
            text(
                "SELECT count(*) FROM app.telegram_system_notification_outbox "
                "WHERE status = 'pending'"
            )
        )
        or 0
    )
    location = int(
        await db.scalar(
            text("SELECT count(*) FROM app.location_audit_outbox WHERE processed_at IS NULL")
        )
        or 0
    )
    return email, telegram, location


def _receipt(
    request: CacheTargetBoundaryRequest,
    *,
    schema_revision: str,
    database_in_flight_transaction_count: int,
    email_queue_pending_count: int,
    telegram_outbox_pending_count: int,
    location_audit_outbox_pending_count: int,
    pending_command_count: int,
    leased_command_count: int,
    dead_letter_command_count: int,
    expected_initial_command_count: int,
    expected_initial_event_count: int,
    expected_initial_claim_item_count: int,
    expected_synthetic_command_count: int,
    expected_synthetic_event_count: int,
    expected_synthetic_claim_count: int,
    unexpected_generation7_command_count: int,
    unexpected_non_synthetic_event_count: int,
    unexpected_non_synthetic_claim_count: int,
    initial_evidence_sha256: bytes | None,
    canary_provenance_sha256_value: bytes | None,
    final_local_remote_evidence_sha256: bytes | None,
) -> BoundaryJson:
    final_audit = request.operation == "finalize"
    request_sha = canonical_sha256(request.json_object()).hex() if final_audit else None
    value: BoundaryJson = {
        "contract_version": request.contract_version,
        "operation": request.operation,
        "transaction_id": str(request.transaction_id),
        "cutover_id": str(request.cutover_id),
        "status": "succeeded",
        "source_revision": request.source_revision,
        "database_identity": request.database_identity,
        "writer_registry_sha256": request.writer_registry_sha256,
        "initial_writer_fence_sha256": request.initial_writer_fence_sha256,
        "final_writer_fence_sha256": request.final_writer_fence_sha256,
        "prior_receipt_sha256": request.prior_receipt_sha256,
        "schema_revision": schema_revision,
        "canary_run_id": str(request.canary_run_id) if request.canary_run_id else None,
        "map_final_evidence": (
            request.map_final_evidence.json_object()
            if request.map_final_evidence is not None
            else None
        ),
        "map_final_evidence_sha256": request.map_final_evidence_sha256,
        "audit_id": str(request.transaction_id) if final_audit else None,
        "audit_request_sha256": request_sha,
        "audit_row_count": 1 if final_audit else 0,
        "pending_command_count": pending_command_count,
        "leased_command_count": leased_command_count,
        "dead_letter_command_count": dead_letter_command_count,
        "in_flight_command_count": pending_command_count + leased_command_count,
        "database_in_flight_transaction_count": database_in_flight_transaction_count,
        "email_queue_pending_count": email_queue_pending_count,
        "telegram_outbox_pending_count": telegram_outbox_pending_count,
        "location_audit_outbox_pending_count": location_audit_outbox_pending_count,
        "expected_initial_command_count": expected_initial_command_count,
        "expected_initial_event_count": expected_initial_event_count,
        "expected_initial_claim_item_count": expected_initial_claim_item_count,
        "expected_synthetic_command_count": expected_synthetic_command_count,
        "expected_synthetic_event_count": expected_synthetic_event_count,
        "expected_synthetic_claim_count": expected_synthetic_claim_count,
        "unexpected_generation7_command_count": unexpected_generation7_command_count,
        "unexpected_non_synthetic_event_count": unexpected_non_synthetic_event_count,
        "unexpected_non_synthetic_claim_count": unexpected_non_synthetic_claim_count,
        "initial_evidence_sha256": (
            initial_evidence_sha256.hex() if initial_evidence_sha256 is not None else None
        ),
        "canary_provenance_sha256": (
            canary_provenance_sha256_value.hex()
            if canary_provenance_sha256_value is not None
            else None
        ),
        "final_local_remote_evidence_sha256": (
            final_local_remote_evidence_sha256.hex()
            if final_local_remote_evidence_sha256 is not None
            else None
        ),
        "runtime_mutation_count": 0,
        "external_mutation_count": 0,
    }
    value["evidence_sha256"] = canonical_sha256(value).hex()
    return value


async def run_cache_target_boundary_preflight(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    request: CacheTargetBoundaryRequest,
    runtime_source_revision: str,
) -> BoundaryJson:
    if request.operation != "preflight" or request.source_revision != runtime_source_revision:
        raise CacheTargetBoundaryFailure("source_revision_mismatch", "preflight")
    async with session_factory() as db:
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        await db.execute(text("SET LOCAL application_name = 'pinvi-cache-target-final-boundary'"))
        revision = await _schema_revision(db)
        if revision != PREFLIGHT_SCHEMA_REVISION:
            raise CacheTargetBoundaryFailure("schema_revision_mismatch", "preflight")
        await db.execute(_COMMON_TABLE_LOCK)
        in_flight = await _validate_database_identity(db, request)
        counts = {
            table: await _table_count(db, table)
            for table in (
                "ktm_cache_target_heads",
                "ktm_cache_target_commands",
                "ktm_cache_target_consumers",
                "ktm_cache_target_events",
                "ktm_cache_target_event_claims",
                "ktm_cache_target_event_claim_items",
                "ktm_cache_target_reconciliation_expectations",
            )
        }
        malformed_source_event_ids = int(
            await db.scalar(
                text(
                    "SELECT count(*) FROM app.ktm_cache_target_events "
                    "WHERE event_type = 'cache_target.state_applied' AND ("
                    "jsonb_typeof(payload -> 'source_event_id') IS DISTINCT FROM 'string' OR "
                    "(payload ->> 'source_event_id') !~ "
                    "'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')"
                )
            )
            or 0
        )
        if any(counts.values()) or malformed_source_event_ids:
            raise CacheTargetBoundaryFailure("preflight_material_not_empty", "preflight")
        email_pending, telegram_pending, location_pending = await _application_queue_counts(db)
        return _receipt(
            request,
            schema_revision=revision,
            database_in_flight_transaction_count=in_flight,
            email_queue_pending_count=email_pending,
            telegram_outbox_pending_count=telegram_pending,
            location_audit_outbox_pending_count=location_pending,
            pending_command_count=0,
            leased_command_count=0,
            dead_letter_command_count=0,
            expected_initial_command_count=0,
            expected_initial_event_count=0,
            expected_initial_claim_item_count=0,
            expected_synthetic_command_count=0,
            expected_synthetic_event_count=0,
            expected_synthetic_claim_count=0,
            unexpected_generation7_command_count=0,
            unexpected_non_synthetic_event_count=0,
            unexpected_non_synthetic_claim_count=0,
            initial_evidence_sha256=None,
            canary_provenance_sha256_value=None,
            final_local_remote_evidence_sha256=None,
        )


async def _validate_initial_and_counts(
    db: AsyncSession,
    *,
    run: KtmCacheTargetCanaryRun,
    consumer: KtmCacheTargetConsumer,
) -> tuple[int, bytes]:
    if (
        consumer.initial_cutover_id is None
        or consumer.initial_reconciliation_request_id is None
        or consumer.initial_source_count is None
        or consumer.initial_source_merkle_root is None
        or consumer.initial_cutover_completed_at is None
    ):
        raise CacheTargetBoundaryFailure("initial_evidence_incomplete", "finalize")
    expectation = await db.scalar(
        select(KtmCacheTargetReconciliationExpectation)
        .where(
            KtmCacheTargetReconciliationExpectation.request_id
            == consumer.initial_reconciliation_request_id
        )
        .with_for_update()
    )
    if (
        expectation is None
        or expectation.status != "received"
        or expectation.receipt_event_id is None
        or expectation.snapshot_count != consumer.initial_source_count
        or expectation.snapshot_merkle_root != consumer.initial_source_merkle_root
        or expectation.restore_epoch != consumer.active_restore_epoch
    ):
        raise CacheTargetBoundaryFailure("initial_evidence_mismatch", "finalize")
    commands = list(
        await db.scalars(select(KtmCacheTargetCommand).order_by(KtmCacheTargetCommand.command_id))
    )
    canary_command_ids = {run.put_command_id, run.delete_command_id}
    initial_commands = [row for row in commands if row.command_id not in canary_command_ids]
    if len(initial_commands) != consumer.initial_source_count or any(
        row.operation != "put" or row.status != "succeeded" for row in initial_commands
    ):
        raise CacheTargetBoundaryFailure("initial_command_provenance_mismatch", "finalize")
    heads = list(await db.scalars(select(KtmCacheTargetHead)))
    initial_heads = {row.poi_id: row for row in heads if row.poi_id != STABLE_TARGET_ID}
    if len(initial_heads) != consumer.initial_source_count or {
        row.poi_id for row in initial_commands
    } != set(initial_heads):
        raise CacheTargetBoundaryFailure("initial_command_head_mismatch", "finalize")
    events = list(
        await db.scalars(select(KtmCacheTargetEvent).order_by(KtmCacheTargetEvent.relay_order))
    )
    by_source = {row.source_event_id: row for row in events if row.source_event_id is not None}
    if len(by_source) != len(initial_commands) + 2:
        raise CacheTargetBoundaryFailure("event_provenance_mismatch", "finalize")
    initial_events: list[KtmCacheTargetEvent] = []
    for command in initial_commands:
        event = by_source.get(command.command_id)
        try:
            validate_initial_state_event(
                command=command,
                event=event,
                head=initial_heads.get(command.poi_id),
                restore_epoch=expectation.restore_epoch,
            )
        except ValueError as exc:
            raise CacheTargetBoundaryFailure(
                "initial_event_provenance_mismatch", "finalize"
            ) from exc
        assert event is not None
        if run.put_relay_order is None or event.relay_order >= run.put_relay_order:
            raise CacheTargetBoundaryFailure("initial_event_order_mismatch", "finalize")
        initial_events.append(event)
    receipt_event = next(
        (row for row in events if row.event_id == expectation.receipt_event_id), None
    )
    expected_payload = {
        "actual_merkle_root": consumer.initial_source_merkle_root.hex(),
        "expected_merkle_root": consumer.initial_source_merkle_root.hex(),
        "request_id": str(expectation.request_id),
        "snapshot_id": str(expectation.snapshot_id),
        "status": "succeeded",
        "version": "cache-target-reconciliation-v1",
    }
    if (
        receipt_event is None
        or receipt_event.event_type != "cache_target.reconciled"
        or receipt_event.external_system != "pinvi"
        or receipt_event.target_key is not None
        or receipt_event.target_id is not None
        or receipt_event.restore_epoch != expectation.restore_epoch
        or receipt_event.source_generation is not None
        or receipt_event.target_sequence is not None
        or receipt_event.payload != expected_payload
        or receipt_event.source_payload_fingerprint != consumer.initial_source_merkle_root
        or receipt_event.payload_fingerprint != canonical_sha256(expected_payload)
        or receipt_event.applied_at is None
        or run.put_relay_order is None
        or receipt_event.relay_order >= run.put_relay_order
    ):
        raise CacheTargetBoundaryFailure("initial_receipt_provenance_mismatch", "finalize")
    expected_event_ids = {
        *(row.event_id for row in initial_events),
        receipt_event.event_id,
        run.put_event_id,
        run.delete_event_id,
    }
    if None in expected_event_ids or {row.event_id for row in events} != expected_event_ids:
        raise CacheTargetBoundaryFailure("unexpected_non_synthetic_event", "finalize")
    items = list(
        await db.scalars(
            select(KtmCacheTargetEventClaimItem).order_by(
                KtmCacheTargetEventClaimItem.claim_id,
                KtmCacheTargetEventClaimItem.position,
            )
        )
    )
    if (
        len(items) != len(expected_event_ids)
        or {row.event_id for row in items} != expected_event_ids
    ):
        raise CacheTargetBoundaryFailure("unexpected_non_synthetic_claim", "finalize")
    event_by_id = {row.event_id: row for row in events}
    if any(
        row.acked_at is None
        or row.payload_fingerprint != event_by_id[row.event_id].payload_fingerprint
        for row in items
    ):
        raise CacheTargetBoundaryFailure("claim_provenance_mismatch", "finalize")
    claims = list(await db.scalars(select(KtmCacheTargetEventClaim)))
    claim_ids = {row.claim_id for row in items}
    if {row.claim_id for row in claims} != claim_ids or any(
        row.status != "acked" or row.completed_at is None for row in claims
    ):
        raise CacheTargetBoundaryFailure("unexpected_non_synthetic_claim", "finalize")
    for claim in claims:
        claim_items = [item for item in items if item.claim_id == claim.claim_id]
        terminal = max(claim_items, key=lambda item: item.position)
        if claim.acked_through_cursor != terminal.delivery_cursor:
            raise CacheTargetBoundaryFailure("claim_provenance_mismatch", "finalize")
    initial_material = {
        "commands": [
            {
                "command_id": str(row.command_id),
                "generation": row.source_generation,
                "payload_fingerprint": row.payload_fingerprint.hex(),
                "poi_id": str(row.poi_id),
            }
            for row in initial_commands
        ],
        "consumer_id": consumer.consumer_id,
        "cutover_id": str(consumer.initial_cutover_id),
        "events": [
            {
                "event_id": str(row.event_id),
                "payload_fingerprint": row.payload_fingerprint.hex(),
                "relay_order": row.relay_order,
                "source_event_id": str(row.source_event_id),
            }
            for row in initial_events
        ],
        "claims": [
            {
                "acked_at": row.acked_at.isoformat() if row.acked_at is not None else None,
                "claim_id": str(row.claim_id),
                "cursor": row.delivery_cursor,
                "event_id": str(row.event_id),
                "payload_fingerprint": row.payload_fingerprint.hex(),
            }
            for row in items
            if row.event_id not in {run.put_event_id, run.delete_event_id}
        ],
        "reconciliation_event_id": str(receipt_event.event_id),
        "reconciliation_request_id": str(expectation.request_id),
        "source_count": consumer.initial_source_count,
        "source_merkle_root": consumer.initial_source_merkle_root.hex(),
        "version": "pinvi-cache-target-initial-evidence/v1",
    }
    return consumer.initial_source_count, canonical_sha256(initial_material)


async def run_cache_target_boundary_finalize(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    request: CacheTargetBoundaryRequest,
    runtime_source_revision: str,
    consumer_id: str,
) -> BoundaryJson:
    if (
        request.operation != "finalize"
        or request.canary_run_id is None
        or request.prior_receipt_sha256 is None
        or request.final_writer_fence_sha256 is None
        or request.final_writer_fence_sha256 == request.initial_writer_fence_sha256
        or request.map_final_evidence is None
        or request.map_final_evidence_sha256 is None
        or request.source_revision != runtime_source_revision
    ):
        raise CacheTargetBoundaryFailure("source_revision_mismatch", "finalize")
    async with session_factory() as db:
        # 0047에서는 audit relation이 아직 없으므로 먼저 typed schema failure를 만든다.
        # 이 관측 transaction은 끝내고, 실제 evidence snapshot은 아래 lock 뒤에 새로 연다.
        if await _schema_revision(db) != FINALIZE_SCHEMA_REVISION:
            raise CacheTargetBoundaryFailure("schema_revision_mismatch", "finalize")
        await db.rollback()
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        await db.execute(text("SET LOCAL application_name = 'pinvi-cache-target-final-boundary'"))
        # REPEATABLE READ snapshot을 만들기 전에 직렬화해야 대기한 replay가 선행
        # transaction의 committed audit를 같은 실행에서 볼 수 있다.
        await db.execute(_AUDIT_SERIALIZE_LOCK)
        revision = await _schema_revision(db)
        if revision != FINALIZE_SCHEMA_REVISION:
            raise CacheTargetBoundaryFailure("schema_revision_mismatch", "finalize")
        await db.execute(_FINALIZE_TABLE_LOCK)
        in_flight = await _validate_database_identity(db, request)
        run = await db.scalar(
            select(KtmCacheTargetCanaryRun)
            .where(KtmCacheTargetCanaryRun.run_id == request.canary_run_id)
            .with_for_update()
        )
        if run is None or run.status != "succeeded" or run.phase != "completed":
            raise CacheTargetBoundaryFailure("canary_not_completed", "finalize")
        try:
            consumer = require_ready_cache_target_consumer(
                await db.scalar(
                    select(KtmCacheTargetConsumer)
                    .where(KtmCacheTargetConsumer.consumer_id == consumer_id)
                    .with_for_update()
                ),
                phase="completed",
            )
            await validate_stored_canary_run(db, run, consumer_id=consumer_id)
            assert consumer.active_restore_epoch is not None
            validate_canary_final_head(
                await db.scalar(
                    select(KtmCacheTargetHead)
                    .where(KtmCacheTargetHead.poi_id == STABLE_TARGET_ID)
                    .with_for_update()
                ),
                run=run,
                restore_epoch=consumer.active_restore_epoch,
            )
        except CacheTargetCanaryFailure as exc:
            raise CacheTargetBoundaryFailure("canary_evidence_mismatch", "finalize") from exc
        provenance_sha = canary_provenance_sha256(run)
        final_sha = canary_final_evidence_sha256(run)
        if run.canary_provenance_sha256 != provenance_sha or run.final_evidence_sha256 != final_sha:
            raise CacheTargetBoundaryFailure("canary_evidence_mismatch", "finalize")
        initial_count, initial_sha = await _validate_initial_and_counts(
            db, run=run, consumer=consumer
        )
        backlog = await cache_target_command_backlog(db)
        if backlog != (0, 0, 0):
            raise CacheTargetBoundaryFailure("command_backlog_not_empty", "finalize")
        email_pending, telegram_pending, location_pending = await _application_queue_counts(db)
        local = await read_cache_target_source_identity(db)
        map_evidence = request.map_final_evidence
        if (
            map_evidence.consumer_id != consumer_id
            or map_evidence.restore_epoch != consumer.active_restore_epoch
            or map_evidence.control_version != run.final_stream_control_version
            or map_evidence.stream_control_etag != consumer.stream_control_etag
            or map_evidence.stream_control_etag != run.final_stream_control_etag
            or map_evidence.high_watermark_cursor != consumer.local_applied_cursor
            or map_evidence.high_watermark_cursor != consumer.remote_acked_cursor
            or map_evidence.high_watermark_cursor != run.final_remote_snapshot_high_watermark_cursor
            or map_evidence.snapshot_count != local.count
            or map_evidence.snapshot_merkle_root != local.merkle_root
            or consumer.feature_cache_generation != run.final_cache_generation
            or map_evidence.restore_epoch != run.final_restore_epoch
            or consumer.local_applied_cursor != run.final_local_applied_cursor
            or consumer.remote_acked_cursor != run.final_local_remote_acked_cursor
            or local.count != run.final_local_count
            or map_evidence.snapshot_count != run.final_remote_count
            or bytes.fromhex(local.merkle_root) != run.final_local_merkle_root
            or bytes.fromhex(map_evidence.snapshot_merkle_root) != run.final_remote_merkle_root
        ):
            raise CacheTargetBoundaryFailure("local_remote_evidence_mismatch", "finalize")
        receipt = _receipt(
            request,
            schema_revision=revision,
            database_in_flight_transaction_count=in_flight,
            email_queue_pending_count=email_pending,
            telegram_outbox_pending_count=telegram_pending,
            location_audit_outbox_pending_count=location_pending,
            pending_command_count=backlog[0],
            leased_command_count=backlog[1],
            dead_letter_command_count=backlog[2],
            expected_initial_command_count=initial_count,
            expected_initial_event_count=initial_count + 1,
            expected_initial_claim_item_count=initial_count + 1,
            expected_synthetic_command_count=2,
            expected_synthetic_event_count=2,
            expected_synthetic_claim_count=2,
            unexpected_generation7_command_count=0,
            unexpected_non_synthetic_event_count=0,
            unexpected_non_synthetic_claim_count=0,
            initial_evidence_sha256=initial_sha,
            canary_provenance_sha256_value=provenance_sha,
            final_local_remote_evidence_sha256=final_sha,
        )
        existing = await db.get(KtmCacheTargetBoundaryAudit, request.transaction_id)
        cutover_owner = await db.scalar(
            select(KtmCacheTargetBoundaryAudit.transaction_id).where(
                KtmCacheTargetBoundaryAudit.cutover_id == request.cutover_id
            )
        )
        evidence_sha = bytes.fromhex(str(receipt["evidence_sha256"]))
        audit_request_sha = canonical_sha256(request.json_object())
        if existing is not None:
            if (
                existing.audit_request_sha256 != audit_request_sha
                or existing.evidence_sha256 != evidence_sha
            ):
                raise CacheTargetBoundaryFailure("boundary_replay_conflict", "finalize")
            await db.rollback()
            return receipt
        if cutover_owner is not None:
            raise CacheTargetBoundaryFailure("boundary_identity_conflict", "finalize")
        assert consumer.initial_cutover_id is not None
        assert consumer.initial_reconciliation_request_id is not None
        expectation = await db.get(
            KtmCacheTargetReconciliationExpectation,
            consumer.initial_reconciliation_request_id,
        )
        assert expectation is not None and expectation.receipt_event_id is not None
        db.add(
            KtmCacheTargetBoundaryAudit(
                transaction_id=request.transaction_id,
                cutover_id=request.cutover_id,
                contract_version=request.contract_version,
                status="succeeded",
                source_revision=request.source_revision,
                database_identity=bytes.fromhex(request.database_identity),
                writer_registry_sha256=bytes.fromhex(request.writer_registry_sha256),
                initial_writer_fence_sha256=bytes.fromhex(request.initial_writer_fence_sha256),
                final_writer_fence_sha256=bytes.fromhex(request.final_writer_fence_sha256),
                map_final_evidence_sha256=bytes.fromhex(request.map_final_evidence_sha256),
                audit_request_sha256=audit_request_sha,
                prior_receipt_sha256=bytes.fromhex(request.prior_receipt_sha256),
                schema_revision=revision,
                canary_run_id=request.canary_run_id,
                consumer_id=consumer.consumer_id,
                initial_cutover_id=consumer.initial_cutover_id,
                initial_reconciliation_request_id=consumer.initial_reconciliation_request_id,
                initial_receipt_event_id=expectation.receipt_event_id,
                initial_expectation_status="received",
                pending_command_count=0,
                leased_command_count=0,
                dead_letter_command_count=0,
                in_flight_command_count=0,
                database_in_flight_transaction_count=0,
                email_queue_pending_count=email_pending,
                telegram_outbox_pending_count=telegram_pending,
                location_audit_outbox_pending_count=location_pending,
                expected_initial_command_count=initial_count,
                expected_initial_event_count=initial_count + 1,
                expected_initial_claim_item_count=initial_count + 1,
                expected_synthetic_command_count=2,
                expected_synthetic_event_count=2,
                expected_synthetic_claim_count=2,
                unexpected_generation7_command_count=0,
                unexpected_non_synthetic_event_count=0,
                unexpected_non_synthetic_claim_count=0,
                initial_evidence_sha256=initial_sha,
                canary_provenance_sha256=provenance_sha,
                final_local_remote_evidence_sha256=final_sha,
                evidence_sha256=evidence_sha,
                runtime_mutation_count=0,
                external_mutation_count=0,
            )
        )
        await db.commit()
        return receipt
