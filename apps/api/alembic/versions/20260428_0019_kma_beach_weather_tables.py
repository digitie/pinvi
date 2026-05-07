"""add kma beach weather tables

Revision ID: 20260428_0019
Revises: 20260428_0018
Create Date: 2026-04-28 21:10:00
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260428_0019"
down_revision: str | None = "20260428_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO place_categories (
                category_code, tier1_code, tier2_code, tier3_code, tier4_code,
                tier1_name, tier2_name, tier3_name, tier4_name,
                depth, parent_category_code, sort_order, is_active, created_at, updated_at
            )
            VALUES
                (
                    '01050000', '01', '05', '00', '00',
                    '관광', '자연명소', NULL, NULL,
                    2, '01000000', 50, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                ),
                (
                    '01050100', '01', '05', '01', '00',
                    '관광', '자연명소', '해수욕장', NULL,
                    3, '01050000', 51, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            ON CONFLICT (category_code) DO NOTHING
            """
        )
    )

    op.create_table(
        "weather_beach_location",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("beach_num", sa.String(length=8), nullable=False),
        sa.Column("beach_name", sa.String(length=200), nullable=False),
        sa.Column("place_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nx", sa.Integer(), nullable=False),
        sa.Column("ny", sa.Integer(), nullable=False),
        sa.Column("longitude", sa.Numeric(12, 8), nullable=False),
        sa.Column("latitude", sa.Numeric(12, 8), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=True),
        sa.Column("sigungu_code", sa.String(length=10), nullable=True),
        sa.Column("sido_code", sa.String(length=10), nullable=True),
        sa.Column("road_name_code", sa.String(length=12), nullable=True),
        sa.Column("road_address_management_no", sa.String(length=64), nullable=True),
        sa.Column("address_mapping_method", sa.String(length=40), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("source_file_hash", sa.String(length=64), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["legal_dong_code"],
            ["address_code_standard.legal_dong_code"],
            name="fk_wbl_legal_dong_code",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["place_id"],
            ["places.id"],
            name="fk_wbl_place_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_weather_beach_location"),
        sa.UniqueConstraint("provider", "beach_num", name="uq_wbl_provider_beach_num"),
    )
    op.create_index("ix_wbl_place_id", "weather_beach_location", ["place_id"])
    op.create_index("ix_wbl_legal_dong", "weather_beach_location", ["legal_dong_code"])
    op.create_index("ix_wbl_sigungu", "weather_beach_location", ["sigungu_code"])
    op.create_index("ix_wbl_geom", "weather_beach_location", ["geom"], postgresql_using="gist")

    op.create_table(
        "weather_raw_beach",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("beach_num", sa.String(length=8), nullable=False),
        sa.Column("request_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_weather_raw_beach"),
        sa.UniqueConstraint(
            "provider",
            "endpoint",
            "beach_num",
            "response_hash",
            name="uq_wrb_provider_endpoint_beach_hash",
        ),
    )
    op.create_index(
        "ix_wrb_endpoint_beach_collected",
        "weather_raw_beach",
        ["endpoint", "beach_num", "collected_at"],
    )
    op.create_index("ix_wrb_response_hash", "weather_raw_beach", ["response_hash"])

    op.create_table(
        "weather_serving_beach",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("beach_location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("place_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("beach_num", sa.String(length=8), nullable=False),
        sa.Column("source_record_key", sa.String(length=180), nullable=False),
        sa.Column("base_date", sa.String(length=8), nullable=True),
        sa.Column("base_time", sa.String(length=4), nullable=True),
        sa.Column("forecast_date", sa.String(length=8), nullable=True),
        sa.Column("forecast_time", sa.String(length=4), nullable=True),
        sa.Column("source_observed_time", sa.String(length=20), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("forecast_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("category_code", sa.String(length=24), nullable=False),
        sa.Column("category_name", sa.String(length=80), nullable=False),
        sa.Column("normalized_category", sa.String(length=40), nullable=False),
        sa.Column("value", sa.String(length=80), nullable=False),
        sa.Column("unit", sa.String(length=24), nullable=True),
        sa.Column("station_name", sa.String(length=120), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["beach_location_id"],
            ["weather_beach_location.id"],
            name="fk_wsb_beach_location_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["place_id"],
            ["places.id"],
            name="fk_wsb_place_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_weather_serving_beach"),
        sa.UniqueConstraint(
            "provider",
            "endpoint",
            "beach_num",
            "source_record_key",
            "category_code",
            name="uq_wsb_provider_endpoint_key_category",
        ),
    )
    op.create_index(
        "ix_wsb_beach_location_id",
        "weather_serving_beach",
        ["beach_location_id"],
    )
    op.create_index("ix_wsb_place_id", "weather_serving_beach", ["place_id"])
    op.create_index(
        "ix_wsb_beach_category",
        "weather_serving_beach",
        ["beach_num", "category_code"],
    )
    op.create_index("ix_wsb_forecast_at", "weather_serving_beach", ["forecast_at"])
    op.create_index("ix_wsb_observed_at", "weather_serving_beach", ["observed_at"])


def downgrade() -> None:
    op.drop_index("ix_wsb_observed_at", table_name="weather_serving_beach")
    op.drop_index("ix_wsb_forecast_at", table_name="weather_serving_beach")
    op.drop_index("ix_wsb_beach_category", table_name="weather_serving_beach")
    op.drop_index("ix_wsb_place_id", table_name="weather_serving_beach")
    op.drop_index("ix_wsb_beach_location_id", table_name="weather_serving_beach")
    op.drop_table("weather_serving_beach")

    op.drop_index("ix_wrb_response_hash", table_name="weather_raw_beach")
    op.drop_index("ix_wrb_endpoint_beach_collected", table_name="weather_raw_beach")
    op.drop_table("weather_raw_beach")

    op.drop_index("ix_wbl_geom", table_name="weather_beach_location")
    op.drop_index("ix_wbl_sigungu", table_name="weather_beach_location")
    op.drop_index("ix_wbl_legal_dong", table_name="weather_beach_location")
    op.drop_index("ix_wbl_place_id", table_name="weather_beach_location")
    op.drop_table("weather_beach_location")
