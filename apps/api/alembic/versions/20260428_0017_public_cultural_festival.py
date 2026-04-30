"""add public cultural festival tables

Revision ID: 20260428_0017
Revises: 20260427_0016
Create Date: 2026-04-28 10:30:00
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260428_0017"
down_revision: str | None = "20260427_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tour_raw_public_cultural_festival",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("source_record_id", sa.String(length=64), nullable=False),
        sa.Column("request_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_tour_raw_public_cultural_festival"),
        sa.UniqueConstraint(
            "provider",
            "source_record_id",
            "response_hash",
            name="uq_trpcf_provider_source_hash",
        ),
    )
    op.create_index(
        "ix_trpcf_source_record",
        "tour_raw_public_cultural_festival",
        ["provider", "source_record_id"],
    )
    op.create_index(
        "ix_trpcf_collected_at",
        "tour_raw_public_cultural_festival",
        ["collected_at"],
    )
    op.create_index(
        "ix_trpcf_response_hash",
        "tour_raw_public_cultural_festival",
        ["response_hash"],
    )

    op.create_table(
        "tour_serving_public_cultural_festival",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("source_record_id", sa.String(length=64), nullable=False),
        sa.Column("place_join_key", sa.String(length=180), nullable=False),
        sa.Column("festival_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_festival_name", sa.String(length=255), nullable=False),
        sa.Column("venue_name", sa.String(length=500), nullable=True),
        sa.Column("event_start_date", sa.Date(), nullable=True),
        sa.Column("event_end_date", sa.Date(), nullable=True),
        sa.Column("event_status", sa.String(length=32), nullable=False),
        sa.Column("festival_content", sa.Text(), nullable=True),
        sa.Column("mnnst_name", sa.String(length=255), nullable=True),
        sa.Column("auspc_instt_name", sa.String(length=255), nullable=True),
        sa.Column("suprt_instt_name", sa.String(length=500), nullable=True),
        sa.Column("phone_number", sa.String(length=120), nullable=True),
        sa.Column("homepage_url", sa.Text(), nullable=True),
        sa.Column("related_info", sa.Text(), nullable=True),
        sa.Column("road_address", sa.String(length=500), nullable=True),
        sa.Column("jibun_address", sa.String(length=500), nullable=True),
        sa.Column("address_snapshot", sa.String(length=700), nullable=True),
        sa.Column("longitude", sa.Numeric(12, 8), nullable=True),
        sa.Column("latitude", sa.Numeric(12, 8), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=True),
        sa.Column("road_name_code", sa.String(length=12), nullable=True),
        sa.Column("road_address_management_no", sa.String(length=64), nullable=True),
        sa.Column("sigungu_code", sa.String(length=10), nullable=True),
        sa.Column("sido_code", sa.String(length=10), nullable=True),
        sa.Column("address_mapping_method", sa.String(length=40), nullable=False),
        sa.Column("provider_institution_code", sa.String(length=40), nullable=True),
        sa.Column("provider_institution_name", sa.String(length=120), nullable=True),
        sa.Column("reference_date", sa.Date(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["legal_dong_code"],
            ["address_code_standard.legal_dong_code"],
            name="fk_tspcf_legal_dong_code",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tour_serving_public_cultural_festival"),
        sa.UniqueConstraint(
            "provider",
            "source_record_id",
            name="uq_tspcf_provider_source_record",
        ),
    )
    op.create_index(
        "ix_tspcf_event_dates",
        "tour_serving_public_cultural_festival",
        ["event_start_date", "event_end_date"],
    )
    op.create_index(
        "ix_tspcf_status_dates",
        "tour_serving_public_cultural_festival",
        ["event_status", "event_start_date", "event_end_date"],
    )
    op.create_index(
        "ix_tspcf_legal_dong",
        "tour_serving_public_cultural_festival",
        ["legal_dong_code"],
    )
    op.create_index(
        "ix_tspcf_sigungu",
        "tour_serving_public_cultural_festival",
        ["sigungu_code"],
    )
    op.create_index(
        "ix_tspcf_place_join_key",
        "tour_serving_public_cultural_festival",
        ["place_join_key"],
    )
    op.create_index(
        "ix_tspcf_geom",
        "tour_serving_public_cultural_festival",
        ["geom"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_tspcf_geom", table_name="tour_serving_public_cultural_festival")
    op.drop_index("ix_tspcf_place_join_key", table_name="tour_serving_public_cultural_festival")
    op.drop_index("ix_tspcf_sigungu", table_name="tour_serving_public_cultural_festival")
    op.drop_index("ix_tspcf_legal_dong", table_name="tour_serving_public_cultural_festival")
    op.drop_index("ix_tspcf_status_dates", table_name="tour_serving_public_cultural_festival")
    op.drop_index("ix_tspcf_event_dates", table_name="tour_serving_public_cultural_festival")
    op.drop_table("tour_serving_public_cultural_festival")

    op.drop_index("ix_trpcf_response_hash", table_name="tour_raw_public_cultural_festival")
    op.drop_index("ix_trpcf_collected_at", table_name="tour_raw_public_cultural_festival")
    op.drop_index("ix_trpcf_source_record", table_name="tour_raw_public_cultural_festival")
    op.drop_table("tour_raw_public_cultural_festival")
