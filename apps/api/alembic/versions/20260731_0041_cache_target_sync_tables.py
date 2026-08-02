"""cache target canonical POI columns and durable sync tables (ADR-058)

Revision ID: 20260731_0041
Revises: 20260721_0040
Create Date: 2026-07-31 20:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.sql.elements import conv

from alembic import op

revision: str = "20260731_0041"
down_revision: str | None = "20260721_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def _add_trip_day_poi_columns() -> None:
    op.add_column(
        "trip_day_pois",
        sa.Column(
            "cache_target_lon",
            sa.Numeric(),
            sa.Computed(
                "COALESCE(feature_snapshot #>> '{coord,lon}', feature_snapshot ->> 'lon')::numeric",
                persisted=True,
            ),
        ),
        schema="app",
    )
    op.add_column(
        "trip_day_pois",
        sa.Column(
            "cache_target_lat",
            sa.Numeric(),
            sa.Computed(
                "COALESCE(feature_snapshot #>> '{coord,lat}', feature_snapshot ->> 'lat')::numeric",
                persisted=True,
            ),
        ),
        schema="app",
    )
    op.add_column(
        "trip_day_pois",
        sa.Column(
            "cache_target_radius_km",
            sa.Numeric(),
            nullable=False,
            server_default=sa.text("5.000"),
        ),
        schema="app",
    )
    op.add_column(
        "trip_day_pois",
        sa.Column(
            "cache_target_update_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        schema="app",
    )
    checks = (
        (
            "ck_trip_day_pois_cache_coord_pair",
            "(cache_target_lon IS NULL) = (cache_target_lat IS NULL)",
        ),
        (
            "ck_trip_day_pois_cache_lon_korea",
            "cache_target_lon IS NULL OR cache_target_lon BETWEEN 124 AND 132",
        ),
        (
            "ck_trip_day_pois_cache_lat_korea",
            "cache_target_lat IS NULL OR cache_target_lat BETWEEN 33 AND 39.5",
        ),
        (
            "ck_trip_day_pois_cache_radius",
            "cache_target_radius_km > 0 AND cache_target_radius_km <= 100",
        ),
        (
            "ck_tdp_cache_lon_consistent",
            "feature_snapshot #>> '{coord,lon}' IS NULL OR feature_snapshot ->> 'lon' IS NULL "
            "OR (feature_snapshot #>> '{coord,lon}')::numeric = "
            "(feature_snapshot ->> 'lon')::numeric",
        ),
        (
            "ck_tdp_cache_lat_consistent",
            "feature_snapshot #>> '{coord,lat}' IS NULL OR feature_snapshot ->> 'lat' IS NULL "
            "OR (feature_snapshot #>> '{coord,lat}')::numeric = "
            "(feature_snapshot ->> 'lat')::numeric",
        ),
    )
    for name, condition in checks:
        op.create_check_constraint(conv(name), "trip_day_pois", condition, schema="app")


def _create_head() -> None:
    op.create_table(
        "ktm_cache_target_heads",
        sa.Column("poi_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("external_system", sa.String(32), nullable=False, server_default="pinvi"),
        sa.Column("target_key", sa.String(36), nullable=False),
        sa.Column("desired_state", sa.String(16), nullable=False),
        sa.Column("source_generation", sa.BigInteger(), nullable=False),
        sa.Column("source_payload_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("lon", sa.Numeric()),
        sa.Column("lat", sa.Numeric()),
        sa.Column("radius_km", sa.Numeric(), nullable=False),
        sa.Column("update_enabled", sa.Boolean(), nullable=False),
        sa.Column("remote_target_id", PgUUID(as_uuid=True)),
        sa.Column("remote_etag", sa.Text()),
        sa.Column("remote_restore_epoch", sa.BigInteger()),
        sa.Column("remote_source_generation", sa.BigInteger()),
        sa.Column("remote_target_sequence", sa.BigInteger()),
        sa.Column("remote_status", sa.String(32)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("poi_id", name="pk_ktm_cache_target_heads"),
        sa.UniqueConstraint("external_system", "target_key", name="uq_ktm_ct_heads_system_key"),
        sa.CheckConstraint("external_system = 'pinvi'", name=conv("ck_ktm_ct_heads_system")),
        sa.CheckConstraint(
            "target_key = lower(poi_id::text)", name=conv("ck_ktm_ct_heads_target_key")
        ),
        sa.CheckConstraint(
            "desired_state IN ('active', 'deleted')", name=conv("ck_ktm_ct_heads_state")
        ),
        sa.CheckConstraint("source_generation > 0", name=conv("ck_ktm_ct_heads_generation")),
        sa.CheckConstraint(
            "octet_length(source_payload_fingerprint) = 32",
            name=conv("ck_ktm_ct_heads_fingerprint"),
        ),
        sa.CheckConstraint(
            "desired_state = 'deleted' OR (lon IS NOT NULL AND lat IS NOT NULL)",
            name=conv("ck_ktm_ct_heads_active_coord"),
        ),
        sa.CheckConstraint(
            "lon IS NULL OR lon BETWEEN 124 AND 132", name=conv("ck_ktm_ct_heads_lon")
        ),
        sa.CheckConstraint(
            "lat IS NULL OR lat BETWEEN 33 AND 39.5", name=conv("ck_ktm_ct_heads_lat")
        ),
        sa.CheckConstraint(
            "radius_km > 0 AND radius_km <= 100", name=conv("ck_ktm_ct_heads_radius")
        ),
        sa.CheckConstraint(
            "remote_restore_epoch IS NULL OR remote_restore_epoch > 0",
            name=conv("ck_ktm_ct_heads_remote_epoch"),
        ),
        sa.CheckConstraint(
            "remote_source_generation IS NULL OR remote_source_generation > 0",
            name=conv("ck_ktm_ct_heads_remote_generation"),
        ),
        sa.CheckConstraint(
            "remote_target_sequence IS NULL OR remote_target_sequence > 0",
            name=conv("ck_ktm_ct_heads_remote_sequence"),
        ),
        schema="app",
    )


def _create_commands() -> None:
    op.create_table(
        "ktm_cache_target_commands",
        sa.Column("command_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("poi_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("source_generation", sa.BigInteger(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("payload_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("expected_etag", sa.Text()),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("response_status", sa.Integer()),
        sa.Column("response_body", JSONB()),
        sa.Column("response_etag", sa.Text()),
        sa.Column("error_code", sa.String(96)),
        sa.Column("error_detail", JSONB()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("command_id", name="pk_ktm_cache_target_commands"),
        sa.ForeignKeyConstraint(
            ["poi_id"],
            ["app.ktm_cache_target_heads.poi_id"],
            name="fk_ktm_ct_commands_poi",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "operation IN ('put', 'delete', 'refresh')",
            name=conv("ck_ktm_ct_commands_operation"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'leased', 'succeeded', 'superseded', 'dead_letter')",
            name=conv("ck_ktm_ct_commands_status"),
        ),
        sa.CheckConstraint("source_generation > 0", name=conv("ck_ktm_ct_commands_generation")),
        sa.CheckConstraint("attempts >= 0", name=conv("ck_ktm_ct_commands_attempts")),
        sa.CheckConstraint(
            "octet_length(payload_fingerprint) = 32",
            name=conv("ck_ktm_ct_commands_fingerprint"),
        ),
        sa.CheckConstraint(
            "(lease_owner IS NULL) = (lease_until IS NULL)",
            name=conv("ck_ktm_ct_commands_lease_pair"),
        ),
        schema="app",
    )
    op.create_index(
        "uq_ktm_ct_commands_state_generation",
        "ktm_cache_target_commands",
        ["poi_id", "source_generation", "operation"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("operation IN ('put', 'delete')"),
    )
    op.create_index(
        "ix_ktm_ct_commands_due",
        "ktm_cache_target_commands",
        ["available_at", "command_id"],
        schema="app",
        postgresql_where=sa.text("status IN ('pending', 'leased')"),
    )
    op.create_index(
        "ix_ktm_ct_commands_lease",
        "ktm_cache_target_commands",
        ["lease_until", "command_id"],
        schema="app",
        postgresql_where=sa.text("status = 'leased'"),
    )


def _create_events() -> None:
    op.create_table(
        "ktm_cache_target_events",
        sa.Column("event_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("external_system", sa.String(32), nullable=False),
        sa.Column("target_key", sa.String(36), nullable=False),
        sa.Column("target_id", PgUUID(as_uuid=True)),
        sa.Column("restore_epoch", sa.BigInteger(), nullable=False),
        sa.Column("source_generation", sa.BigInteger(), nullable=False),
        sa.Column("target_sequence", sa.BigInteger(), nullable=False),
        sa.Column("relay_order", sa.BigInteger(), nullable=False),
        sa.Column("source_payload_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("event_id", name="pk_ktm_cache_target_events"),
        sa.UniqueConstraint(
            "external_system",
            "target_key",
            "restore_epoch",
            "source_generation",
            "target_sequence",
            name="uq_ktm_ct_events_target_sequence",
        ),
        sa.CheckConstraint("external_system = 'pinvi'", name=conv("ck_ktm_ct_events_system")),
        sa.CheckConstraint(
            "event_type IN ('cache_target.state_applied', "
            "'cache_target.links_reconciled', 'refresh_request.status_changed', "
            "'cache_target.reconciled')",
            name=conv("ck_ktm_ct_events_type"),
        ),
        sa.CheckConstraint("restore_epoch > 0", name=conv("ck_ktm_ct_events_epoch")),
        sa.CheckConstraint("source_generation > 0", name=conv("ck_ktm_ct_events_generation")),
        sa.CheckConstraint("target_sequence > 0", name=conv("ck_ktm_ct_events_sequence")),
        sa.CheckConstraint("relay_order > 0", name=conv("ck_ktm_ct_events_relay_order")),
        sa.CheckConstraint(
            "octet_length(source_payload_fingerprint) = 32",
            name=conv("ck_ktm_ct_events_fingerprint"),
        ),
        schema="app",
    )
    op.create_index(
        "ix_ktm_ct_events_epoch_relay",
        "ktm_cache_target_events",
        ["restore_epoch", "relay_order"],
        schema="app",
    )


def _create_consumers() -> None:
    op.create_table(
        "ktm_cache_target_consumers",
        sa.Column("consumer_id", sa.String(64), nullable=False),
        sa.Column("external_system", sa.String(32), nullable=False, server_default="pinvi"),
        sa.Column("active_restore_epoch", sa.BigInteger()),
        sa.Column("local_applied_cursor", sa.Text()),
        sa.Column("remote_acked_cursor", sa.Text()),
        sa.Column("high_watermark_cursor", sa.Text()),
        sa.Column("stream_control_etag", sa.Text()),
        sa.Column("snapshot_id", sa.Text()),
        sa.Column("snapshot_count", sa.BigInteger()),
        sa.Column("snapshot_merkle_root", sa.LargeBinary()),
        sa.Column(
            "reconcile_status", sa.String(16), nullable=False, server_default="uninitialized"
        ),
        sa.Column("feature_cache_generation", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("ready", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
        sa.PrimaryKeyConstraint("consumer_id", name="pk_ktm_cache_target_consumers"),
        sa.CheckConstraint("external_system = 'pinvi'", name=conv("ck_ktm_ct_consumers_system")),
        sa.CheckConstraint(
            "active_restore_epoch IS NULL OR active_restore_epoch > 0",
            name=conv("ck_ktm_ct_consumers_epoch"),
        ),
        sa.CheckConstraint(
            "reconcile_status IN ('uninitialized', 'checking', 'matched', 'mismatched', 'blocked')",
            name=conv("ck_ktm_ct_consumers_reconcile"),
        ),
        sa.CheckConstraint(
            "feature_cache_generation >= 0",
            name=conv("ck_ktm_ct_consumers_cache_generation"),
        ),
        sa.CheckConstraint(
            "snapshot_count IS NULL OR snapshot_count >= 0",
            name=conv("ck_ktm_ct_consumers_snapshot_count"),
        ),
        sa.CheckConstraint(
            "snapshot_merkle_root IS NULL OR octet_length(snapshot_merkle_root) = 32",
            name=conv("ck_ktm_ct_consumers_merkle"),
        ),
        schema="app",
    )


def _create_event_claims() -> None:
    op.create_table(
        "ktm_cache_target_event_claims",
        sa.Column("claim_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("consumer_id", sa.String(64), nullable=False),
        sa.Column("lease_token", PgUUID(as_uuid=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("acked_through_cursor", sa.Text()),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("claim_id", name="pk_ktm_cache_target_event_claims"),
        sa.ForeignKeyConstraint(
            ["consumer_id"],
            ["app.ktm_cache_target_consumers.consumer_id"],
            name="fk_ktm_ct_event_claims_consumer",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("lease_token", name="uq_ktm_ct_event_claims_lease_token"),
        sa.CheckConstraint(
            "status IN ('active', 'acked', 'expired', 'invalidated')",
            name=conv("ck_ktm_ct_event_claims_status"),
        ),
        sa.CheckConstraint(
            "(status = 'active' AND completed_at IS NULL) OR "
            "(status <> 'active' AND completed_at IS NOT NULL)",
            name=conv("ck_ktm_ct_event_claims_completion"),
        ),
        schema="app",
    )
    op.create_index(
        "ix_ktm_ct_event_claims_lease",
        "ktm_cache_target_event_claims",
        ["lease_expires_at", "claim_id"],
        schema="app",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "ktm_cache_target_event_claim_items",
        sa.Column("claim_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("event_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("delivery_cursor", sa.Text(), nullable=False),
        sa.Column("payload_fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("acked_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint(
            "claim_id",
            "event_id",
            name="pk_ktm_cache_target_event_claim_items",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["app.ktm_cache_target_event_claims.claim_id"],
            name="fk_ktm_ct_claim_items_claim",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["app.ktm_cache_target_events.event_id"],
            name="fk_ktm_ct_claim_items_event",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "claim_id",
            "delivery_cursor",
            name="uq_ktm_ct_claim_items_cursor",
        ),
        sa.UniqueConstraint(
            "claim_id",
            "position",
            name="uq_ktm_ct_claim_items_position",
        ),
        sa.CheckConstraint("position > 0", name=conv("ck_ktm_ct_claim_items_position")),
        sa.CheckConstraint(
            "octet_length(payload_fingerprint) = 32",
            name=conv("ck_ktm_ct_claim_items_fingerprint"),
        ),
        schema="app",
    )
    op.create_index(
        "ix_ktm_ct_claim_items_ack_gap",
        "ktm_cache_target_event_claim_items",
        ["claim_id", "position"],
        schema="app",
        postgresql_where=sa.text("acked_at IS NULL"),
    )


def _add_touch_triggers() -> None:
    for table in (
        "ktm_cache_target_heads",
        "ktm_cache_target_commands",
        "ktm_cache_target_consumers",
    ):
        op.execute(
            sa.text(
                f"CREATE TRIGGER trg_{table}_touch "
                f"BEFORE UPDATE ON app.{table} "
                "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
            )
        )


def upgrade() -> None:
    _add_trip_day_poi_columns()
    _create_head()
    _create_commands()
    _create_events()
    _create_consumers()
    _create_event_claims()
    _add_touch_triggers()


def downgrade() -> None:
    for table in (
        "ktm_cache_target_consumers",
        "ktm_cache_target_commands",
        "ktm_cache_target_heads",
    ):
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table}_touch ON app.{table}"))
    op.drop_index(
        "ix_ktm_ct_claim_items_ack_gap",
        table_name="ktm_cache_target_event_claim_items",
        schema="app",
    )
    op.drop_table("ktm_cache_target_event_claim_items", schema="app")
    op.drop_index(
        "ix_ktm_ct_event_claims_lease",
        table_name="ktm_cache_target_event_claims",
        schema="app",
    )
    op.drop_table("ktm_cache_target_event_claims", schema="app")
    op.drop_table("ktm_cache_target_consumers", schema="app")
    op.drop_index(
        "ix_ktm_ct_events_epoch_relay", table_name="ktm_cache_target_events", schema="app"
    )
    op.drop_table("ktm_cache_target_events", schema="app")
    op.drop_index("ix_ktm_ct_commands_lease", table_name="ktm_cache_target_commands", schema="app")
    op.drop_index("ix_ktm_ct_commands_due", table_name="ktm_cache_target_commands", schema="app")
    op.drop_index(
        "uq_ktm_ct_commands_state_generation",
        table_name="ktm_cache_target_commands",
        schema="app",
    )
    op.drop_table("ktm_cache_target_commands", schema="app")
    op.drop_table("ktm_cache_target_heads", schema="app")
    for name in (
        "ck_tdp_cache_lat_consistent",
        "ck_tdp_cache_lon_consistent",
        "ck_trip_day_pois_cache_radius",
        "ck_trip_day_pois_cache_lat_korea",
        "ck_trip_day_pois_cache_lon_korea",
        "ck_trip_day_pois_cache_coord_pair",
    ):
        op.drop_constraint(conv(name), "trip_day_pois", schema="app", type_="check")
    op.drop_column("trip_day_pois", "cache_target_update_enabled", schema="app")
    op.drop_column("trip_day_pois", "cache_target_radius_km", schema="app")
    op.drop_column("trip_day_pois", "cache_target_lat", schema="app")
    op.drop_column("trip_day_pois", "cache_target_lon", schema="app")
