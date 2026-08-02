"""cache target production causal canary의 durable 실행 정본을 추가한다.

Revision ID: 20260802_0048
Revises: 20260801_0047
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260802_0048"
down_revision: str | None = "20260801_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AUDIT_IMMUTABLE_FUNCTION = """
CREATE FUNCTION app.reject_ktm_cache_target_boundary_audit_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
    RAISE EXCEPTION 'cache target boundary audit is append-only' USING ERRCODE = '55000';
END;
$$
"""


def upgrade() -> None:
    op.add_column(
        "ktm_cache_target_events",
        sa.Column(
            "source_event_id",
            postgresql.UUID(as_uuid=True),
            sa.Computed(
                "CASE WHEN event_type = 'cache_target.state_applied' "
                "THEN (payload ->> 'source_event_id')::uuid ELSE NULL END",
                persisted=True,
            ),
            nullable=True,
        ),
        schema="app",
    )
    op.create_unique_constraint(
        "uq_ktm_ct_commands_provenance",
        "ktm_cache_target_commands",
        ["command_id", "poi_id", "source_generation", "payload_fingerprint"],
        schema="app",
    )
    op.create_unique_constraint(
        "uq_ktm_ct_events_provenance",
        "ktm_cache_target_events",
        [
            "event_id",
            "source_event_id",
            "source_generation",
            "source_payload_fingerprint",
            "payload_fingerprint",
        ],
        schema="app",
    )
    op.create_unique_constraint(
        "uq_ktm_ct_claims_terminal_provenance",
        "ktm_cache_target_event_claims",
        ["claim_id", "consumer_id", "status", "acked_through_cursor", "completed_at"],
        schema="app",
    )
    op.create_unique_constraint(
        "uq_ktm_ct_claim_items_terminal_provenance",
        "ktm_cache_target_event_claim_items",
        ["claim_id", "event_id", "delivery_cursor", "payload_fingerprint", "acked_at"],
        schema="app",
    )
    op.create_unique_constraint(
        "uq_ktm_ct_consumers_initial_boundary",
        "ktm_cache_target_consumers",
        ["consumer_id", "initial_cutover_id", "initial_reconciliation_request_id"],
        schema="app",
    )
    op.create_unique_constraint(
        "uq_ktm_ct_reconcile_expectations_boundary",
        "ktm_cache_target_reconciliation_expectations",
        ["request_id", "receipt_event_id", "status"],
        schema="app",
    )
    op.create_table(
        "ktm_cache_target_canary_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_poi_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consumer_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("phase", sa.Text(), nullable=False, server_default="put_enqueued"),
        sa.Column("put_command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delete_command_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("put_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("delete_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("put_claim_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("delete_claim_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("put_generation", sa.BigInteger(), nullable=False),
        sa.Column("delete_generation", sa.BigInteger(), nullable=False),
        sa.Column("put_source_payload_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("delete_source_payload_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("put_event_payload_fingerprint", sa.LargeBinary(), nullable=True),
        sa.Column("delete_event_payload_fingerprint", sa.LargeBinary(), nullable=True),
        sa.Column("put_claim_status", sa.Text(), nullable=True),
        sa.Column("delete_claim_status", sa.Text(), nullable=True),
        sa.Column("put_acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delete_acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("put_claim_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delete_claim_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("put_relay_order", sa.BigInteger(), nullable=True),
        sa.Column("delete_relay_order", sa.BigInteger(), nullable=True),
        sa.Column("baseline_cache_generation", sa.BigInteger(), nullable=False),
        sa.Column("put_cache_generation", sa.BigInteger(), nullable=True),
        sa.Column("final_cache_generation", sa.BigInteger(), nullable=True),
        sa.Column("final_restore_epoch", sa.BigInteger(), nullable=True),
        sa.Column("final_stream_control_version", sa.BigInteger(), nullable=True),
        sa.Column("final_stream_control_etag", sa.Text(), nullable=True),
        sa.Column("baseline_cursor", sa.Text(), nullable=False),
        sa.Column("put_cursor", sa.Text(), nullable=True),
        sa.Column("delete_cursor", sa.Text(), nullable=True),
        sa.Column("final_local_applied_cursor", sa.Text(), nullable=True),
        sa.Column("final_local_remote_acked_cursor", sa.Text(), nullable=True),
        sa.Column("final_remote_snapshot_high_watermark_cursor", sa.Text(), nullable=True),
        sa.Column("baseline_count", sa.BigInteger(), nullable=False),
        sa.Column("baseline_merkle_root", sa.LargeBinary(), nullable=False),
        sa.Column("final_local_count", sa.BigInteger(), nullable=True),
        sa.Column("final_remote_count", sa.BigInteger(), nullable=True),
        sa.Column("final_local_merkle_root", sa.LargeBinary(), nullable=True),
        sa.Column("final_remote_merkle_root", sa.LargeBinary(), nullable=True),
        sa.Column("final_pending_commands", sa.BigInteger(), nullable=True),
        sa.Column("final_leased_commands", sa.BigInteger(), nullable=True),
        sa.Column("final_dead_letter_commands", sa.BigInteger(), nullable=True),
        sa.Column("canary_provenance_sha256", sa.LargeBinary(), nullable=True),
        sa.Column("final_evidence_sha256", sa.LargeBinary(), nullable=True),
        sa.Column("terminal_error_code", sa.Text(), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("run_id", name="pk_ktm_cache_target_canary_runs"),
        sa.UniqueConstraint("put_command_id", name="uq_ktm_ct_canary_put_command"),
        sa.UniqueConstraint("delete_command_id", name="uq_ktm_ct_canary_delete_command"),
        sa.UniqueConstraint("put_event_id", name="uq_ktm_ct_canary_put_event"),
        sa.UniqueConstraint("delete_event_id", name="uq_ktm_ct_canary_delete_event"),
        sa.UniqueConstraint(
            "run_id",
            "canary_provenance_sha256",
            "final_evidence_sha256",
            name="uq_ktm_ct_canary_final_evidence",
        ),
        sa.ForeignKeyConstraint(
            ["target_poi_id"],
            ["app.ktm_cache_target_heads.poi_id"],
            name="fk_ktm_ct_canary_target",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["consumer_id"],
            ["app.ktm_cache_target_consumers.consumer_id"],
            name="fk_ktm_ct_canary_consumer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
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
        sa.CheckConstraint(
            "target_poi_id = '15f98050-27d7-5f85-be21-dc53eded5d7d'::uuid",
            name="ck_ktm_ct_canary_stable_target",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_ktm_ct_canary_status",
        ),
        sa.CheckConstraint(
            "phase IN ('put_enqueued', 'put_applied', 'delete_enqueued', "
            "'delete_applied', 'completed')",
            name="ck_ktm_ct_canary_phase",
        ),
        sa.CheckConstraint(
            "put_generation > 0 AND delete_generation = put_generation + 1 "
            "AND octet_length(put_source_payload_fingerprint) = 32 "
            "AND octet_length(delete_source_payload_fingerprint) = 32 "
            "AND put_source_payload_fingerprint <> delete_source_payload_fingerprint",
            name="ck_ktm_ct_canary_generations",
        ),
        sa.CheckConstraint(
            "baseline_cache_generation >= 0 AND baseline_count >= 0 "
            "AND octet_length(baseline_merkle_root) = 32 AND length(baseline_cursor) > 0",
            name="ck_ktm_ct_canary_baseline",
        ),
        sa.CheckConstraint(
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
            name="ck_ktm_ct_canary_put_material",
        ),
        sa.CheckConstraint(
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
            name="ck_ktm_ct_canary_delete_material",
        ),
        sa.CheckConstraint(
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
            name="ck_ktm_ct_canary_final_material",
        ),
        sa.CheckConstraint(
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
            name="ck_ktm_ct_canary_phase_material",
        ),
        sa.CheckConstraint(
            "(status = 'running' AND terminal_error_code IS NULL AND failed_at IS NULL "
            "AND completed_at IS NULL AND phase <> 'completed') OR "
            "(status = 'succeeded' AND terminal_error_code IS NULL AND failed_at IS NULL "
            "AND completed_at IS NOT NULL AND phase = 'completed') OR "
            "(status = 'failed' AND length(terminal_error_code) > 0 "
            "AND failed_at IS NOT NULL AND completed_at IS NULL AND phase <> 'completed')",
            name="ck_ktm_ct_canary_terminal",
        ),
        schema="app",
    )
    op.create_index(
        "uq_ktm_ct_canary_running_target",
        "ktm_cache_target_canary_runs",
        ["target_poi_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_table(
        "ktm_cache_target_boundary_audits",
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cutover_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source_revision", sa.Text(), nullable=False),
        sa.Column("database_identity", sa.LargeBinary(), nullable=False),
        sa.Column("writer_registry_sha256", sa.LargeBinary(), nullable=False),
        sa.Column("initial_writer_fence_sha256", sa.LargeBinary(), nullable=False),
        sa.Column("final_writer_fence_sha256", sa.LargeBinary(), nullable=False),
        sa.Column("map_final_evidence_sha256", sa.LargeBinary(), nullable=False),
        sa.Column("audit_request_sha256", sa.LargeBinary(), nullable=False),
        sa.Column("prior_receipt_sha256", sa.LargeBinary(), nullable=False),
        sa.Column("schema_revision", sa.Text(), nullable=False),
        sa.Column("canary_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consumer_id", sa.Text(), nullable=False),
        sa.Column("initial_cutover_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "initial_reconciliation_request_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("initial_receipt_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("initial_expectation_status", sa.Text(), nullable=False),
        sa.Column("pending_command_count", sa.BigInteger(), nullable=False),
        sa.Column("leased_command_count", sa.BigInteger(), nullable=False),
        sa.Column("dead_letter_command_count", sa.BigInteger(), nullable=False),
        sa.Column("in_flight_command_count", sa.BigInteger(), nullable=False),
        sa.Column("database_in_flight_transaction_count", sa.BigInteger(), nullable=False),
        sa.Column("email_queue_pending_count", sa.BigInteger(), nullable=False),
        sa.Column("telegram_outbox_pending_count", sa.BigInteger(), nullable=False),
        sa.Column("location_audit_outbox_pending_count", sa.BigInteger(), nullable=False),
        sa.Column("expected_initial_command_count", sa.BigInteger(), nullable=False),
        sa.Column("expected_initial_event_count", sa.BigInteger(), nullable=False),
        sa.Column("expected_initial_claim_item_count", sa.BigInteger(), nullable=False),
        sa.Column("expected_synthetic_command_count", sa.BigInteger(), nullable=False),
        sa.Column("expected_synthetic_event_count", sa.BigInteger(), nullable=False),
        sa.Column("expected_synthetic_claim_count", sa.BigInteger(), nullable=False),
        sa.Column("unexpected_generation7_command_count", sa.BigInteger(), nullable=False),
        sa.Column("unexpected_non_synthetic_event_count", sa.BigInteger(), nullable=False),
        sa.Column("unexpected_non_synthetic_claim_count", sa.BigInteger(), nullable=False),
        sa.Column("initial_evidence_sha256", sa.LargeBinary(), nullable=False),
        sa.Column("canary_provenance_sha256", sa.LargeBinary(), nullable=False),
        sa.Column("final_local_remote_evidence_sha256", sa.LargeBinary(), nullable=False),
        sa.Column("evidence_sha256", sa.LargeBinary(), nullable=False),
        sa.Column("runtime_mutation_count", sa.BigInteger(), nullable=False),
        sa.Column("external_mutation_count", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("transaction_id", name="pk_ktm_cache_target_boundary_audits"),
        sa.UniqueConstraint("cutover_id", name="uq_ktm_ct_boundary_cutover"),
        sa.ForeignKeyConstraint(
            ["canary_run_id", "canary_provenance_sha256", "final_local_remote_evidence_sha256"],
            [
                "app.ktm_cache_target_canary_runs.run_id",
                "app.ktm_cache_target_canary_runs.canary_provenance_sha256",
                "app.ktm_cache_target_canary_runs.final_evidence_sha256",
            ],
            name="fk_ktm_ct_boundary_canary_evidence",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["consumer_id", "initial_cutover_id", "initial_reconciliation_request_id"],
            [
                "app.ktm_cache_target_consumers.consumer_id",
                "app.ktm_cache_target_consumers.initial_cutover_id",
                "app.ktm_cache_target_consumers.initial_reconciliation_request_id",
            ],
            name="fk_ktm_ct_boundary_initial_consumer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
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
        sa.CheckConstraint(
            "contract_version = 'pinvi-cache-target-final-boundary/v1' "
            "AND status = 'succeeded' AND schema_revision = '20260802_0048'",
            name="ck_ktm_ct_boundary_contract",
        ),
        sa.CheckConstraint(
            "source_revision ~ '^[0-9a-f]{40}$' "
            "AND octet_length(database_identity) = 32 "
            "AND octet_length(writer_registry_sha256) = 32 "
            "AND octet_length(initial_writer_fence_sha256) = 32 "
            "AND octet_length(final_writer_fence_sha256) = 32 "
            "AND initial_writer_fence_sha256 <> final_writer_fence_sha256 "
            "AND octet_length(map_final_evidence_sha256) = 32 "
            "AND octet_length(audit_request_sha256) = 32 "
            "AND octet_length(prior_receipt_sha256) = 32",
            name="ck_ktm_ct_boundary_identity",
        ),
        sa.CheckConstraint(
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
            name="ck_ktm_ct_boundary_zero_counts",
        ),
        sa.CheckConstraint(
            "email_queue_pending_count >= 0 AND telegram_outbox_pending_count >= 0 "
            "AND location_audit_outbox_pending_count >= 0",
            name="ck_ktm_ct_boundary_app_queue_counts",
        ),
        sa.CheckConstraint(
            "octet_length(initial_evidence_sha256) = 32 "
            "AND octet_length(canary_provenance_sha256) = 32 "
            "AND octet_length(final_local_remote_evidence_sha256) = 32 "
            "AND octet_length(evidence_sha256) = 32 "
            "AND runtime_mutation_count = 0 AND external_mutation_count = 0",
            name="ck_ktm_ct_boundary_evidence",
        ),
        schema="app",
    )
    op.execute(sa.text(_AUDIT_IMMUTABLE_FUNCTION))
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_ktm_ct_boundary_audit_row_immutable "
            "BEFORE UPDATE OR DELETE ON app.ktm_cache_target_boundary_audits "
            "FOR EACH ROW EXECUTE FUNCTION app.reject_ktm_cache_target_boundary_audit_mutation()"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_ktm_ct_boundary_audit_truncate_immutable "
            "BEFORE TRUNCATE ON app.ktm_cache_target_boundary_audits "
            "FOR EACH STATEMENT EXECUTE FUNCTION "
            "app.reject_ktm_cache_target_boundary_audit_mutation()"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_ktm_ct_boundary_audit_truncate_immutable "
            "ON app.ktm_cache_target_boundary_audits"
        )
    )
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_ktm_ct_boundary_audit_row_immutable "
            "ON app.ktm_cache_target_boundary_audits"
        )
    )
    op.drop_table("ktm_cache_target_boundary_audits", schema="app")
    op.execute(sa.text("DROP FUNCTION app.reject_ktm_cache_target_boundary_audit_mutation()"))
    op.drop_index(
        "uq_ktm_ct_canary_running_target",
        table_name="ktm_cache_target_canary_runs",
        schema="app",
    )
    op.drop_table("ktm_cache_target_canary_runs", schema="app")
    op.drop_constraint(
        "uq_ktm_ct_reconcile_expectations_boundary",
        "ktm_cache_target_reconciliation_expectations",
        schema="app",
        type_="unique",
    )
    op.drop_constraint(
        "uq_ktm_ct_consumers_initial_boundary",
        "ktm_cache_target_consumers",
        schema="app",
        type_="unique",
    )
    op.drop_constraint(
        "uq_ktm_ct_claim_items_terminal_provenance",
        "ktm_cache_target_event_claim_items",
        schema="app",
        type_="unique",
    )
    op.drop_constraint(
        "uq_ktm_ct_claims_terminal_provenance",
        "ktm_cache_target_event_claims",
        schema="app",
        type_="unique",
    )
    op.drop_constraint(
        "uq_ktm_ct_events_provenance",
        "ktm_cache_target_events",
        schema="app",
        type_="unique",
    )
    op.drop_column("ktm_cache_target_events", "source_event_id", schema="app")
    op.drop_constraint(
        "uq_ktm_ct_commands_provenance",
        "ktm_cache_target_commands",
        schema="app",
        type_="unique",
    )
