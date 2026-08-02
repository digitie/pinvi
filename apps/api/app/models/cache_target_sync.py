"""kor-travel-map cache target command/outbox paired consumer durable state."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.elements import conv

from app.db.base import Base
from app.models.mixins import TimestampMixin


class KtmCacheTargetHead(Base, TimestampMixin):
    """PinVi target 자연키의 desired head와 마지막 Map 적용 상태."""

    __tablename__ = "ktm_cache_target_heads"
    __table_args__ = (
        UniqueConstraint(
            "external_system",
            "target_key",
            name="uq_ktm_ct_heads_system_key",
        ),
        CheckConstraint("external_system = 'pinvi'", name=conv("ck_ktm_ct_heads_system")),
        CheckConstraint(
            "target_key = lower(poi_id::text)",
            name=conv("ck_ktm_ct_heads_target_key"),
        ),
        CheckConstraint(
            "desired_state IN ('active', 'deleted')",
            name=conv("ck_ktm_ct_heads_state"),
        ),
        CheckConstraint("source_generation > 0", name=conv("ck_ktm_ct_heads_generation")),
        CheckConstraint(
            "octet_length(source_payload_fingerprint) = 32",
            name=conv("ck_ktm_ct_heads_fingerprint"),
        ),
        CheckConstraint(
            "desired_state = 'deleted' OR (lon IS NOT NULL AND lat IS NOT NULL)",
            name=conv("ck_ktm_ct_heads_active_coord"),
        ),
        CheckConstraint("lon IS NULL OR lon BETWEEN 124 AND 132", name=conv("ck_ktm_ct_heads_lon")),
        CheckConstraint("lat IS NULL OR lat BETWEEN 33 AND 39.5", name=conv("ck_ktm_ct_heads_lat")),
        CheckConstraint("radius_km > 0 AND radius_km <= 100", name=conv("ck_ktm_ct_heads_radius")),
        CheckConstraint(
            "remote_restore_epoch IS NULL OR remote_restore_epoch > 0",
            name=conv("ck_ktm_ct_heads_remote_epoch"),
        ),
        CheckConstraint(
            "remote_source_generation IS NULL OR remote_source_generation > 0",
            name=conv("ck_ktm_ct_heads_remote_generation"),
        ),
        CheckConstraint(
            "remote_target_sequence IS NULL OR remote_target_sequence > 0",
            name=conv("ck_ktm_ct_heads_remote_sequence"),
        ),
    )

    # POI hard-delete 뒤에도 Map delete command와 tombstone을 보존해야 하므로 물리 FK를 두지 않는다.
    poi_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    external_system: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pinvi")
    target_key: Mapped[str] = mapped_column(String(36), nullable=False)
    desired_state: Mapped[str] = mapped_column(String(16), nullable=False)
    source_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_payload_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    lon: Mapped[Decimal | None] = mapped_column(Numeric())
    lat: Mapped[Decimal | None] = mapped_column(Numeric())
    radius_km: Mapped[Decimal] = mapped_column(Numeric(), nullable=False)
    update_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    remote_target_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    remote_etag: Mapped[str | None] = mapped_column(Text)
    remote_restore_epoch: Mapped[int | None] = mapped_column(BigInteger)
    remote_source_generation: Mapped[int | None] = mapped_column(BigInteger)
    remote_target_sequence: Mapped[int | None] = mapped_column(BigInteger)
    remote_status: Mapped[str | None] = mapped_column(String(32))


class KtmCacheTargetCommand(Base, TimestampMixin):
    """사용자 transaction과 함께 생성되는 Map command outbox."""

    __tablename__ = "ktm_cache_target_commands"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('put', 'delete', 'refresh')",
            name=conv("ck_ktm_ct_commands_operation"),
        ),
        CheckConstraint(
            "status IN ('pending', 'leased', 'succeeded', 'superseded', 'dead_letter')",
            name=conv("ck_ktm_ct_commands_status"),
        ),
        CheckConstraint("source_generation > 0", name=conv("ck_ktm_ct_commands_generation")),
        CheckConstraint("attempts >= 0", name=conv("ck_ktm_ct_commands_attempts")),
        CheckConstraint(
            "octet_length(payload_fingerprint) = 32",
            name=conv("ck_ktm_ct_commands_fingerprint"),
        ),
        CheckConstraint(
            "(lease_owner IS NULL) = (lease_until IS NULL)",
            name=conv("ck_ktm_ct_commands_lease_pair"),
        ),
        Index(
            "uq_ktm_ct_commands_state_generation",
            "poi_id",
            "source_generation",
            "operation",
            unique=True,
            postgresql_where=text("operation IN ('put', 'delete')"),
        ),
        Index(
            "ix_ktm_ct_commands_due",
            "available_at",
            "command_id",
            postgresql_where=text("status IN ('pending', 'leased')"),
        ),
        Index(
            "ix_ktm_ct_commands_lease",
            "lease_until",
            "command_id",
            postgresql_where=text("status = 'leased'"),
        ),
    )

    command_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    poi_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.ktm_cache_target_heads.poi_id", ondelete="RESTRICT"),
        nullable=False,
    )
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    source_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expected_etag: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    response_etag: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(96))
    error_detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KtmCacheTargetCanaryRun(Base, TimestampMixin):
    """production causal canary의 crash-safe phase와 secret-free receipt."""

    __tablename__ = "ktm_cache_target_canary_runs"
    __table_args__ = (
        UniqueConstraint("put_command_id", name="uq_ktm_ct_canary_put_command"),
        UniqueConstraint("delete_command_id", name="uq_ktm_ct_canary_delete_command"),
        UniqueConstraint("put_event_id", name="uq_ktm_ct_canary_put_event"),
        UniqueConstraint("delete_event_id", name="uq_ktm_ct_canary_delete_event"),
        Index(
            "uq_ktm_ct_canary_running_target",
            "target_poi_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
        CheckConstraint(
            "target_poi_id = '15f98050-27d7-5f85-be21-dc53eded5d7d'::uuid",
            name=conv("ck_ktm_ct_canary_stable_target"),
        ),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name=conv("ck_ktm_ct_canary_status"),
        ),
        CheckConstraint(
            "phase IN ('put_enqueued', 'put_applied', 'delete_enqueued', "
            "'delete_applied', 'completed')",
            name=conv("ck_ktm_ct_canary_phase"),
        ),
        CheckConstraint(
            "put_generation > 0 AND delete_generation = put_generation + 1",
            name=conv("ck_ktm_ct_canary_generations"),
        ),
        CheckConstraint(
            "baseline_cache_generation >= 0 AND baseline_count >= 0 "
            "AND octet_length(baseline_merkle_root) = 32 AND length(baseline_cursor) > 0",
            name=conv("ck_ktm_ct_canary_baseline"),
        ),
        CheckConstraint(
            "(put_event_id IS NULL AND put_relay_order IS NULL "
            "AND put_cache_generation IS NULL AND put_cursor IS NULL) OR "
            "(put_event_id IS NOT NULL AND put_relay_order > 0 "
            "AND put_cache_generation > baseline_cache_generation AND length(put_cursor) > 0)",
            name=conv("ck_ktm_ct_canary_put_material"),
        ),
        CheckConstraint(
            "(delete_event_id IS NULL AND delete_relay_order IS NULL) OR "
            "(delete_event_id IS NOT NULL AND delete_relay_order > put_relay_order)",
            name=conv("ck_ktm_ct_canary_delete_material"),
        ),
        CheckConstraint(
            "(final_cache_generation IS NULL AND final_cursor IS NULL "
            "AND final_count IS NULL AND final_merkle_root IS NULL) OR "
            "(final_cache_generation > put_cache_generation AND length(final_cursor) > 0 "
            "AND final_count >= 0 AND octet_length(final_merkle_root) = 32)",
            name=conv("ck_ktm_ct_canary_final_material"),
        ),
        CheckConstraint(
            "(phase = 'put_enqueued' AND put_event_id IS NULL AND delete_command_id IS NULL "
            "AND delete_event_id IS NULL AND final_cache_generation IS NULL) OR "
            "(phase = 'put_applied' AND put_event_id IS NOT NULL AND delete_command_id IS NULL "
            "AND delete_event_id IS NULL AND final_cache_generation IS NULL) OR "
            "(phase = 'delete_enqueued' AND put_event_id IS NOT NULL "
            "AND delete_command_id IS NOT NULL AND delete_event_id IS NULL "
            "AND final_cache_generation IS NULL) OR "
            "(phase = 'delete_applied' AND put_event_id IS NOT NULL "
            "AND delete_command_id IS NOT NULL AND delete_event_id IS NOT NULL "
            "AND final_cache_generation IS NULL) OR "
            "(phase = 'completed' AND put_event_id IS NOT NULL "
            "AND delete_command_id IS NOT NULL AND delete_event_id IS NOT NULL "
            "AND final_cache_generation IS NOT NULL)",
            name=conv("ck_ktm_ct_canary_phase_material"),
        ),
        CheckConstraint(
            "(status = 'running' AND terminal_error_code IS NULL AND failed_at IS NULL "
            "AND completed_at IS NULL AND phase <> 'completed') OR "
            "(status = 'succeeded' AND terminal_error_code IS NULL AND failed_at IS NULL "
            "AND completed_at IS NOT NULL AND phase = 'completed') OR "
            "(status = 'failed' AND length(terminal_error_code) > 0 "
            "AND failed_at IS NOT NULL AND completed_at IS NULL AND phase <> 'completed')",
            name=conv("ck_ktm_ct_canary_terminal"),
        ),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    target_poi_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.ktm_cache_target_heads.poi_id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="running")
    phase: Mapped[str] = mapped_column(Text, nullable=False, server_default="put_enqueued")
    put_command_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.ktm_cache_target_commands.command_id", ondelete="RESTRICT"),
        nullable=False,
    )
    delete_command_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.ktm_cache_target_commands.command_id", ondelete="RESTRICT"),
    )
    put_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.ktm_cache_target_events.event_id", ondelete="RESTRICT"),
    )
    delete_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.ktm_cache_target_events.event_id", ondelete="RESTRICT"),
    )
    put_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    delete_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    put_relay_order: Mapped[int | None] = mapped_column(BigInteger)
    delete_relay_order: Mapped[int | None] = mapped_column(BigInteger)
    baseline_cache_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    put_cache_generation: Mapped[int | None] = mapped_column(BigInteger)
    final_cache_generation: Mapped[int | None] = mapped_column(BigInteger)
    baseline_cursor: Mapped[str] = mapped_column(Text, nullable=False)
    put_cursor: Mapped[str | None] = mapped_column(Text)
    final_cursor: Mapped[str | None] = mapped_column(Text)
    baseline_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    baseline_merkle_root: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    final_count: Mapped[int | None] = mapped_column(BigInteger)
    final_merkle_root: Mapped[bytes | None] = mapped_column(LargeBinary)
    terminal_error_code: Mapped[str | None] = mapped_column(Text)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KtmCacheTargetEvent(Base):
    """Map at-least-once event의 immutable inbox와 local apply marker."""

    __tablename__ = "ktm_cache_target_events"
    __table_args__ = (
        CheckConstraint("external_system = 'pinvi'", name=conv("ck_ktm_ct_events_system")),
        CheckConstraint(
            "event_type IN ('cache_target.state_applied', "
            "'cache_target.links_reconciled', 'refresh_request.status_changed', "
            "'cache_target.reconciled')",
            name=conv("ck_ktm_ct_events_type"),
        ),
        CheckConstraint("restore_epoch > 0", name=conv("ck_ktm_ct_events_epoch")),
        CheckConstraint(
            "octet_length(source_payload_fingerprint) = 32 AND ("
            "(event_type = 'cache_target.reconciled' AND target_key IS NULL AND "
            "target_id IS NULL AND source_generation IS NULL AND target_sequence IS NULL) OR "
            "(event_type <> 'cache_target.reconciled' AND target_key IS NOT NULL AND "
            "target_id IS NOT NULL AND "
            "source_generation > 0 AND target_sequence > 0))",
            name=conv("ck_ktm_ct_events_scope_tuple"),
        ),
        CheckConstraint("relay_order > 0", name=conv("ck_ktm_ct_events_relay_order")),
        CheckConstraint(
            "octet_length(payload_fingerprint) = 32",
            name=conv("ck_ktm_ct_events_payload_fingerprint"),
        ),
        UniqueConstraint(
            "external_system",
            "restore_epoch",
            "relay_order",
            name="uq_ktm_ct_events_stream_order",
        ),
        Index(
            "uq_ktm_ct_events_target_sequence",
            "external_system",
            "target_key",
            "restore_epoch",
            "source_generation",
            "target_sequence",
            unique=True,
            postgresql_where=text("target_key IS NOT NULL"),
        ),
        Index("ix_ktm_ct_events_epoch_relay", "restore_epoch", "relay_order"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_system: Mapped[str] = mapped_column(String(32), nullable=False)
    target_key: Mapped[str | None] = mapped_column(String(36))
    target_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    restore_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_generation: Mapped[int | None] = mapped_column(BigInteger)
    target_sequence: Mapped[int | None] = mapped_column(BigInteger)
    relay_order: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_payload_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    payload_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KtmCacheTargetConsumer(Base, TimestampMixin):
    """local applied와 remote ACK를 분리한 stream consumer singleton."""

    __tablename__ = "ktm_cache_target_consumers"
    __table_args__ = (
        CheckConstraint("external_system = 'pinvi'", name=conv("ck_ktm_ct_consumers_system")),
        CheckConstraint(
            "active_restore_epoch IS NULL OR active_restore_epoch > 0",
            name=conv("ck_ktm_ct_consumers_epoch"),
        ),
        CheckConstraint(
            "reconcile_status IN ('uninitialized', 'checking', 'matched', 'mismatched', 'blocked')",
            name=conv("ck_ktm_ct_consumers_reconcile"),
        ),
        CheckConstraint(
            "feature_cache_generation >= 0",
            name=conv("ck_ktm_ct_consumers_cache_generation"),
        ),
        CheckConstraint(
            "snapshot_count IS NULL OR snapshot_count >= 0",
            name=conv("ck_ktm_ct_consumers_snapshot_count"),
        ),
        CheckConstraint(
            "snapshot_merkle_root IS NULL OR octet_length(snapshot_merkle_root) = 32",
            name=conv("ck_ktm_ct_consumers_merkle"),
        ),
        CheckConstraint(
            "(initial_cutover_id IS NULL AND initial_reconciliation_request_id IS NULL "
            "AND initial_begin_stream_etag IS NULL AND initial_reconciliation_etag IS NULL "
            "AND initial_source_count IS NULL AND initial_source_merkle_root IS NULL "
            "AND initial_cutover_completed_at IS NULL) OR "
            "(initial_cutover_id IS NOT NULL AND initial_source_count >= 0 "
            "AND octet_length(initial_source_merkle_root) = 32)",
            name=conv("ck_ktm_ct_consumers_initial_cutover"),
        ),
    )

    consumer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    external_system: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pinvi")
    active_restore_epoch: Mapped[int | None] = mapped_column(BigInteger)
    local_applied_cursor: Mapped[str | None] = mapped_column(Text)
    remote_acked_cursor: Mapped[str | None] = mapped_column(Text)
    high_watermark_cursor: Mapped[str | None] = mapped_column(Text)
    stream_control_etag: Mapped[str | None] = mapped_column(Text)
    snapshot_id: Mapped[str | None] = mapped_column(Text)
    snapshot_count: Mapped[int | None] = mapped_column(BigInteger)
    snapshot_merkle_root: Mapped[bytes | None] = mapped_column(LargeBinary)
    reconcile_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="uninitialized"
    )
    feature_cache_generation: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    ready: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    initial_cutover_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    initial_reconciliation_request_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True)
    )
    initial_begin_stream_etag: Mapped[str | None] = mapped_column(Text)
    initial_reconciliation_etag: Mapped[str | None] = mapped_column(Text)
    initial_source_count: Mapped[int | None] = mapped_column(BigInteger)
    initial_source_merkle_root: Mapped[bytes | None] = mapped_column(LargeBinary)
    initial_cutover_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KtmCacheTargetReconciliationExpectation(Base, TimestampMixin):
    """request-bound fixed snapshot과 terminal stream receipt의 durable 결박."""

    __tablename__ = "ktm_cache_target_reconciliation_expectations"
    __table_args__ = (
        CheckConstraint(
            "external_system = 'pinvi'",
            name=conv("ck_ktm_ct_reconcile_expectations_system"),
        ),
        CheckConstraint(
            "restore_epoch > 0",
            name=conv("ck_ktm_ct_reconcile_expectations_epoch"),
        ),
        CheckConstraint(
            "snapshot_count >= 0",
            name=conv("ck_ktm_ct_reconcile_expectations_count"),
        ),
        CheckConstraint(
            "octet_length(snapshot_merkle_root) = 32",
            name=conv("ck_ktm_ct_reconcile_expectations_root"),
        ),
        CheckConstraint(
            "length(high_watermark_cursor) > 0",
            name=conv("ck_ktm_ct_reconcile_expectations_cursor"),
        ),
        CheckConstraint(
            "status IN ('pending', 'received', 'invalidated')",
            name=conv("ck_ktm_ct_reconcile_expectations_status"),
        ),
        CheckConstraint(
            "(status = 'pending' AND receipt_event_id IS NULL AND resolved_at IS NULL) OR "
            "(status = 'received' AND receipt_event_id IS NOT NULL AND resolved_at IS NOT NULL) OR "
            "(status = 'invalidated' AND receipt_event_id IS NULL AND resolved_at IS NOT NULL)",
            name=conv("ck_ktm_ct_reconcile_expectations_resolution"),
        ),
        UniqueConstraint(
            "snapshot_id",
            name="uq_ktm_ct_reconcile_expectations_snapshot",
        ),
        UniqueConstraint(
            "receipt_event_id",
            name="uq_ktm_ct_reconcile_expectations_receipt",
        ),
        Index(
            "ix_ktm_ct_reconcile_expectations_pending",
            "external_system",
            "restore_epoch",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    external_system: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pinvi")
    snapshot_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    restore_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    snapshot_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    snapshot_merkle_root: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    high_watermark_cursor: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    receipt_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "app.ktm_cache_target_events.event_id",
            ondelete="RESTRICT",
            name="fk_ktm_ct_reconcile_expectations_receipt",
        ),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KtmCacheTargetEventClaim(Base):
    """한 pull lease의 mutable ACK 권한과 완료 상태."""

    __tablename__ = "ktm_cache_target_event_claims"
    __table_args__ = (
        UniqueConstraint("lease_token", name="uq_ktm_ct_event_claims_lease_token"),
        CheckConstraint(
            "status IN ('active', 'acked', 'expired', 'invalidated')",
            name=conv("ck_ktm_ct_event_claims_status"),
        ),
        CheckConstraint(
            "(status = 'active' AND completed_at IS NULL) OR "
            "(status <> 'active' AND completed_at IS NOT NULL)",
            name=conv("ck_ktm_ct_event_claims_completion"),
        ),
        Index(
            "ix_ktm_ct_event_claims_lease",
            "lease_expires_at",
            "claim_id",
            postgresql_where=text("status = 'active'"),
        ),
    )

    claim_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    consumer_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("app.ktm_cache_target_consumers.consumer_id", ondelete="RESTRICT"),
        nullable=False,
    )
    lease_token: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    acked_through_cursor: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KtmCacheTargetEventClaimItem(Base):
    """재claim마다 새로 남기는 event delivery/ACK receipt."""

    __tablename__ = "ktm_cache_target_event_claim_items"
    __table_args__ = (
        UniqueConstraint(
            "claim_id",
            "delivery_cursor",
            name="uq_ktm_ct_claim_items_cursor",
        ),
        UniqueConstraint(
            "claim_id",
            "position",
            name="uq_ktm_ct_claim_items_position",
        ),
        CheckConstraint("position > 0", name=conv("ck_ktm_ct_claim_items_position")),
        CheckConstraint(
            "octet_length(payload_fingerprint) = 32",
            name=conv("ck_ktm_ct_claim_items_fingerprint"),
        ),
        Index(
            "ix_ktm_ct_claim_items_ack_gap",
            "claim_id",
            "position",
            postgresql_where=text("acked_at IS NULL"),
        ),
    )

    claim_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.ktm_cache_target_event_claims.claim_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.ktm_cache_target_events.event_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    delivery_cursor: Mapped[str] = mapped_column(Text, nullable=False)
    payload_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
