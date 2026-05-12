"""apply library spec v3 db schema

Revision ID: 20260513_0024
Revises: 20260509_0023
Create Date: 2026-05-13 06:20:00
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260513_0024"
down_revision: str | None = "20260509_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis_topology")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    _upgrade_users()
    _upgrade_trips()
    _create_auth_tables()
    _create_feature_tables()
    _create_trip_collaboration_tables()
    _create_admin_tables()


def downgrade() -> None:
    _drop_admin_tables()
    _drop_trip_collaboration_tables()
    _drop_feature_tables()
    _drop_auth_tables()
    _downgrade_trips()
    _downgrade_users()


def _upgrade_users() -> None:
    op.add_column("users", sa.Column("google_sub", sa.String(length=255)))
    op.add_column("users", sa.Column("avatar_url", sa.Text()))
    op.add_column(
        "users",
        sa.Column("avatar_kind", sa.String(length=20), nullable=False, server_default="default"),
    )
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "users",
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending_verification",
        ),
    )
    op.add_column("users", sa.Column("birth_yyyymm", sa.String(length=6)))
    op.add_column("users", sa.Column("sigungu_code", sa.String(length=5)))
    op.execute("UPDATE users SET email_verified = true WHERE email_verified_at IS NOT NULL")
    op.execute(
        """
        UPDATE users
        SET status = CASE account_status
            WHEN 'active' THEN 'active'
            WHEN 'disabled' THEN 'disabled'
            WHEN 'deleted' THEN 'disabled'
            WHEN 'invited' THEN 'pending_profile'
            ELSE 'pending_verification'
        END
        """
    )
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.drop_constraint("ck_users_gender", "users", type_="check")
    op.create_check_constraint(
        "ck_users_gender",
        "users",
        "gender IS NULL OR gender IN "
        "('female', 'male', 'non_binary', 'no_answer', 'm', 'f', 'other')",
    )
    op.create_check_constraint(
        "ck_users_avatar_kind",
        "users",
        "avatar_kind IN ('default', 'upload')",
    )
    op.create_check_constraint(
        "ck_users_birth_yyyymm_format",
        "users",
        "birth_yyyymm IS NULL OR birth_yyyymm ~ '^[0-9]{6}$'",
    )
    op.create_check_constraint(
        "ck_users_status",
        "users",
        "status IN ('pending_verification', 'pending_profile', 'active', 'disabled')",
    )
    op.create_unique_constraint("uq_users_google_sub", "users", ["google_sub"])
    op.create_index("ix_users_status", "users", ["status"])


def _downgrade_users() -> None:
    op.drop_index("ix_users_status", table_name="users")
    op.drop_constraint("uq_users_google_sub", "users", type_="unique")
    op.drop_constraint("ck_users_status", "users", type_="check")
    op.drop_constraint("ck_users_birth_yyyymm_format", "users", type_="check")
    op.drop_constraint("ck_users_avatar_kind", "users", type_="check")
    op.drop_constraint("ck_users_gender", "users", type_="check")
    op.create_check_constraint(
        "ck_users_gender",
        "users",
        "gender IS NULL OR gender IN ('female', 'male', 'non_binary', 'no_answer')",
    )
    op.execute("UPDATE users SET password_hash = '' WHERE password_hash IS NULL")
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.drop_column("users", "sigungu_code")
    op.drop_column("users", "birth_yyyymm")
    op.drop_column("users", "status")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "avatar_kind")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "google_sub")


def _upgrade_trips() -> None:
    op.add_column("trips", sa.Column("leader_id", postgresql.UUID(as_uuid=True)))
    op.add_column("trips", sa.Column("name", sa.Text()))
    op.add_column("trips", sa.Column("fuel_types", postgresql.ARRAY(sa.String(length=40))))
    op.add_column("trips", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE trips SET leader_id = user_id, name = title")
    op.create_foreign_key(
        "fk_trips_leader_id",
        "trips",
        "users",
        ["leader_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_trips_leader_id", "trips", ["leader_id"])


def _downgrade_trips() -> None:
    op.drop_index("ix_trips_leader_id", table_name="trips")
    op.drop_constraint("fk_trips_leader_id", "trips", type_="foreignkey")
    op.drop_column("trips", "deleted_at")
    op.drop_column("trips", "fuel_types")
    op.drop_column("trips", "name")
    op.drop_column("trips", "leader_id")


def _create_auth_tables() -> None:
    op.create_table(
        "user_consents",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consent_type", sa.String(length=40), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column(
            "agreed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "consent_type IN ('tos', 'privacy', 'demographic_use', 'location_use', 'marketing')",
            name="ck_user_consents_type",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_consents_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "consent_type", "version", name="pk_user_consents"),
    )
    op.create_index("ix_user_consents_user", "user_consents", ["user_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column(
            "jti",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("user_agent", sa.Text()),
        sa.Column("ip_addr", postgresql.INET()),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_refresh_tokens_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("jti", name="pk_refresh_tokens"),
    )
    op.create_index(
        "ix_refresh_tokens_user_revoked",
        "refresh_tokens",
        ["user_id", "revoked_at"],
    )


def _drop_auth_tables() -> None:
    op.drop_index("ix_refresh_tokens_user_revoked", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_user_consents_user", table_name="user_consents")
    op.drop_table("user_consents")


def _create_feature_tables() -> None:
    op.create_table(
        "bjd_lookup",
        sa.Column("bjd_code", sa.String(length=10), nullable=False),
        sa.Column("sido", sa.Text(), nullable=False),
        sa.Column("sigungu", sa.Text()),
        sa.Column("eupmyeondong", sa.Text()),
        sa.Column("ri", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at_src", sa.Date()),
        sa.Column("deleted_at_src", sa.Date()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("bjd_code", name="pk_bjd_lookup"),
    )
    op.create_index(
        "ix_bjd_lookup_sido_trgm",
        "bjd_lookup",
        ["sido"],
        postgresql_using="gin",
        postgresql_ops={"sido": "gin_trgm_ops"},
    )

    op.create_table(
        "features",
        sa.Column("feature_id", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("bjd_code", sa.String(length=10)),
        sa.Column(
            "coord",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
        ),
        sa.Column("address_road", sa.Text()),
        sa.Column("address_jibun", sa.Text()),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("parent_feature_id", sa.String(length=120)),
        sa.Column("sibling_group_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "urls", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("marker_icon", sa.Text(), nullable=False),
        sa.Column("marker_color", sa.String(length=16), nullable=False),
        sa.Column("detail", postgresql.JSONB()),
        sa.Column(
            "raw_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "kind IN ('place', 'event', 'notice', 'price', 'weather', 'route', 'area')",
            name="ck_features_kind",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'hidden', 'broken')",
            name="ck_features_status",
        ),
        sa.ForeignKeyConstraint(
            ["bjd_code"],
            ["bjd_lookup.bjd_code"],
            name="fk_features_bjd_code",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["parent_feature_id"],
            ["features.feature_id"],
            name="fk_features_parent",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("feature_id", name="pk_features"),
    )
    op.create_index("ix_features_coord", "features", ["coord"], postgresql_using="gist")
    op.create_index("ix_features_geom", "features", ["geom"], postgresql_using="gist")
    op.create_index(
        "ix_features_kind_category",
        "features",
        ["kind", "category"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_features_parent", "features", ["parent_feature_id"])
    op.create_index("ix_features_sibling_group", "features", ["sibling_group_id"])
    op.create_index("ix_features_bjd_code", "features", ["bjd_code"])
    op.create_index(
        "ix_features_name_trgm",
        "features",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    op.create_table(
        "price_points",
        sa.Column("feature_id", sa.String(length=120), nullable=False),
        sa.Column("price_category", sa.String(length=40), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="3650"),
        sa.ForeignKeyConstraint(
            ["feature_id"],
            ["features.feature_id"],
            name="fk_price_points_feature",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("feature_id", name="pk_price_points"),
    )

    op.create_table(
        "price_values",
        sa.Column("feature_id", sa.String(length=120), nullable=False),
        sa.Column("item_key", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="KRW"),
        sa.ForeignKeyConstraint(
            ["feature_id"],
            ["price_points.feature_id"],
            name="fk_price_values_feature",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "feature_id",
            "item_key",
            "observed_at",
            name="pk_price_values",
        ),
    )
    op.create_index(
        "ix_price_values_observed_at",
        "price_values",
        ["observed_at"],
        postgresql_using="brin",
    )

    op.create_table(
        "weather_observations",
        sa.Column("feature_id", sa.String(length=120), nullable=False),
        sa.Column("forecast_kind", sa.String(length=32), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "forecast_kind IN ('nowcast', 'short', 'mid', 'observed', 'warning')",
            name="ck_weather_observations_kind",
        ),
        sa.ForeignKeyConstraint(
            ["feature_id"],
            ["features.feature_id"],
            name="fk_weather_obs_feature",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "feature_id",
            "forecast_kind",
            "valid_at",
            "issued_at",
            name="pk_weather_observations",
        ),
    )
    op.create_index(
        "ix_weather_obs_valid_at",
        "weather_observations",
        ["valid_at"],
        postgresql_using="brin",
    )


def _drop_feature_tables() -> None:
    op.drop_index("ix_weather_obs_valid_at", table_name="weather_observations")
    op.drop_table("weather_observations")
    op.drop_index("ix_price_values_observed_at", table_name="price_values")
    op.drop_table("price_values")
    op.drop_table("price_points")
    op.drop_index("ix_features_name_trgm", table_name="features")
    op.drop_index("ix_features_bjd_code", table_name="features")
    op.drop_index("ix_features_sibling_group", table_name="features")
    op.drop_index("ix_features_parent", table_name="features")
    op.drop_index("ix_features_kind_category", table_name="features")
    op.drop_index("ix_features_geom", table_name="features")
    op.drop_index("ix_features_coord", table_name="features")
    op.drop_table("features")
    op.drop_index("ix_bjd_lookup_sido_trgm", table_name="bjd_lookup")
    op.drop_table("bjd_lookup")


def _create_trip_collaboration_tables() -> None:
    op.create_table(
        "trip_members",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("invited_email", postgresql.CITEXT()),
        sa.Column("invited_nickname", sa.Text()),
        sa.Column("invited_gender", sa.String(length=32)),
        sa.Column("invited_birth_yyyymm", sa.String(length=6)),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="companion"),
        sa.Column(
            "invited_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("joined_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "user_id IS NOT NULL OR invited_email IS NOT NULL",
            name="ck_trip_members_identity",
        ),
        sa.CheckConstraint("role IN ('companion')", name="ck_trip_members_role"),
        sa.CheckConstraint(
            "invited_birth_yyyymm IS NULL OR invited_birth_yyyymm ~ '^[0-9]{6}$'",
            name="ck_trip_members_birth_yyyymm",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
            name="fk_trip_members_trip_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_trip_members_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trip_members"),
    )
    op.create_index("ix_trip_members_trip_user", "trip_members", ["trip_id", "user_id"])
    op.create_index("ix_trip_members_user", "trip_members", ["user_id"])
    op.create_index(
        "uq_trip_members_trip_user",
        "trip_members",
        ["trip_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_trip_members_trip_email",
        "trip_members",
        ["trip_id", "invited_email"],
        unique=True,
        postgresql_where=sa.text("invited_email IS NOT NULL"),
    )

    op.create_table(
        "trip_pois",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.String(length=80), nullable=False),
        sa.Column("feature_id", sa.String(length=120)),
        sa.Column("feature_link_broken_at", sa.DateTime(timezone=True)),
        sa.Column(
            "snapshot", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("custom_marker_color", sa.String(length=16)),
        sa.Column("custom_marker_icon", sa.Text()),
        sa.Column("added_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("memo", sa.Text()),
        sa.Column("budget", sa.Numeric(12, 2)),
        sa.Column("actual_spent", sa.Numeric(12, 2)),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="KRW"),
        sa.Column("user_url", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("version >= 1", name="ck_trip_pois_version"),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
            name="fk_trip_pois_trip_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id", "day_index"],
            ["trip_days.trip_id", "trip_days.day_index"],
            name="fk_trip_pois_trip_day",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["feature_id"],
            ["features.feature_id"],
            name="fk_trip_pois_feature_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["added_by_user_id"],
            ["users.id"],
            name="fk_trip_pois_added_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trip_pois"),
    )
    op.create_index(
        "ix_trip_pois_trip_day_sort",
        "trip_pois",
        ["trip_id", "day_index", "sort_order"],
    )
    op.create_index("ix_trip_pois_feature", "trip_pois", ["feature_id"])
    op.create_index("ix_trip_pois_added_by", "trip_pois", ["added_by_user_id"])

    op.create_table(
        "trip_share_tokens",
        sa.Column("token", sa.String(length=43), nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission", sa.String(length=20), nullable=False, server_default="view"),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("permission IN ('view')", name="ck_trip_share_tokens_permission"),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
            name="fk_trip_share_tokens_trip_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_trip_share_tokens_created_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("token", name="pk_trip_share_tokens"),
    )
    op.create_index(
        "ix_trip_share_tokens_active_trip",
        "trip_share_tokens",
        ["trip_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index("ix_trip_share_tokens_created_by", "trip_share_tokens", ["created_by"])


def _drop_trip_collaboration_tables() -> None:
    op.drop_index("ix_trip_share_tokens_created_by", table_name="trip_share_tokens")
    op.drop_index("ix_trip_share_tokens_active_trip", table_name="trip_share_tokens")
    op.drop_table("trip_share_tokens")
    op.drop_index("ix_trip_pois_added_by", table_name="trip_pois")
    op.drop_index("ix_trip_pois_feature", table_name="trip_pois")
    op.drop_index("ix_trip_pois_trip_day_sort", table_name="trip_pois")
    op.drop_table("trip_pois")
    op.drop_index("uq_trip_members_trip_email", table_name="trip_members")
    op.drop_index("uq_trip_members_trip_user", table_name="trip_members")
    op.drop_index("ix_trip_members_user", table_name="trip_members")
    op.drop_index("ix_trip_members_trip_user", table_name="trip_members")
    op.drop_table("trip_members")


def _create_admin_tables() -> None:
    op.create_table(
        "api_call_log",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("status", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("error", sa.Text()),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_api_call_log"),
    )
    op.create_index(
        "ix_api_call_log_occurred_brin",
        "api_call_log",
        ["occurred_at"],
        postgresql_using="brin",
    )
    op.create_index("ix_api_call_log_provider_time", "api_call_log", ["provider", "occurred_at"])

    op.create_table(
        "email_queue",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("to_email", postgresql.CITEXT(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "template IN ('verify', 'reset', 'invite', 'system')",
            name="ck_email_queue_template",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'sending', 'sent', 'failed')",
            name="ck_email_queue_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_email_queue_attempts"),
        sa.PrimaryKeyConstraint("id", name="pk_email_queue"),
    )
    op.create_index("ix_email_queue_status_queued", "email_queue", ["status", "queued_at"])

    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("admin_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text()),
        sa.Column("target_id", sa.Text()),
        sa.Column("diff", postgresql.JSONB()),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["admin_user_id"],
            ["users.id"],
            name="fk_admin_audit_log_admin_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_admin_audit_log"),
    )
    op.create_index(
        "ix_admin_audit_log_admin_time",
        "admin_audit_log",
        ["admin_user_id", "occurred_at"],
    )
    op.create_index("ix_admin_audit_log_target", "admin_audit_log", ["target_type", "target_id"])


def _drop_admin_tables() -> None:
    op.drop_index("ix_admin_audit_log_target", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_admin_time", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
    op.drop_index("ix_email_queue_status_queued", table_name="email_queue")
    op.drop_table("email_queue")
    op.drop_index("ix_api_call_log_provider_time", table_name="api_call_log")
    op.drop_index("ix_api_call_log_occurred_brin", table_name="api_call_log")
    op.drop_table("api_call_log")
