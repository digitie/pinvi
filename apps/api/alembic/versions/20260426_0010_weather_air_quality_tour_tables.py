"""add weather air quality and kma tour course tables

Revision ID: 20260426_0010
Revises: 20260426_0009
Create Date: 2026-04-26 21:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260426_0010"
down_revision: str | None = "20260426_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "weather_short_term_grid_mapping",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("region_code_type", sa.String(length=32), nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=False),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=True),
        sa.Column("sigungu_code", sa.String(length=10), nullable=True),
        sa.Column("sido_code", sa.String(length=10), nullable=True),
        sa.Column("representative_lon", sa.Numeric(12, 8), nullable=False),
        sa.Column("representative_lat", sa.Numeric(12, 8), nullable=False),
        sa.Column("nx", sa.Integer(), nullable=False),
        sa.Column("ny", sa.Integer(), nullable=False),
        sa.Column("mapping_method", sa.String(length=40), nullable=False),
        sa.Column("source_boundary_version", sa.String(length=64), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["legal_dong_code"],
            ["address_code_standard.legal_dong_code"],
            name="fk_wstgm_legal_dong_code",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_weather_short_term_grid_mapping"),
        sa.UniqueConstraint("region_code_type", "region_code", name="uq_wstgm_region"),
    )
    op.create_index("ix_wstgm_grid", "weather_short_term_grid_mapping", ["nx", "ny"])
    op.create_index(
        "ix_wstgm_legal_dong",
        "weather_short_term_grid_mapping",
        ["legal_dong_code"],
    )
    op.create_index("ix_wstgm_sigungu", "weather_short_term_grid_mapping", ["sigungu_code"])

    op.create_table(
        "weather_raw_short_term",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("nx", sa.Integer(), nullable=False),
        sa.Column("ny", sa.Integer(), nullable=False),
        sa.Column("base_date", sa.String(length=8), nullable=False),
        sa.Column("base_time", sa.String(length=4), nullable=False),
        sa.Column("forecast_date", sa.String(length=8), nullable=True),
        sa.Column("forecast_time", sa.String(length=4), nullable=True),
        sa.Column("category_code", sa.String(length=16), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_weather_raw_short_term"),
    )
    op.create_index(
        "ix_wrst_grid_base",
        "weather_raw_short_term",
        ["nx", "ny", "base_date", "base_time"],
    )
    op.create_index("ix_wrst_response_hash", "weather_raw_short_term", ["response_hash"])

    op.create_table(
        "weather_serving_short_term",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("nx", sa.Integer(), nullable=False),
        sa.Column("ny", sa.Integer(), nullable=False),
        sa.Column("base_date", sa.String(length=8), nullable=False),
        sa.Column("base_time", sa.String(length=4), nullable=False),
        sa.Column("forecast_date", sa.String(length=8), nullable=True),
        sa.Column("forecast_time", sa.String(length=4), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("forecast_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("category_code", sa.String(length=16), nullable=False),
        sa.Column("category_name", sa.String(length=80), nullable=False),
        sa.Column("normalized_category", sa.String(length=40), nullable=False),
        sa.Column("value", sa.String(length=80), nullable=False),
        sa.Column("unit", sa.String(length=24), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_weather_serving_short_term"),
        sa.UniqueConstraint(
            "endpoint",
            "nx",
            "ny",
            "base_date",
            "base_time",
            "forecast_date",
            "forecast_time",
            "category_code",
            name="uq_wsst_endpoint_grid_time_category",
        ),
    )
    op.create_index(
        "ix_wsst_grid_category",
        "weather_serving_short_term",
        ["nx", "ny", "category_code"],
    )

    op.create_table(
        "weather_kma_alert_station_code",
        sa.Column("stn_id", sa.String(length=12), nullable=False),
        sa.Column("station_name", sa.String(length=120), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("stn_id", name="pk_weather_kma_alert_station_code"),
    )
    op.create_table(
        "weather_raw_kma_alert",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column("stn_id", sa.String(length=12), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("tm_fc", sa.String(length=20), nullable=True),
        sa.Column("tm_seq", sa.String(length=20), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_weather_raw_kma_alert"),
    )
    op.create_index(
        "ix_wrka_type_stn_tm",
        "weather_raw_kma_alert",
        ["alert_type", "stn_id", "tm_fc"],
    )
    op.create_index("ix_wrka_response_hash", "weather_raw_kma_alert", ["response_hash"])
    op.create_table(
        "weather_serving_kma_alert",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column("stn_id", sa.String(length=12), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("tm_fc", sa.String(length=20), nullable=True),
        sa.Column("tm_seq", sa.String(length=20), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["stn_id"],
            ["weather_kma_alert_station_code.stn_id"],
            name="fk_wska_station_code",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_weather_serving_kma_alert"),
        sa.UniqueConstraint(
            "alert_type",
            "stn_id",
            "tm_fc",
            "tm_seq",
            "title",
            name="uq_wska_type_station_fc_seq_title",
        ),
    )
    op.create_index(
        "ix_wska_alert_type_tm",
        "weather_serving_kma_alert",
        ["alert_type", "tm_fc"],
    )

    op.create_table(
        "air_quality_raw_station",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("request_sido_name", sa.String(length=40), nullable=True),
        sa.Column("station_name", sa.String(length=120), nullable=False),
        sa.Column("mang_name", sa.String(length=80), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_air_quality_raw_station"),
    )
    op.create_index("ix_aqrs_station", "air_quality_raw_station", ["station_name"])
    op.create_index("ix_aqrs_response_hash", "air_quality_raw_station", ["response_hash"])
    op.create_table(
        "air_quality_serving_station",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("station_name", sa.String(length=120), nullable=False),
        sa.Column("mang_name", sa.String(length=80), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("sido_name", sa.String(length=40), nullable=True),
        sa.Column("item", sa.String(length=255), nullable=True),
        sa.Column("installation_year", sa.String(length=8), nullable=True),
        sa.Column("longitude", sa.Numeric(12, 8), nullable=True),
        sa.Column("latitude", sa.Numeric(12, 8), nullable=True),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=True),
        sa.Column("sigungu_code", sa.String(length=10), nullable=True),
        sa.Column("mapping_method", sa.String(length=40), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["legal_dong_code"],
            ["address_code_standard.legal_dong_code"],
            name="fk_aqss_legal_dong_code",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_air_quality_serving_station"),
        sa.UniqueConstraint("station_name", "mang_name", "address", name="uq_aqss_station_address"),
    )
    op.create_index("ix_aqss_legal_dong", "air_quality_serving_station", ["legal_dong_code"])
    op.create_index("ix_aqss_sigungu", "air_quality_serving_station", ["sigungu_code"])

    op.create_table(
        "air_quality_raw_forecast",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("inform_code", sa.String(length=16), nullable=True),
        sa.Column("data_time", sa.String(length=40), nullable=True),
        sa.Column("inform_data", sa.String(length=40), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_air_quality_raw_forecast"),
    )
    op.create_index(
        "ix_aqrf_code_time",
        "air_quality_raw_forecast",
        ["inform_code", "data_time"],
    )
    op.create_index("ix_aqrf_response_hash", "air_quality_raw_forecast", ["response_hash"])
    op.create_table(
        "air_quality_serving_forecast",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inform_code", sa.String(length=16), nullable=False),
        sa.Column("data_time", sa.String(length=40), nullable=False),
        sa.Column("inform_data", sa.String(length=40), nullable=True),
        sa.Column("inform_overall", sa.String(length=1000), nullable=True),
        sa.Column("inform_cause", sa.String(length=1000), nullable=True),
        sa.Column("inform_grade", sa.String(length=1000), nullable=True),
        sa.Column("action_knack", sa.String(length=1000), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_air_quality_serving_forecast"),
        sa.UniqueConstraint(
            "inform_code",
            "data_time",
            "inform_data",
            "inform_overall",
            name="uq_aqsf_code_time_data_overall",
        ),
    )
    op.create_index(
        "ix_aqsf_code_time",
        "air_quality_serving_forecast",
        ["inform_code", "data_time"],
    )

    op.create_table(
        "air_quality_raw_sido_measurement",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("sido_name", sa.String(length=40), nullable=False),
        sa.Column("station_name", sa.String(length=120), nullable=False),
        sa.Column("data_time", sa.String(length=40), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_air_quality_raw_sido_measurement"),
    )
    op.create_index(
        "ix_aqrsm_station_time",
        "air_quality_raw_sido_measurement",
        ["sido_name", "station_name", "data_time"],
    )
    op.create_index(
        "ix_aqrsm_response_hash",
        "air_quality_raw_sido_measurement",
        ["response_hash"],
    )
    op.create_table(
        "air_quality_serving_sido_measurement",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sido_name", sa.String(length=40), nullable=False),
        sa.Column("station_name", sa.String(length=120), nullable=False),
        sa.Column("mang_name", sa.String(length=80), nullable=True),
        sa.Column("data_time", sa.String(length=40), nullable=False),
        sa.Column("khai_value", sa.String(length=20), nullable=True),
        sa.Column("khai_grade", sa.String(length=20), nullable=True),
        sa.Column("pm10_value", sa.String(length=20), nullable=True),
        sa.Column("pm10_grade", sa.String(length=20), nullable=True),
        sa.Column("pm25_value", sa.String(length=20), nullable=True),
        sa.Column("pm25_grade", sa.String(length=20), nullable=True),
        sa.Column("no2_value", sa.String(length=20), nullable=True),
        sa.Column("o3_value", sa.String(length=20), nullable=True),
        sa.Column("co_value", sa.String(length=20), nullable=True),
        sa.Column("so2_value", sa.String(length=20), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_air_quality_serving_sido_measurement"),
        sa.UniqueConstraint(
            "sido_name",
            "station_name",
            "data_time",
            name="uq_aqssm_sido_station_time",
        ),
    )
    op.create_index(
        "ix_aqssm_station_time",
        "air_quality_serving_sido_measurement",
        ["station_name", "data_time"],
    )

    op.create_table(
        "tour_course_raw_kma_point",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("source_file_hash", sa.String(length=64), nullable=False),
        sa.Column("source_encoding", sa.String(length=32), nullable=False),
        sa.Column("source_snapshot_date", sa.Date(), nullable=True),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("theme_category_code", sa.String(length=32), nullable=False),
        sa.Column("course_id", sa.String(length=40), nullable=False),
        sa.Column("spot_id", sa.String(length=40), nullable=False),
        sa.Column("region_id", sa.String(length=40), nullable=True),
        sa.Column("spot_name", sa.String(length=255), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_line", sa.Text(), nullable=True),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_tour_course_raw_kma_point"),
        sa.UniqueConstraint("source_file_hash", "row_number", name="uq_tcrkp_file_row"),
    )
    op.create_index("ix_tcrkp_spot_id", "tour_course_raw_kma_point", ["spot_id"])
    op.create_table(
        "kma_recommended_tour_course",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("source_file_hash", sa.String(length=64), nullable=False),
        sa.Column("source_encoding", sa.String(length=32), nullable=False),
        sa.Column("source_snapshot_date", sa.Date(), nullable=True),
        sa.Column("theme_category_code", sa.String(length=32), nullable=False),
        sa.Column("theme_category", sa.String(length=40), nullable=False),
        sa.Column("theme_name", sa.String(length=120), nullable=True),
        sa.Column("course_id", sa.String(length=40), nullable=False),
        sa.Column("spot_id", sa.String(length=40), nullable=False),
        sa.Column("region_id", sa.String(length=40), nullable=True),
        sa.Column("spot_name", sa.String(length=255), nullable=False),
        sa.Column("longitude", sa.Numeric(12, 8), nullable=False),
        sa.Column("latitude", sa.Numeric(12, 8), nullable=False),
        sa.Column("course_order", sa.Integer(), nullable=True),
        sa.Column("travel_time_minutes", sa.Integer(), nullable=True),
        sa.Column("indoor_type", sa.String(length=40), nullable=True),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=True),
        sa.Column("sigungu_code", sa.String(length=10), nullable=True),
        sa.Column("sido_code", sa.String(length=10), nullable=True),
        sa.Column("address_snapshot", sa.String(length=500), nullable=True),
        sa.Column("address_mapping_method", sa.String(length=40), nullable=False),
        sa.Column("marker_source_type", sa.String(length=80), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["legal_dong_code"],
            ["address_code_standard.legal_dong_code"],
            name="fk_krt_legal_dong_code",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_kma_recommended_tour_course"),
        sa.UniqueConstraint("source_file_hash", "spot_id", name="uq_krt_course_file_spot"),
    )
    op.create_index(
        "ix_krt_theme_course_order",
        "kma_recommended_tour_course",
        ["theme_category_code", "course_id", "course_order"],
    )
    op.create_index("ix_krt_legal_dong", "kma_recommended_tour_course", ["legal_dong_code"])


def downgrade() -> None:
    op.drop_index("ix_krt_legal_dong", table_name="kma_recommended_tour_course")
    op.drop_index("ix_krt_theme_course_order", table_name="kma_recommended_tour_course")
    op.drop_table("kma_recommended_tour_course")
    op.drop_index("ix_tcrkp_spot_id", table_name="tour_course_raw_kma_point")
    op.drop_table("tour_course_raw_kma_point")

    op.drop_index("ix_aqssm_station_time", table_name="air_quality_serving_sido_measurement")
    op.drop_table("air_quality_serving_sido_measurement")
    op.drop_index("ix_aqrsm_response_hash", table_name="air_quality_raw_sido_measurement")
    op.drop_index("ix_aqrsm_station_time", table_name="air_quality_raw_sido_measurement")
    op.drop_table("air_quality_raw_sido_measurement")

    op.drop_index("ix_aqsf_code_time", table_name="air_quality_serving_forecast")
    op.drop_table("air_quality_serving_forecast")
    op.drop_index("ix_aqrf_response_hash", table_name="air_quality_raw_forecast")
    op.drop_index("ix_aqrf_code_time", table_name="air_quality_raw_forecast")
    op.drop_table("air_quality_raw_forecast")

    op.drop_index("ix_aqss_sigungu", table_name="air_quality_serving_station")
    op.drop_index("ix_aqss_legal_dong", table_name="air_quality_serving_station")
    op.drop_table("air_quality_serving_station")
    op.drop_index("ix_aqrs_response_hash", table_name="air_quality_raw_station")
    op.drop_index("ix_aqrs_station", table_name="air_quality_raw_station")
    op.drop_table("air_quality_raw_station")

    op.drop_index("ix_wska_alert_type_tm", table_name="weather_serving_kma_alert")
    op.drop_table("weather_serving_kma_alert")
    op.drop_index("ix_wrka_response_hash", table_name="weather_raw_kma_alert")
    op.drop_index("ix_wrka_type_stn_tm", table_name="weather_raw_kma_alert")
    op.drop_table("weather_raw_kma_alert")
    op.drop_table("weather_kma_alert_station_code")

    op.drop_index("ix_wsst_grid_category", table_name="weather_serving_short_term")
    op.drop_table("weather_serving_short_term")
    op.drop_index("ix_wrst_response_hash", table_name="weather_raw_short_term")
    op.drop_index("ix_wrst_grid_base", table_name="weather_raw_short_term")
    op.drop_table("weather_raw_short_term")
    op.drop_index("ix_wstgm_sigungu", table_name="weather_short_term_grid_mapping")
    op.drop_index("ix_wstgm_legal_dong", table_name="weather_short_term_grid_mapping")
    op.drop_index("ix_wstgm_grid", table_name="weather_short_term_grid_mapping")
    op.drop_table("weather_short_term_grid_mapping")
