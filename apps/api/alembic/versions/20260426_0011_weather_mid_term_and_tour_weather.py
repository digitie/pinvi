"""add mid term weather and tour course weather cache

Revision ID: 20260426_0011
Revises: 20260426_0010
Create Date: 2026-04-26 23:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260426_0011"
down_revision: str | None = "20260426_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "air_quality_serving_sido_measurement",
        sa.Column("no2_grade", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "air_quality_serving_sido_measurement",
        sa.Column("o3_grade", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "air_quality_serving_sido_measurement",
        sa.Column("co_grade", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "air_quality_serving_sido_measurement",
        sa.Column("so2_grade", sa.String(length=20), nullable=True),
    )
    for column_name in (
        "pm10_flag",
        "pm25_flag",
        "no2_flag",
        "o3_flag",
        "co_flag",
        "so2_flag",
    ):
        op.add_column(
            "air_quality_serving_sido_measurement",
            sa.Column(column_name, sa.String(length=20), nullable=True),
        )

    op.create_table(
        "weather_mid_forecast_region",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("region_kind", sa.String(length=32), nullable=False),
        sa.Column("provider_region_id", sa.String(length=20), nullable=False),
        sa.Column("region_name", sa.String(length=120), nullable=False),
        sa.Column("parent_region_id", sa.String(length=20), nullable=True),
        sa.Column("source_version", sa.String(length=80), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_weather_mid_forecast_region"),
        sa.UniqueConstraint(
            "provider",
            "endpoint",
            "region_kind",
            "provider_region_id",
            name="uq_wmfr_provider_endpoint_kind_region",
        ),
    )
    op.create_index(
        "ix_wmfr_kind_region",
        "weather_mid_forecast_region",
        ["region_kind", "provider_region_id"],
    )

    op.create_table(
        "weather_mid_region_address_mapping",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("provider_region_kind", sa.String(length=32), nullable=False),
        sa.Column("provider_region_id", sa.String(length=20), nullable=False),
        sa.Column("sido_code", sa.String(length=10), nullable=True),
        sa.Column("sigungu_code", sa.String(length=10), nullable=True),
        sa.Column("legal_dong_code_prefix", sa.String(length=10), nullable=True),
        sa.Column("mapping_method", sa.String(length=40), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.String(length=8), nullable=True),
        sa.Column("source_version", sa.String(length=80), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["provider", "endpoint", "provider_region_kind", "provider_region_id"],
            [
                "weather_mid_forecast_region.provider",
                "weather_mid_forecast_region.endpoint",
                "weather_mid_forecast_region.region_kind",
                "weather_mid_forecast_region.provider_region_id",
            ],
            name="fk_wmram_forecast_region",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_weather_mid_region_address_mapping"),
        sa.UniqueConstraint(
            "provider",
            "endpoint",
            "provider_region_kind",
            "provider_region_id",
            "sido_code",
            "sigungu_code",
            "legal_dong_code_prefix",
            name="uq_wmram_provider_region_address_scope",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_wmram_sido_sigungu",
        "weather_mid_region_address_mapping",
        ["sido_code", "sigungu_code"],
    )
    op.create_index(
        "ix_wmram_region",
        "weather_mid_region_address_mapping",
        ["provider_region_kind", "provider_region_id"],
    )

    op.create_table(
        "weather_raw_mid_term",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("region_kind", sa.String(length=32), nullable=False),
        sa.Column("provider_region_id", sa.String(length=20), nullable=False),
        sa.Column("tm_fc", sa.String(length=20), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_weather_raw_mid_term"),
    )
    op.create_index(
        "ix_wrmt_endpoint_region_tm",
        "weather_raw_mid_term",
        ["endpoint", "provider_region_id", "tm_fc"],
    )
    op.create_index("ix_wrmt_response_hash", "weather_raw_mid_term", ["response_hash"])

    op.create_table(
        "weather_serving_mid_term",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("region_kind", sa.String(length=32), nullable=False),
        sa.Column("provider_region_id", sa.String(length=20), nullable=False),
        sa.Column("source_region_code", sa.String(length=20), nullable=False),
        sa.Column("tm_fc", sa.String(length=20), nullable=False),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("forecast_slot", sa.String(length=16), nullable=False),
        sa.Column("weather_summary", sa.String(length=255), nullable=True),
        sa.Column("rain_probability", sa.String(length=20), nullable=True),
        sa.Column("min_temperature", sa.String(length=20), nullable=True),
        sa.Column("max_temperature", sa.String(length=20), nullable=True),
        sa.Column("mapping_method", sa.String(length=40), nullable=True),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("fallback_reason", sa.String(length=255), nullable=True),
        sa.Column("display_priority", sa.Integer(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_weather_serving_mid_term"),
        sa.UniqueConstraint(
            "endpoint",
            "region_kind",
            "provider_region_id",
            "tm_fc",
            "forecast_date",
            "forecast_slot",
            name="uq_wsmt_endpoint_region_forecast_slot",
        ),
    )
    op.create_index(
        "ix_wsmt_region_date",
        "weather_serving_mid_term",
        ["provider_region_id", "forecast_date"],
    )
    op.create_index(
        "ix_wsmt_date_slot",
        "weather_serving_mid_term",
        ["forecast_date", "forecast_slot"],
    )

    op.create_table(
        "tour_course_raw_kma_spot_weather",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("course_id", sa.String(length=40), nullable=False),
        sa.Column("spot_id", sa.String(length=40), nullable=True),
        sa.Column("base_date", sa.String(length=8), nullable=True),
        sa.Column("base_time", sa.String(length=4), nullable=True),
        sa.Column("forecast_date", sa.String(length=8), nullable=True),
        sa.Column("forecast_time", sa.String(length=4), nullable=True),
        sa.Column("category_code", sa.String(length=16), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_tour_course_raw_kma_spot_weather"),
    )
    op.create_index(
        "ix_tcrksw_course_spot_time",
        "tour_course_raw_kma_spot_weather",
        ["course_id", "spot_id", "base_date", "base_time"],
    )
    op.create_index(
        "ix_tcrksw_response_hash",
        "tour_course_raw_kma_spot_weather",
        ["response_hash"],
    )

    op.create_table(
        "tour_course_serving_kma_spot_weather",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("source_file_hash", sa.String(length=64), nullable=True),
        sa.Column("theme_category_code", sa.String(length=32), nullable=True),
        sa.Column("course_id", sa.String(length=40), nullable=False),
        sa.Column("spot_id", sa.String(length=40), nullable=True),
        sa.Column("spot_name", sa.String(length=255), nullable=True),
        sa.Column("longitude", sa.Numeric(12, 8), nullable=True),
        sa.Column("latitude", sa.Numeric(12, 8), nullable=True),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=True),
        sa.Column("sigungu_code", sa.String(length=10), nullable=True),
        sa.Column("sido_code", sa.String(length=10), nullable=True),
        sa.Column("base_date", sa.String(length=8), nullable=True),
        sa.Column("base_time", sa.String(length=4), nullable=True),
        sa.Column("forecast_date", sa.String(length=8), nullable=True),
        sa.Column("forecast_time", sa.String(length=4), nullable=True),
        sa.Column("category_code", sa.String(length=16), nullable=False),
        sa.Column("category_name", sa.String(length=80), nullable=False),
        sa.Column("normalized_category", sa.String(length=40), nullable=False),
        sa.Column("value", sa.String(length=80), nullable=False),
        sa.Column("unit", sa.String(length=24), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_tour_course_serving_kma_spot_weather"),
        sa.UniqueConstraint(
            "course_id",
            "spot_id",
            "base_date",
            "base_time",
            "forecast_date",
            "forecast_time",
            "category_code",
            name="uq_tcskw_course_spot_time_category",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_tcskw_course_spot",
        "tour_course_serving_kma_spot_weather",
        ["course_id", "spot_id"],
    )
    op.create_index(
        "ix_tcskw_legal_dong",
        "tour_course_serving_kma_spot_weather",
        ["legal_dong_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_tcskw_legal_dong", table_name="tour_course_serving_kma_spot_weather")
    op.drop_index("ix_tcskw_course_spot", table_name="tour_course_serving_kma_spot_weather")
    op.drop_table("tour_course_serving_kma_spot_weather")
    op.drop_index("ix_tcrksw_response_hash", table_name="tour_course_raw_kma_spot_weather")
    op.drop_index("ix_tcrksw_course_spot_time", table_name="tour_course_raw_kma_spot_weather")
    op.drop_table("tour_course_raw_kma_spot_weather")

    op.drop_index("ix_wsmt_date_slot", table_name="weather_serving_mid_term")
    op.drop_index("ix_wsmt_region_date", table_name="weather_serving_mid_term")
    op.drop_table("weather_serving_mid_term")
    op.drop_index("ix_wrmt_response_hash", table_name="weather_raw_mid_term")
    op.drop_index("ix_wrmt_endpoint_region_tm", table_name="weather_raw_mid_term")
    op.drop_table("weather_raw_mid_term")
    op.drop_index("ix_wmram_region", table_name="weather_mid_region_address_mapping")
    op.drop_index("ix_wmram_sido_sigungu", table_name="weather_mid_region_address_mapping")
    op.drop_table("weather_mid_region_address_mapping")
    op.drop_index("ix_wmfr_kind_region", table_name="weather_mid_forecast_region")
    op.drop_table("weather_mid_forecast_region")

    for column_name in (
        "so2_flag",
        "co_flag",
        "o3_flag",
        "no2_flag",
        "pm25_flag",
        "pm10_flag",
        "so2_grade",
        "co_grade",
        "o3_grade",
        "no2_grade",
    ):
        op.drop_column("air_quality_serving_sido_measurement", column_name)
