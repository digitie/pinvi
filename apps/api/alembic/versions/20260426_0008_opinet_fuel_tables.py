"""add opinet fuel tables

Revision ID: 20260426_0008
Revises: 20260426_0007
Create Date: 2026-04-26 19:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260426_0008"
down_revision: str | None = "20260426_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fuel_raw_opinet_region_code",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(length=64), nullable=False),
        sa.Column("request_area_code", sa.String(length=8), nullable=True),
        sa.Column("provider_region_code", sa.String(length=8), nullable=False),
        sa.Column("provider_region_name", sa.String(length=80), nullable=False),
        sa.Column("region_level", sa.String(length=32), nullable=False),
        sa.Column("parent_provider_region_code", sa.String(length=8), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_fuel_raw_opinet_region_code"),
    )
    op.create_index(
        "ix_frorc_region_code",
        "fuel_raw_opinet_region_code",
        ["provider_region_code"],
    )
    op.create_index(
        "ix_frorc_response_hash",
        "fuel_raw_opinet_region_code",
        ["response_hash"],
    )

    op.create_table(
        "fuel_serving_opinet_region_code",
        sa.Column("provider_region_code", sa.String(length=8), nullable=False),
        sa.Column("provider_region_name", sa.String(length=80), nullable=False),
        sa.Column("region_level", sa.String(length=32), nullable=False),
        sa.Column("parent_provider_region_code", sa.String(length=8), nullable=True),
        sa.Column("address_code_standard_code", sa.String(length=10), nullable=True),
        sa.Column("mapping_status", sa.String(length=32), nullable=False),
        sa.Column("mapping_source", sa.String(length=40), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["address_code_standard_code"],
            ["address_code_standard.legal_dong_code"],
            name="fk_fsorc_address_code_standard",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("provider_region_code", name="pk_fuel_serving_opinet_region_code"),
    )
    op.create_index(
        "ix_fsorc_address_code",
        "fuel_serving_opinet_region_code",
        ["address_code_standard_code"],
    )
    op.create_index(
        "ix_fsorc_parent",
        "fuel_serving_opinet_region_code",
        ["parent_provider_region_code"],
    )

    op.create_table(
        "fuel_region_legal_dong_mapping",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_region_code", sa.String(length=8), nullable=False),
        sa.Column("provider_region_name", sa.String(length=80), nullable=False),
        sa.Column("region_level", sa.String(length=32), nullable=False),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=True),
        sa.Column("mapping_source", sa.String(length=40), nullable=False),
        sa.Column("mapping_status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["legal_dong_code"],
            ["address_code_standard.legal_dong_code"],
            name="fk_frlm_legal_dong_code",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["provider_region_code"],
            ["fuel_serving_opinet_region_code.provider_region_code"],
            name="fk_frlm_provider_region_code",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fuel_region_legal_dong_mapping"),
        sa.UniqueConstraint("provider_region_code", name="uq_frlm_provider_region_code"),
    )
    op.create_index(
        "ix_frlm_legal_dong_code",
        "fuel_region_legal_dong_mapping",
        ["legal_dong_code"],
    )

    op.create_table(
        "fuel_raw_avg_price",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(length=64), nullable=False),
        sa.Column("provider_region_code", sa.String(length=8), nullable=True),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=True),
        sa.Column("trade_date", sa.String(length=8), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_fuel_code", sa.String(length=8), nullable=False),
        sa.Column("provider_fuel_name", sa.String(length=80), nullable=False),
        sa.Column("fuel_type", sa.String(length=32), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("diff", sa.Numeric(10, 2), nullable=True),
        sa.Column("price_unit", sa.String(length=24), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_fuel_raw_avg_price"),
    )
    op.create_index("ix_frap_response_hash", "fuel_raw_avg_price", ["response_hash"])
    op.create_index(
        "ix_frap_trade_fuel",
        "fuel_raw_avg_price",
        ["trade_date", "provider_fuel_code"],
    )

    op.create_table(
        "fuel_serving_avg_price",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("region_key", sa.String(length=32), nullable=False),
        sa.Column("provider_region_code", sa.String(length=8), nullable=True),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=True),
        sa.Column("trade_date", sa.String(length=8), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fuel_type", sa.String(length=32), nullable=False),
        sa.Column("provider_fuel_code", sa.String(length=8), nullable=False),
        sa.Column("provider_fuel_name", sa.String(length=80), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("diff", sa.Numeric(10, 2), nullable=True),
        sa.Column("price_unit", sa.String(length=24), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["legal_dong_code"],
            ["address_code_standard.legal_dong_code"],
            name="fk_fsap_legal_dong_code",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fuel_serving_avg_price"),
        sa.UniqueConstraint(
            "region_key",
            "trade_date",
            "fuel_type",
            name="uq_fsap_region_trade_fuel",
        ),
    )
    op.create_index(
        "ix_fsap_legal_fuel_ts",
        "fuel_serving_avg_price",
        ["legal_dong_code", "fuel_type", "timestamp"],
    )

    op.create_table(
        "fuel_raw_lowest_station",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(length=64), nullable=False),
        sa.Column("provider_region_code", sa.String(length=8), nullable=False),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_fuel_code", sa.String(length=8), nullable=False),
        sa.Column("provider_fuel_name", sa.String(length=80), nullable=False),
        sa.Column("fuel_type", sa.String(length=32), nullable=False),
        sa.Column("station_id", sa.String(length=40), nullable=False),
        sa.Column("station_name", sa.String(length=120), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("poll_div_code", sa.String(length=16), nullable=True),
        sa.Column("van_address", sa.String(length=255), nullable=True),
        sa.Column("road_address", sa.String(length=255), nullable=True),
        sa.Column("gis_x", sa.Numeric(14, 6), nullable=True),
        sa.Column("gis_y", sa.Numeric(14, 6), nullable=True),
        sa.Column("price_unit", sa.String(length=24), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_fuel_raw_lowest_station"),
    )
    op.create_index("ix_frls_response_hash", "fuel_raw_lowest_station", ["response_hash"])
    op.create_index(
        "ix_frls_region_fuel",
        "fuel_raw_lowest_station",
        ["provider_region_code", "provider_fuel_code"],
    )
    op.create_index("ix_frls_station", "fuel_raw_lowest_station", ["station_id"])

    op.create_table(
        "fuel_serving_lowest_station",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_region_code", sa.String(length=8), nullable=False),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fuel_type", sa.String(length=32), nullable=False),
        sa.Column("provider_fuel_code", sa.String(length=8), nullable=False),
        sa.Column("provider_fuel_name", sa.String(length=80), nullable=False),
        sa.Column("station_id", sa.String(length=40), nullable=False),
        sa.Column("station_name", sa.String(length=120), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("poll_div_code", sa.String(length=16), nullable=True),
        sa.Column("van_address", sa.String(length=255), nullable=True),
        sa.Column("road_address", sa.String(length=255), nullable=True),
        sa.Column("gis_x", sa.Numeric(14, 6), nullable=True),
        sa.Column("gis_y", sa.Numeric(14, 6), nullable=True),
        sa.Column("price_unit", sa.String(length=24), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["legal_dong_code"],
            ["address_code_standard.legal_dong_code"],
            name="fk_fsls_legal_dong_code",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fuel_serving_lowest_station"),
        sa.UniqueConstraint(
            "provider_region_code",
            "fuel_type",
            "station_id",
            "timestamp",
            name="uq_fsls_region_fuel_station_timestamp",
        ),
    )
    op.create_index(
        "ix_fsls_legal_fuel_price",
        "fuel_serving_lowest_station",
        ["legal_dong_code", "fuel_type", "price"],
    )


def downgrade() -> None:
    op.drop_index("ix_fsls_legal_fuel_price", table_name="fuel_serving_lowest_station")
    op.drop_table("fuel_serving_lowest_station")

    op.drop_index("ix_frls_station", table_name="fuel_raw_lowest_station")
    op.drop_index("ix_frls_region_fuel", table_name="fuel_raw_lowest_station")
    op.drop_index("ix_frls_response_hash", table_name="fuel_raw_lowest_station")
    op.drop_table("fuel_raw_lowest_station")

    op.drop_index("ix_fsap_legal_fuel_ts", table_name="fuel_serving_avg_price")
    op.drop_table("fuel_serving_avg_price")

    op.drop_index("ix_frap_trade_fuel", table_name="fuel_raw_avg_price")
    op.drop_index("ix_frap_response_hash", table_name="fuel_raw_avg_price")
    op.drop_table("fuel_raw_avg_price")

    op.drop_index("ix_frlm_legal_dong_code", table_name="fuel_region_legal_dong_mapping")
    op.drop_table("fuel_region_legal_dong_mapping")

    op.drop_index("ix_fsorc_parent", table_name="fuel_serving_opinet_region_code")
    op.drop_index("ix_fsorc_address_code", table_name="fuel_serving_opinet_region_code")
    op.drop_table("fuel_serving_opinet_region_code")

    op.drop_index("ix_frorc_response_hash", table_name="fuel_raw_opinet_region_code")
    op.drop_index("ix_frorc_region_code", table_name="fuel_raw_opinet_region_code")
    op.drop_table("fuel_raw_opinet_region_code")
