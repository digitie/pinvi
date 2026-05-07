"""add KHOA ocean activity index tables

Revision ID: 20260429_0022
Revises: 20260429_0021
Create Date: 2026-04-29 23:40:00
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260429_0022"
down_revision: str | None = "20260429_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ocean_activity_index_locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_dataset_key", sa.String(length=120), nullable=False),
        sa.Column("provider_location_id", sa.String(length=180), nullable=False),
        sa.Column("provider_place_code", sa.String(length=80), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
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
        sa.Column("address_snapshot", sa.String(length=700), nullable=True),
        sa.Column("address_mapping_method", sa.String(length=48), nullable=False),
        sa.Column(
            "source_specific_attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["legal_dong_code"],
            ["address_code_standard.legal_dong_code"],
            name="fk_oail_legal_dong_code",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ocean_activity_index_locations"),
        sa.UniqueConstraint(
            "provider",
            "provider_dataset_key",
            "provider_location_id",
            name="uq_oail_provider_dataset_location",
        ),
    )
    op.create_index(
        "ix_oail_dataset_name",
        "ocean_activity_index_locations",
        ["provider_dataset_key", "normalized_name"],
    )
    op.create_index(
        "ix_oail_legal_dong_code",
        "ocean_activity_index_locations",
        ["legal_dong_code"],
    )
    op.create_index(
        "ix_oail_sigungu_code",
        "ocean_activity_index_locations",
        ["sigungu_code"],
    )
    op.create_index(
        "ix_oail_sido_code",
        "ocean_activity_index_locations",
        ["sido_code"],
    )
    op.create_index(
        "ix_oail_geom",
        "ocean_activity_index_locations",
        ["geom"],
        postgresql_using="gist",
    )

    op.create_table(
        "ocean_activity_index_source_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("dataset_key", sa.String(length=120), nullable=False),
        sa.Column("endpoint", sa.String(length=180), nullable=False),
        sa.Column("source_record_id", sa.String(length=255), nullable=False),
        sa.Column("request_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ocean_activity_index_source_records"),
        sa.UniqueConstraint(
            "provider",
            "dataset_key",
            "source_record_id",
            "response_hash",
            name="uq_oaisr_provider_dataset_record_hash",
        ),
    )
    op.create_index(
        "ix_oaisr_dataset_record",
        "ocean_activity_index_source_records",
        ["dataset_key", "source_record_id"],
    )
    op.create_index(
        "ix_oaisr_collected_at",
        "ocean_activity_index_source_records",
        ["collected_at"],
    )

    op.create_table(
        "ocean_activity_index_forecasts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_dataset_key", sa.String(length=120), nullable=False),
        sa.Column("provider_place_code", sa.String(length=80), nullable=True),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("forecast_slot", sa.String(length=24), nullable=False),
        sa.Column("activity_time_key", sa.String(length=120), nullable=False),
        sa.Column("activity_time_text", sa.Text(), nullable=True),
        sa.Column("activity_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activity_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weather", sa.String(length=80), nullable=True),
        sa.Column("air_temperature_c", sa.Numeric(8, 3), nullable=True),
        sa.Column("wind_speed_ms", sa.Numeric(8, 3), nullable=True),
        sa.Column("index_score", sa.Numeric(8, 3), nullable=True),
        sa.Column("total_index", sa.String(length=80), nullable=True),
        sa.Column("grade", sa.String(length=80), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["ocean_activity_index_locations.id"],
            name="fk_oaif_location_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["ocean_activity_index_source_records.id"],
            name="fk_oaif_source_record_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ocean_activity_index_forecasts"),
        sa.UniqueConstraint(
            "provider",
            "provider_dataset_key",
            "location_id",
            "forecast_date",
            "forecast_slot",
            "activity_time_key",
            name="uq_oaif_provider_location_date_slot_time",
        ),
    )
    op.create_index(
        "ix_oaif_location_date",
        "ocean_activity_index_forecasts",
        ["location_id", "forecast_date"],
    )
    op.create_index(
        "ix_oaif_forecast_date",
        "ocean_activity_index_forecasts",
        ["forecast_date"],
    )
    op.create_index(
        "ix_oaif_source_record_id",
        "ocean_activity_index_forecasts",
        ["source_record_id"],
    )
    op.create_index(
        "ix_oaif_dataset_date",
        "ocean_activity_index_forecasts",
        ["provider_dataset_key", "forecast_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_oaif_dataset_date", table_name="ocean_activity_index_forecasts")
    op.drop_index("ix_oaif_source_record_id", table_name="ocean_activity_index_forecasts")
    op.drop_index("ix_oaif_forecast_date", table_name="ocean_activity_index_forecasts")
    op.drop_index("ix_oaif_location_date", table_name="ocean_activity_index_forecasts")
    op.drop_table("ocean_activity_index_forecasts")
    op.drop_index("ix_oaisr_collected_at", table_name="ocean_activity_index_source_records")
    op.drop_index("ix_oaisr_dataset_record", table_name="ocean_activity_index_source_records")
    op.drop_table("ocean_activity_index_source_records")
    op.drop_index("ix_oail_geom", table_name="ocean_activity_index_locations")
    op.drop_index("ix_oail_sido_code", table_name="ocean_activity_index_locations")
    op.drop_index("ix_oail_sigungu_code", table_name="ocean_activity_index_locations")
    op.drop_index("ix_oail_legal_dong_code", table_name="ocean_activity_index_locations")
    op.drop_index("ix_oail_dataset_name", table_name="ocean_activity_index_locations")
    op.drop_table("ocean_activity_index_locations")
