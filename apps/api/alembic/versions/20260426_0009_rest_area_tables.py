"""add rest area etl tables

Revision ID: 20260426_0009
Revises: 20260426_0008
Create Date: 2026-04-26 20:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260426_0009"
down_revision: str | None = "20260426_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rest_area_raw_master",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("endpoint", sa.String(length=120), nullable=False),
        sa.Column("source_api_id", sa.String(length=16), nullable=False),
        sa.Column("source_key", sa.String(length=80), nullable=False),
        sa.Column("source_snapshot_date", sa.Date(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rest_area_raw_master"),
    )
    op.create_index("ix_rarm_response_hash", "rest_area_raw_master", ["response_hash"])
    op.create_index("ix_rarm_source_key", "rest_area_raw_master", ["source_key"])

    op.create_table(
        "rest_area_serving_master",
        sa.Column("svar_cd", sa.String(length=16), nullable=False),
        sa.Column("provider_service_area_code", sa.String(length=24), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("direction", sa.String(length=80), nullable=True),
        sa.Column("route_code", sa.String(length=16), nullable=True),
        sa.Column("route_name", sa.String(length=120), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("convenience_raw", sa.String(length=500), nullable=True),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.Column("maintenance_yn", sa.String(length=8), nullable=True),
        sa.Column("truck_sa_yn", sa.String(length=8), nullable=True),
        sa.Column("representative_food", sa.String(length=255), nullable=True),
        sa.Column("lon", sa.Numeric(12, 8), nullable=True),
        sa.Column("lat", sa.Numeric(12, 8), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_snapshot_date", sa.Date(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("svar_cd", name="pk_rest_area_serving_master"),
    )
    op.create_index("ix_rasm_name", "rest_area_serving_master", ["name"])
    op.create_index(
        "ix_rasm_route",
        "rest_area_serving_master",
        ["route_code", "direction"],
    )

    op.create_table(
        "rest_area_raw_oil_price",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("endpoint", sa.String(length=120), nullable=False),
        sa.Column("source_api_id", sa.String(length=16), nullable=False),
        sa.Column("source_key", sa.String(length=80), nullable=False),
        sa.Column("service_area_code2", sa.String(length=16), nullable=True),
        sa.Column("source_snapshot_date", sa.Date(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rest_area_raw_oil_price"),
    )
    op.create_index("ix_rarop_response_hash", "rest_area_raw_oil_price", ["response_hash"])
    op.create_index("ix_rarop_source_key", "rest_area_raw_oil_price", ["source_key"])

    op.create_table(
        "rest_area_raw_service",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("endpoint", sa.String(length=120), nullable=False),
        sa.Column("source_api_id", sa.String(length=16), nullable=False),
        sa.Column("source_key", sa.String(length=80), nullable=False),
        sa.Column("service_area_code2", sa.String(length=16), nullable=True),
        sa.Column("source_snapshot_date", sa.Date(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rest_area_raw_service"),
    )
    op.create_index("ix_rars_response_hash", "rest_area_raw_service", ["response_hash"])
    op.create_index("ix_rars_source_key", "rest_area_raw_service", ["source_key"])

    op.create_table(
        "rest_area_serving_oil_price",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("svar_cd", sa.String(length=16), nullable=False),
        sa.Column("provider_service_area_code", sa.String(length=24), nullable=True),
        sa.Column("station_name", sa.String(length=160), nullable=True),
        sa.Column("route_code", sa.String(length=16), nullable=True),
        sa.Column("route_name", sa.String(length=120), nullable=True),
        sa.Column("direction", sa.String(length=80), nullable=True),
        sa.Column("oil_company", sa.String(length=80), nullable=True),
        sa.Column("lpg_yn", sa.String(length=8), nullable=True),
        sa.Column("provider_fuel_code", sa.String(length=40), nullable=False),
        sa.Column("provider_fuel_name", sa.String(length=80), nullable=False),
        sa.Column("fuel_type", sa.String(length=32), nullable=False),
        sa.Column("price_per_liter_krw", sa.Integer(), nullable=False),
        sa.Column("price_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price_time_source", sa.String(length=40), nullable=False),
        sa.Column("price_unit", sa.String(length=24), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_snapshot_date", sa.Date(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["svar_cd"],
            ["rest_area_serving_master.svar_cd"],
            name="fk_rasop_svar_cd",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rest_area_serving_oil_price"),
        sa.UniqueConstraint(
            "svar_cd",
            "provider_fuel_code",
            "collected_at",
            name="uq_rasop_svar_fuel_collected_at",
        ),
    )
    op.create_index(
        "ix_rasop_fuel_price",
        "rest_area_serving_oil_price",
        ["fuel_type", "price_per_liter_krw"],
    )

    op.create_table(
        "rest_area_serving_service",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("svar_cd", sa.String(length=16), nullable=False),
        sa.Column("provider_service_area_code", sa.String(length=24), nullable=True),
        sa.Column("route_code", sa.String(length=16), nullable=True),
        sa.Column("route_name", sa.String(length=120), nullable=True),
        sa.Column("direction", sa.String(length=80), nullable=True),
        sa.Column("provider_service_code", sa.String(length=120), nullable=False),
        sa.Column("provider_service_name", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_snapshot_date", sa.Date(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["svar_cd"],
            ["rest_area_serving_master.svar_cd"],
            name="fk_rass_svar_cd",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rest_area_serving_service"),
        sa.UniqueConstraint(
            "svar_cd",
            "provider_service_code",
            "source_snapshot_date",
            name="uq_rass_svar_service_snapshot",
        ),
    )
    op.create_index(
        "ix_rass_service_name",
        "rest_area_serving_service",
        ["provider_service_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_rass_service_name", table_name="rest_area_serving_service")
    op.drop_table("rest_area_serving_service")

    op.drop_index("ix_rasop_fuel_price", table_name="rest_area_serving_oil_price")
    op.drop_table("rest_area_serving_oil_price")

    op.drop_index("ix_rars_source_key", table_name="rest_area_raw_service")
    op.drop_index("ix_rars_response_hash", table_name="rest_area_raw_service")
    op.drop_table("rest_area_raw_service")

    op.drop_index("ix_rarop_source_key", table_name="rest_area_raw_oil_price")
    op.drop_index("ix_rarop_response_hash", table_name="rest_area_raw_oil_price")
    op.drop_table("rest_area_raw_oil_price")

    op.drop_index("ix_rasm_route", table_name="rest_area_serving_master")
    op.drop_index("ix_rasm_name", table_name="rest_area_serving_master")
    op.drop_table("rest_area_serving_master")

    op.drop_index("ix_rarm_source_key", table_name="rest_area_raw_master")
    op.drop_index("ix_rarm_response_hash", table_name="rest_area_raw_master")
    op.drop_table("rest_area_raw_master")
