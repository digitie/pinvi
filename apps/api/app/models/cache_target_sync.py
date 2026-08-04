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
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
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
        UniqueConstraint(
            "command_id",
            "poi_id",
            "source_generation",
            "payload_fingerprint",
            name="uq_ktm_ct_commands_provenance",
        ),
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
        UniqueConstraint(
            "run_id",
            "canary_provenance_sha256",
            "final_evidence_sha256",
            name="uq_ktm_ct_canary_final_evidence",
        ),
        ForeignKeyConstraint(
            ["consumer_id"],
            ["app.ktm_cache_target_consumers.consumer_id"],
            name="fk_ktm_ct_canary_consumer",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "put_command_id",
                "target_poi_id",
                "put_generation",
                "put_source_payload_fingerprint",
            ],
            [
                "app.ktm_cache_target_commands.command_id",
                "app.ktm_cache_target_commands.poi_id",
                "app.ktm_cache_target_commands.source_generation",
                "app.ktm_cache_target_commands.payload_fingerprint",
            ],
            name="fk_ktm_ct_canary_put_command",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "delete_command_id",
                "target_poi_id",
                "delete_generation",
                "delete_source_payload_fingerprint",
            ],
            [
                "app.ktm_cache_target_commands.command_id",
                "app.ktm_cache_target_commands.poi_id",
                "app.ktm_cache_target_commands.source_generation",
                "app.ktm_cache_target_commands.payload_fingerprint",
            ],
            name="fk_ktm_ct_canary_delete_command",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "put_event_id",
                "put_command_id",
                "put_generation",
                "put_source_payload_fingerprint",
                "put_event_payload_fingerprint",
            ],
            [
                "app.ktm_cache_target_events.event_id",
                "app.ktm_cache_target_events.source_event_id",
                "app.ktm_cache_target_events.source_generation",
                "app.ktm_cache_target_events.source_payload_fingerprint",
                "app.ktm_cache_target_events.payload_fingerprint",
            ],
            name="fk_ktm_ct_canary_put_event",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "delete_event_id",
                "delete_command_id",
                "delete_generation",
                "delete_source_payload_fingerprint",
                "delete_event_payload_fingerprint",
            ],
            [
                "app.ktm_cache_target_events.event_id",
                "app.ktm_cache_target_events.source_event_id",
                "app.ktm_cache_target_events.source_generation",
                "app.ktm_cache_target_events.source_payload_fingerprint",
                "app.ktm_cache_target_events.payload_fingerprint",
            ],
            name="fk_ktm_ct_canary_delete_event",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "put_claim_id",
                "put_event_id",
                "put_cursor",
                "put_event_payload_fingerprint",
                "put_acked_at",
            ],
            [
                "app.ktm_cache_target_event_claim_items.claim_id",
                "app.ktm_cache_target_event_claim_items.event_id",
                "app.ktm_cache_target_event_claim_items.delivery_cursor",
                "app.ktm_cache_target_event_claim_items.payload_fingerprint",
                "app.ktm_cache_target_event_claim_items.acked_at",
            ],
            name="fk_ktm_ct_canary_put_ack",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "delete_claim_id",
                "delete_event_id",
                "delete_cursor",
                "delete_event_payload_fingerprint",
                "delete_acked_at",
            ],
            [
                "app.ktm_cache_target_event_claim_items.claim_id",
                "app.ktm_cache_target_event_claim_items.event_id",
                "app.ktm_cache_target_event_claim_items.delivery_cursor",
                "app.ktm_cache_target_event_claim_items.payload_fingerprint",
                "app.ktm_cache_target_event_claim_items.acked_at",
            ],
            name="fk_ktm_ct_canary_delete_ack",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "put_claim_id",
                "consumer_id",
                "put_claim_status",
                "put_cursor",
                "put_claim_completed_at",
            ],
            [
                "app.ktm_cache_target_event_claims.claim_id",
                "app.ktm_cache_target_event_claims.consumer_id",
                "app.ktm_cache_target_event_claims.status",
                "app.ktm_cache_target_event_claims.acked_through_cursor",
                "app.ktm_cache_target_event_claims.completed_at",
            ],
            name="fk_ktm_ct_canary_put_claim_terminal",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "delete_claim_id",
                "consumer_id",
                "delete_claim_status",
                "delete_cursor",
                "delete_claim_completed_at",
            ],
            [
                "app.ktm_cache_target_event_claims.claim_id",
                "app.ktm_cache_target_event_claims.consumer_id",
                "app.ktm_cache_target_event_claims.status",
                "app.ktm_cache_target_event_claims.acked_through_cursor",
                "app.ktm_cache_target_event_claims.completed_at",
            ],
            name="fk_ktm_ct_canary_delete_claim_terminal",
            ondelete="RESTRICT",
        ),
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
            "put_generation > 0 AND delete_generation = put_generation + 1 "
            "AND octet_length(put_source_payload_fingerprint) = 32 "
            "AND octet_length(delete_source_payload_fingerprint) = 32 "
            "AND put_source_payload_fingerprint <> delete_source_payload_fingerprint",
            name=conv("ck_ktm_ct_canary_generations"),
        ),
        CheckConstraint(
            "baseline_cache_generation >= 0 AND baseline_count >= 0 "
            "AND octet_length(baseline_merkle_root) = 32 AND length(baseline_cursor) > 0",
            name=conv("ck_ktm_ct_canary_baseline"),
        ),
        CheckConstraint(
            "num_nonnulls(put_event_id, put_claim_id, put_relay_order, "
            "put_cache_generation, put_cursor, encode(put_event_payload_fingerprint, 'hex'), "
            "put_claim_status, put_acked_at, put_claim_completed_at) IN (0, 9) AND ("
            "put_event_id IS NULL OR (put_event_id IS NOT NULL AND put_claim_id IS NOT NULL "
            "AND put_relay_order IS NOT NULL AND put_relay_order > 0 "
            "AND put_cache_generation IS NOT NULL "
            "AND put_cache_generation > baseline_cache_generation "
            "AND put_cursor IS NOT NULL AND length(put_cursor) > 0 "
            "AND put_event_payload_fingerprint IS NOT NULL "
            "AND octet_length(put_event_payload_fingerprint) = 32 "
            "AND put_claim_status = 'acked' AND put_acked_at IS NOT NULL "
            "AND put_claim_completed_at IS NOT NULL))",
            name=conv("ck_ktm_ct_canary_put_material"),
        ),
        CheckConstraint(
            "num_nonnulls(delete_event_id, delete_claim_id, delete_relay_order, delete_cursor, "
            "encode(delete_event_payload_fingerprint, 'hex'), delete_claim_status, "
            "delete_acked_at, delete_claim_completed_at) IN (0, 8) AND ("
            "delete_event_id IS NULL OR (delete_event_id IS NOT NULL "
            "AND delete_claim_id IS NOT NULL AND delete_relay_order IS NOT NULL "
            "AND put_relay_order IS NOT NULL AND delete_relay_order > put_relay_order "
            "AND delete_cursor IS NOT NULL AND length(delete_cursor) > 0 "
            "AND delete_event_payload_fingerprint IS NOT NULL "
            "AND octet_length(delete_event_payload_fingerprint) = 32 "
            "AND delete_claim_status = 'acked' AND delete_acked_at IS NOT NULL "
            "AND delete_claim_completed_at IS NOT NULL))",
            name=conv("ck_ktm_ct_canary_delete_material"),
        ),
        CheckConstraint(
            "num_nonnulls(final_cache_generation::text, final_restore_epoch::text, "
            "final_stream_control_version::text, final_stream_control_etag, "
            "final_local_applied_cursor, final_local_remote_acked_cursor, "
            "final_remote_snapshot_high_watermark_cursor, "
            "final_local_count::text, final_remote_count::text, "
            "encode(final_local_merkle_root, 'hex'), encode(final_remote_merkle_root, 'hex'), "
            "final_pending_commands::text, final_leased_commands::text, "
            "final_dead_letter_commands::text, "
            "encode(canary_provenance_sha256, 'hex'), "
            "encode(final_evidence_sha256, 'hex')) = 0 OR "
            "(num_nonnulls(final_cache_generation::text, final_restore_epoch::text, "
            "final_stream_control_version::text, final_stream_control_etag, "
            "final_local_applied_cursor, final_local_remote_acked_cursor, "
            "final_remote_snapshot_high_watermark_cursor, final_local_count::text, "
            "final_remote_count::text, "
            "encode(final_local_merkle_root, 'hex'), encode(final_remote_merkle_root, 'hex'), "
            "final_pending_commands::text, final_leased_commands::text, "
            "final_dead_letter_commands::text, "
            "encode(canary_provenance_sha256, 'hex'), "
            "encode(final_evidence_sha256, 'hex')) = 16 "
            "AND final_cache_generation > put_cache_generation "
            "AND final_restore_epoch > 0 AND final_stream_control_version > 0 "
            "AND length(final_stream_control_etag) > 0 "
            "AND length(final_local_applied_cursor) > 0 "
            "AND length(final_local_remote_acked_cursor) > 0 "
            "AND length(final_remote_snapshot_high_watermark_cursor) > 0 "
            "AND final_local_applied_cursor = final_local_remote_acked_cursor "
            "AND final_local_remote_acked_cursor = final_remote_snapshot_high_watermark_cursor "
            "AND final_local_count >= 0 AND final_local_count = final_remote_count "
            "AND octet_length(final_local_merkle_root) = 32 "
            "AND final_local_merkle_root = final_remote_merkle_root "
            "AND octet_length(canary_provenance_sha256) = 32 "
            "AND octet_length(final_evidence_sha256) = 32 "
            "AND final_pending_commands = 0 AND final_leased_commands = 0 "
            "AND final_dead_letter_commands = 0)",
            name=conv("ck_ktm_ct_canary_final_material"),
        ),
        CheckConstraint(
            "(phase = 'put_enqueued' AND put_event_id IS NULL AND put_claim_id IS NULL "
            "AND put_relay_order IS NULL AND put_cache_generation IS NULL AND put_cursor IS NULL "
            "AND put_event_payload_fingerprint IS NULL AND put_claim_status IS NULL "
            "AND put_acked_at IS NULL AND put_claim_completed_at IS NULL "
            "AND delete_command_id IS NULL AND delete_event_id IS NULL "
            "AND delete_claim_id IS NULL AND delete_relay_order IS NULL AND delete_cursor IS NULL "
            "AND delete_event_payload_fingerprint IS NULL AND delete_claim_status IS NULL "
            "AND delete_acked_at IS NULL AND delete_claim_completed_at IS NULL "
            "AND final_cache_generation IS NULL) OR "
            "(phase = 'put_applied' AND put_event_id IS NOT NULL AND put_claim_id IS NOT NULL "
            "AND put_relay_order IS NOT NULL AND put_cache_generation IS NOT NULL "
            "AND put_cursor IS NOT NULL AND put_event_payload_fingerprint IS NOT NULL "
            "AND put_claim_status IS NOT NULL AND put_acked_at IS NOT NULL "
            "AND put_claim_completed_at IS NOT NULL AND delete_command_id IS NULL "
            "AND delete_event_id IS NULL AND delete_claim_id IS NULL "
            "AND delete_relay_order IS NULL AND delete_cursor IS NULL "
            "AND delete_event_payload_fingerprint IS NULL AND delete_claim_status IS NULL "
            "AND delete_acked_at IS NULL AND delete_claim_completed_at IS NULL "
            "AND final_cache_generation IS NULL) OR "
            "(phase = 'delete_enqueued' AND put_event_id IS NOT NULL "
            "AND put_claim_id IS NOT NULL AND put_relay_order IS NOT NULL "
            "AND put_cache_generation IS NOT NULL AND put_cursor IS NOT NULL "
            "AND put_event_payload_fingerprint IS NOT NULL AND put_claim_status IS NOT NULL "
            "AND put_acked_at IS NOT NULL AND put_claim_completed_at IS NOT NULL "
            "AND delete_command_id IS NOT NULL AND delete_event_id IS NULL "
            "AND delete_claim_id IS NULL AND delete_relay_order IS NULL "
            "AND delete_cursor IS NULL AND delete_event_payload_fingerprint IS NULL "
            "AND delete_claim_status IS NULL AND delete_acked_at IS NULL "
            "AND delete_claim_completed_at IS NULL AND final_cache_generation IS NULL) OR "
            "(phase = 'delete_applied' AND put_event_id IS NOT NULL "
            "AND put_claim_id IS NOT NULL AND put_relay_order IS NOT NULL "
            "AND put_cache_generation IS NOT NULL AND put_cursor IS NOT NULL "
            "AND put_event_payload_fingerprint IS NOT NULL AND put_claim_status IS NOT NULL "
            "AND put_acked_at IS NOT NULL AND put_claim_completed_at IS NOT NULL "
            "AND delete_command_id IS NOT NULL AND delete_event_id IS NOT NULL "
            "AND delete_claim_id IS NOT NULL AND delete_relay_order IS NOT NULL "
            "AND delete_cursor IS NOT NULL AND delete_event_payload_fingerprint IS NOT NULL "
            "AND delete_claim_status IS NOT NULL AND delete_acked_at IS NOT NULL "
            "AND delete_claim_completed_at IS NOT NULL AND final_cache_generation IS NULL) OR "
            "(phase = 'completed' AND put_event_id IS NOT NULL AND put_claim_id IS NOT NULL "
            "AND put_relay_order IS NOT NULL AND put_cache_generation IS NOT NULL "
            "AND put_cursor IS NOT NULL AND put_event_payload_fingerprint IS NOT NULL "
            "AND put_claim_status IS NOT NULL AND put_acked_at IS NOT NULL "
            "AND put_claim_completed_at IS NOT NULL AND delete_command_id IS NOT NULL "
            "AND delete_event_id IS NOT NULL AND delete_claim_id IS NOT NULL "
            "AND delete_relay_order IS NOT NULL AND delete_cursor IS NOT NULL "
            "AND delete_event_payload_fingerprint IS NOT NULL "
            "AND delete_claim_status IS NOT NULL AND delete_acked_at IS NOT NULL "
            "AND delete_claim_completed_at IS NOT NULL "
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
    consumer_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="running")
    phase: Mapped[str] = mapped_column(Text, nullable=False, server_default="put_enqueued")
    put_command_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        nullable=False,
    )
    delete_command_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
    )
    put_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
    )
    delete_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
    )
    put_claim_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    delete_claim_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    put_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    delete_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    put_source_payload_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    delete_source_payload_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    put_event_payload_fingerprint: Mapped[bytes | None] = mapped_column(LargeBinary)
    delete_event_payload_fingerprint: Mapped[bytes | None] = mapped_column(LargeBinary)
    put_claim_status: Mapped[str | None] = mapped_column(Text)
    delete_claim_status: Mapped[str | None] = mapped_column(Text)
    put_acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delete_acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    put_claim_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delete_claim_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    put_relay_order: Mapped[int | None] = mapped_column(BigInteger)
    delete_relay_order: Mapped[int | None] = mapped_column(BigInteger)
    baseline_cache_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    put_cache_generation: Mapped[int | None] = mapped_column(BigInteger)
    final_cache_generation: Mapped[int | None] = mapped_column(BigInteger)
    final_restore_epoch: Mapped[int | None] = mapped_column(BigInteger)
    final_stream_control_version: Mapped[int | None] = mapped_column(BigInteger)
    final_stream_control_etag: Mapped[str | None] = mapped_column(Text)
    baseline_cursor: Mapped[str] = mapped_column(Text, nullable=False)
    put_cursor: Mapped[str | None] = mapped_column(Text)
    delete_cursor: Mapped[str | None] = mapped_column(Text)
    final_local_applied_cursor: Mapped[str | None] = mapped_column(Text)
    final_local_remote_acked_cursor: Mapped[str | None] = mapped_column(Text)
    final_remote_snapshot_high_watermark_cursor: Mapped[str | None] = mapped_column(Text)
    baseline_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    baseline_merkle_root: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    final_local_count: Mapped[int | None] = mapped_column(BigInteger)
    final_remote_count: Mapped[int | None] = mapped_column(BigInteger)
    final_local_merkle_root: Mapped[bytes | None] = mapped_column(LargeBinary)
    final_remote_merkle_root: Mapped[bytes | None] = mapped_column(LargeBinary)
    final_pending_commands: Mapped[int | None] = mapped_column(BigInteger)
    final_leased_commands: Mapped[int | None] = mapped_column(BigInteger)
    final_dead_letter_commands: Mapped[int | None] = mapped_column(BigInteger)
    canary_provenance_sha256: Mapped[bytes | None] = mapped_column(LargeBinary)
    final_evidence_sha256: Mapped[bytes | None] = mapped_column(LargeBinary)
    terminal_error_code: Mapped[str | None] = mapped_column(Text)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KtmCacheTargetBoundaryAudit(Base):
    """forward commit 직전의 append-only Pin-owned final boundary receipt."""

    __tablename__ = "ktm_cache_target_boundary_audits"
    __table_args__ = (
        UniqueConstraint("cutover_id", name="uq_ktm_ct_boundary_cutover"),
        ForeignKeyConstraint(
            ["canary_run_id", "canary_provenance_sha256", "final_local_remote_evidence_sha256"],
            [
                "app.ktm_cache_target_canary_runs.run_id",
                "app.ktm_cache_target_canary_runs.canary_provenance_sha256",
                "app.ktm_cache_target_canary_runs.final_evidence_sha256",
            ],
            name="fk_ktm_ct_boundary_canary_evidence",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["consumer_id", "initial_cutover_id", "initial_reconciliation_request_id"],
            [
                "app.ktm_cache_target_consumers.consumer_id",
                "app.ktm_cache_target_consumers.initial_cutover_id",
                "app.ktm_cache_target_consumers.initial_reconciliation_request_id",
            ],
            name="fk_ktm_ct_boundary_initial_consumer",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "initial_reconciliation_request_id",
                "initial_receipt_event_id",
                "initial_expectation_status",
            ],
            [
                "app.ktm_cache_target_reconciliation_expectations.request_id",
                "app.ktm_cache_target_reconciliation_expectations.receipt_event_id",
                "app.ktm_cache_target_reconciliation_expectations.status",
            ],
            name="fk_ktm_ct_boundary_initial_receipt",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            # schema_revision pin은 head migration마다 의식적 re-pin (0049에서
            # 갱신 — services/cache_target_final_boundary.FINALIZE_SCHEMA_REVISION
            # 과 반드시 동일).
            "contract_version = 'pinvi-cache-target-final-boundary/v1' "
            "AND status = 'succeeded' AND schema_revision = '20260804_0049'",
            name=conv("ck_ktm_ct_boundary_contract"),
        ),
        CheckConstraint(
            "source_revision ~ '^[0-9a-f]{40}$' "
            "AND octet_length(database_identity) = 32 "
            "AND octet_length(writer_registry_sha256) = 32 "
            "AND octet_length(initial_writer_fence_sha256) = 32 "
            "AND octet_length(final_writer_fence_sha256) = 32 "
            "AND initial_writer_fence_sha256 <> final_writer_fence_sha256 "
            "AND octet_length(map_final_evidence_sha256) = 32 "
            "AND octet_length(audit_request_sha256) = 32 "
            "AND octet_length(prior_receipt_sha256) = 32",
            name=conv("ck_ktm_ct_boundary_identity"),
        ),
        CheckConstraint(
            "initial_expectation_status = 'received' "
            "AND expected_initial_command_count >= 0 "
            "AND expected_initial_event_count = expected_initial_command_count + 1 "
            "AND expected_initial_claim_item_count = expected_initial_command_count + 1 "
            "AND expected_synthetic_command_count = 2 "
            "AND expected_synthetic_event_count = 2 "
            "AND expected_synthetic_claim_count = 2 "
            "AND pending_command_count = 0 AND leased_command_count = 0 "
            "AND dead_letter_command_count = 0 AND in_flight_command_count = 0 "
            "AND database_in_flight_transaction_count = 0 "
            "AND unexpected_generation7_command_count = 0 "
            "AND unexpected_non_synthetic_event_count = 0 "
            "AND unexpected_non_synthetic_claim_count = 0",
            name=conv("ck_ktm_ct_boundary_zero_counts"),
        ),
        CheckConstraint(
            "octet_length(initial_evidence_sha256) = 32 "
            "AND octet_length(canary_provenance_sha256) = 32 "
            "AND octet_length(final_local_remote_evidence_sha256) = 32 "
            "AND octet_length(evidence_sha256) = 32 "
            "AND runtime_mutation_count = 0 AND external_mutation_count = 0",
            name=conv("ck_ktm_ct_boundary_evidence"),
        ),
        CheckConstraint(
            "email_queue_pending_count >= 0 AND telegram_outbox_pending_count >= 0 "
            "AND location_audit_outbox_pending_count >= 0",
            name=conv("ck_ktm_ct_boundary_app_queue_counts"),
        ),
    )

    transaction_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    cutover_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    source_revision: Mapped[str] = mapped_column(Text, nullable=False)
    database_identity: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    writer_registry_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    initial_writer_fence_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    final_writer_fence_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    map_final_evidence_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    audit_request_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    prior_receipt_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    schema_revision: Mapped[str] = mapped_column(Text, nullable=False)
    canary_run_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    consumer_id: Mapped[str] = mapped_column(Text, nullable=False)
    initial_cutover_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    initial_reconciliation_request_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False
    )
    initial_receipt_event_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False
    )
    initial_expectation_status: Mapped[str] = mapped_column(Text, nullable=False)
    pending_command_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    leased_command_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dead_letter_command_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    in_flight_command_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    database_in_flight_transaction_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    email_queue_pending_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_outbox_pending_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    location_audit_outbox_pending_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_initial_command_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_initial_event_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_initial_claim_item_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_synthetic_command_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_synthetic_event_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_synthetic_claim_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unexpected_generation7_command_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unexpected_non_synthetic_event_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unexpected_non_synthetic_claim_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    initial_evidence_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    canary_provenance_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    final_local_remote_evidence_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    evidence_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    runtime_mutation_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    external_mutation_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KtmCacheTargetEvent(Base):
    """Map at-least-once event의 immutable inbox와 local apply marker."""

    __tablename__ = "ktm_cache_target_events"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "source_event_id",
            "source_generation",
            "source_payload_fingerprint",
            "payload_fingerprint",
            name="uq_ktm_ct_events_provenance",
        ),
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
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        Computed(
            "CASE WHEN event_type = 'cache_target.state_applied' "
            "THEN (payload ->> 'source_event_id')::uuid ELSE NULL END",
            persisted=True,
        ),
    )
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
        UniqueConstraint(
            "consumer_id",
            "initial_cutover_id",
            "initial_reconciliation_request_id",
            name="uq_ktm_ct_consumers_initial_boundary",
        ),
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
        UniqueConstraint(
            "request_id",
            "receipt_event_id",
            "status",
            name="uq_ktm_ct_reconcile_expectations_boundary",
        ),
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
        UniqueConstraint(
            "claim_id",
            "consumer_id",
            "status",
            "acked_through_cursor",
            "completed_at",
            name="uq_ktm_ct_claims_terminal_provenance",
        ),
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
        UniqueConstraint(
            "claim_id",
            "event_id",
            "delivery_cursor",
            "payload_fingerprint",
            "acked_at",
            name="uq_ktm_ct_claim_items_terminal_provenance",
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
