"""add integrated beach source tables

Revision ID: 20260428_0020
Revises: 20260428_0019
Create Date: 2026-04-28 23:10:00
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260428_0020"
down_revision: str | None = "20260428_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "beach_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_key", sa.String(length=180), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("place_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("representative_provider", sa.String(length=40), nullable=False),
        sa.Column("representative_dataset_key", sa.String(length=120), nullable=False),
        sa.Column("longitude", sa.Numeric(12, 8), nullable=True),
        sa.Column("latitude", sa.Numeric(12, 8), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=True),
        sa.Column("sigungu_code", sa.String(length=10), nullable=True),
        sa.Column("sido_code", sa.String(length=10), nullable=True),
        sa.Column("road_name_code", sa.String(length=12), nullable=True),
        sa.Column("road_address_management_no", sa.String(length=64), nullable=True),
        sa.Column("road_address", sa.String(length=500), nullable=True),
        sa.Column("address_snapshot", sa.String(length=700), nullable=True),
        sa.Column("address_mapping_method", sa.String(length=48), nullable=False),
        sa.Column("beach_width_m", sa.Numeric(12, 2), nullable=True),
        sa.Column("beach_length_m", sa.Numeric(12, 2), nullable=True),
        sa.Column("beach_material", sa.String(length=255), nullable=True),
        sa.Column("homepage_url", sa.Text(), nullable=True),
        sa.Column("homepage_name", sa.String(length=200), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("emergency_contact", sa.String(length=120), nullable=True),
        sa.Column(
            "source_specific_attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["legal_dong_code"],
            ["address_code_standard.legal_dong_code"],
            name="fk_beach_profiles_legal_dong_code",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["place_id"],
            ["places.id"],
            name="fk_beach_profiles_place_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_beach_profiles"),
        sa.UniqueConstraint("canonical_key", name="uq_beach_profiles_canonical_key"),
    )
    op.create_index("ix_beach_profiles_place_id", "beach_profiles", ["place_id"])
    op.create_index("ix_beach_profiles_legal_dong", "beach_profiles", ["legal_dong_code"])
    op.create_index("ix_beach_profiles_sigungu", "beach_profiles", ["sigungu_code"])
    op.create_index("ix_beach_profiles_sido", "beach_profiles", ["sido_code"])
    op.create_index("ix_beach_profiles_geom", "beach_profiles", ["geom"], postgresql_using="gist")

    op.create_table(
        "beach_provider_refs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("beach_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_dataset_key", sa.String(length=120), nullable=False),
        sa.Column("provider_beach_id", sa.String(length=255), nullable=False),
        sa.Column("stable_name", sa.String(length=255), nullable=True),
        sa.Column("stable_address", sa.String(length=500), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["beach_id"],
            ["beach_profiles.id"],
            name="fk_beach_provider_refs_beach_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_beach_provider_refs"),
        sa.UniqueConstraint(
            "provider",
            "provider_dataset_key",
            "provider_beach_id",
            name="uq_beach_provider_refs_provider_dataset_id",
        ),
    )
    op.create_index("ix_beach_provider_refs_beach_id", "beach_provider_refs", ["beach_id"])
    op.create_index(
        "ix_beach_provider_refs_provider_name",
        "beach_provider_refs",
        ["provider", "stable_name"],
    )

    op.create_table(
        "beach_source_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("dataset_key", sa.String(length=120), nullable=False),
        sa.Column("endpoint", sa.String(length=180), nullable=False),
        sa.Column("source_record_id", sa.String(length=255), nullable=False),
        sa.Column("request_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_beach_source_records"),
        sa.UniqueConstraint(
            "provider",
            "dataset_key",
            "source_record_id",
            "response_hash",
            name="uq_beach_source_records_provider_dataset_record_hash",
        ),
    )
    op.create_index(
        "ix_beach_source_records_dataset_record",
        "beach_source_records",
        ["dataset_key", "source_record_id"],
    )
    op.create_index(
        "ix_beach_source_records_collected_at", "beach_source_records", ["collected_at"]
    )

    op.create_table(
        "beach_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("beach_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_dataset_key", sa.String(length=120), nullable=False),
        sa.Column("provider_beach_id", sa.String(length=255), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observation_station_name", sa.String(length=120), nullable=True),
        sa.Column("tide", sa.String(length=80), nullable=True),
        sa.Column("wave_height_m", sa.Numeric(8, 3), nullable=True),
        sa.Column("water_temperature_c", sa.Numeric(8, 3), nullable=True),
        sa.Column("wind_speed_ms", sa.Numeric(8, 3), nullable=True),
        sa.Column("wind_direction", sa.String(length=80), nullable=True),
        sa.Column("forecast_status", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quota_snapshot", sa.String(length=120), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["beach_id"],
            ["beach_profiles.id"],
            name="fk_beach_observations_beach_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["beach_source_records.id"],
            name="fk_beach_observations_source_record_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_beach_observations"),
        sa.UniqueConstraint(
            "provider",
            "provider_beach_id",
            "observed_at",
            name="uq_beach_observations_provider_beach_time",
        ),
    )
    op.create_index(
        "ix_beach_observations_beach_time",
        "beach_observations",
        ["beach_id", "observed_at"],
    )
    op.create_index(
        "ix_beach_observations_source_record_id",
        "beach_observations",
        ["source_record_id"],
    )

    op.create_table(
        "beach_index_forecasts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("beach_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_dataset_key", sa.String(length=120), nullable=False),
        sa.Column("provider_place_code", sa.String(length=80), nullable=True),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("forecast_slot", sa.String(length=24), nullable=False),
        sa.Column("index_score", sa.Numeric(8, 3), nullable=True),
        sa.Column("total_index", sa.String(length=80), nullable=True),
        sa.Column("max_wave_height_m", sa.Numeric(8, 3), nullable=True),
        sa.Column("avg_water_temperature_c", sa.Numeric(8, 3), nullable=True),
        sa.Column("avg_air_temperature_c", sa.Numeric(8, 3), nullable=True),
        sa.Column("max_wind_speed_ms", sa.Numeric(8, 3), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["beach_id"],
            ["beach_profiles.id"],
            name="fk_beach_index_forecasts_beach_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["beach_source_records.id"],
            name="fk_beach_index_forecasts_source_record_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_beach_index_forecasts"),
        sa.UniqueConstraint(
            "provider",
            "provider_dataset_key",
            "beach_id",
            "forecast_date",
            "forecast_slot",
            name="uq_beach_index_forecasts_provider_beach_date_slot",
        ),
    )
    op.create_index(
        "ix_beach_index_forecasts_beach_date",
        "beach_index_forecasts",
        ["beach_id", "forecast_date"],
    )
    op.create_index(
        "ix_beach_index_forecasts_forecast_date",
        "beach_index_forecasts",
        ["forecast_date"],
    )
    op.create_index(
        "ix_beach_index_forecasts_source_record_id",
        "beach_index_forecasts",
        ["source_record_id"],
    )

    op.create_table(
        "beach_water_quality_measurements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("beach_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("source_record_key", sa.String(length=255), nullable=False),
        sa.Column("survey_year", sa.Integer(), nullable=False),
        sa.Column("survey_date", sa.Date(), nullable=True),
        sa.Column("survey_round", sa.String(length=40), nullable=True),
        sa.Column("survey_kind", sa.String(length=80), nullable=True),
        sa.Column("survey_location", sa.String(length=255), nullable=True),
        sa.Column("survey_location_detail", sa.String(length=500), nullable=True),
        sa.Column("ecoli_result", sa.String(length=80), nullable=True),
        sa.Column("enterococcus_result", sa.String(length=80), nullable=True),
        sa.Column("suitability", sa.String(length=40), nullable=True),
        sa.Column("longitude", sa.Numeric(12, 8), nullable=True),
        sa.Column("latitude", sa.Numeric(12, 8), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=True),
        sa.Column("sigungu_code", sa.String(length=10), nullable=True),
        sa.Column("sido_code", sa.String(length=10), nullable=True),
        sa.Column("address_mapping_method", sa.String(length=48), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["beach_id"],
            ["beach_profiles.id"],
            name="fk_beach_water_quality_measurements_beach_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["beach_source_records.id"],
            name="fk_beach_water_quality_measurements_source_record_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_beach_water_quality_measurements"),
        sa.UniqueConstraint(
            "provider",
            "source_record_key",
            name="uq_beach_water_quality_measurements_provider_source_key",
        ),
    )
    op.create_index(
        "ix_beach_water_quality_measurements_beach_date",
        "beach_water_quality_measurements",
        ["beach_id", "survey_date"],
    )
    op.create_index(
        "ix_beach_water_quality_measurements_year",
        "beach_water_quality_measurements",
        ["survey_year"],
    )
    op.create_index(
        "ix_beach_water_quality_measurements_source_record_id",
        "beach_water_quality_measurements",
        ["source_record_id"],
    )
    op.create_index(
        "ix_beach_water_quality_measurements_geom",
        "beach_water_quality_measurements",
        ["geom"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_beach_water_quality_measurements_geom",
        table_name="beach_water_quality_measurements",
    )
    op.drop_index(
        "ix_beach_water_quality_measurements_source_record_id",
        table_name="beach_water_quality_measurements",
    )
    op.drop_index(
        "ix_beach_water_quality_measurements_year",
        table_name="beach_water_quality_measurements",
    )
    op.drop_index(
        "ix_beach_water_quality_measurements_beach_date",
        table_name="beach_water_quality_measurements",
    )
    op.drop_table("beach_water_quality_measurements")

    op.drop_index("ix_beach_index_forecasts_source_record_id", table_name="beach_index_forecasts")
    op.drop_index("ix_beach_index_forecasts_forecast_date", table_name="beach_index_forecasts")
    op.drop_index("ix_beach_index_forecasts_beach_date", table_name="beach_index_forecasts")
    op.drop_table("beach_index_forecasts")

    op.drop_index("ix_beach_observations_source_record_id", table_name="beach_observations")
    op.drop_index("ix_beach_observations_beach_time", table_name="beach_observations")
    op.drop_table("beach_observations")

    op.drop_index("ix_beach_source_records_collected_at", table_name="beach_source_records")
    op.drop_index("ix_beach_source_records_dataset_record", table_name="beach_source_records")
    op.drop_table("beach_source_records")

    op.drop_index("ix_beach_provider_refs_provider_name", table_name="beach_provider_refs")
    op.drop_index("ix_beach_provider_refs_beach_id", table_name="beach_provider_refs")
    op.drop_table("beach_provider_refs")

    op.drop_index("ix_beach_profiles_geom", table_name="beach_profiles")
    op.drop_index("ix_beach_profiles_sido", table_name="beach_profiles")
    op.drop_index("ix_beach_profiles_sigungu", table_name="beach_profiles")
    op.drop_index("ix_beach_profiles_legal_dong", table_name="beach_profiles")
    op.drop_index("ix_beach_profiles_place_id", table_name="beach_profiles")
    op.drop_table("beach_profiles")
