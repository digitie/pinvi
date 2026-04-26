"""add vworld region boundary tables

Revision ID: 20260425_0004
Revises: 20260425_0003
Create Date: 2026-04-25 14:30:00
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260425_0004"
down_revision: str | None = "20260425_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "address_code_standard",
        sa.Column("sido_code", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "address_code_standard",
        sa.Column("sigungu_code", sa.String(length=10), nullable=True),
    )
    op.execute(
        "UPDATE address_code_standard "
        "SET sido_code = substring(legal_dong_code from 1 for 2) || '00000000', "
        "sigungu_code = substring(legal_dong_code from 1 for 5) || '00000'"
    )
    op.alter_column("address_code_standard", "sido_code", nullable=False)
    op.alter_column("address_code_standard", "sigungu_code", nullable=False)
    op.create_index(
        "ix_address_code_standard_sido_code",
        "address_code_standard",
        ["sido_code"],
        unique=False,
    )
    op.create_index(
        "ix_address_code_standard_sigungu_code",
        "address_code_standard",
        ["sigungu_code"],
        unique=False,
    )

    op.create_table(
        "region_boundary_import_batch",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("source_file_hash", sa.String(length=64), nullable=False),
        sa.Column("layer_code", sa.String(length=32), nullable=False),
        sa.Column("boundary_level", sa.String(length=32), nullable=False),
        sa.Column("source_encoding", sa.String(length=16), nullable=False),
        sa.Column("source_srid", sa.Integer(), nullable=False),
        sa.Column("serving_srid", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_region_boundary_import_batch"),
    )

    op.create_table(
        "region_raw_vworld_boundary",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("layer_code", sa.String(length=32), nullable=False),
        sa.Column("boundary_level", sa.String(length=32), nullable=False),
        sa.Column("ufid", sa.String(length=34), nullable=False),
        sa.Column("bjcd", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("divi", sa.String(length=20), nullable=False),
        sa.Column("scls", sa.String(length=8), nullable=False),
        sa.Column("fmta", sa.String(length=9), nullable=False),
        sa.Column("raw_attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("source_file_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=5179,
                spatial_index=False,
            ),
            nullable=False,
        ),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["region_boundary_import_batch.id"],
            name="fk_rrvb_batch",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_region_raw_vworld_boundary"),
        sa.UniqueConstraint("import_batch_id", "ufid", name="uq_rrvb_batch_ufid"),
    )
    op.create_index("ix_rrvb_batch_id", "region_raw_vworld_boundary", ["import_batch_id"])
    op.create_index("ix_rrvb_bjcd", "region_raw_vworld_boundary", ["bjcd"])
    op.create_index(
        "ix_rrvb_geom",
        "region_raw_vworld_boundary",
        ["geom"],
        postgresql_using="gist",
    )

    op.create_table(
        "region_serving_boundary",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_boundary_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("layer_code", sa.String(length=32), nullable=False),
        sa.Column("boundary_level", sa.String(length=32), nullable=False),
        sa.Column("region_code", sa.String(length=10), nullable=False),
        sa.Column("region_name", sa.String(length=100), nullable=False),
        sa.Column("sido_code", sa.String(length=10), nullable=False),
        sa.Column("sigungu_code", sa.String(length=10), nullable=True),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=True),
        sa.Column("parent_region_code", sa.String(length=10), nullable=True),
        sa.Column("full_region_name", sa.String(length=255), nullable=False),
        sa.Column("address_code_standard_code", sa.String(length=10), nullable=True),
        sa.Column("address_code_matched", sa.Boolean(), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("source_file_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                spatial_index=False,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["address_code_standard_code"],
            ["address_code_standard.legal_dong_code"],
            name="fk_rsb_address_code_standard",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["region_boundary_import_batch.id"],
            name="fk_rsb_batch",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["raw_boundary_id"],
            ["region_raw_vworld_boundary.id"],
            name="fk_rsb_raw_boundary",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_region_serving_boundary"),
        sa.UniqueConstraint("boundary_level", "region_code", name="uq_rsb_level_code"),
    )
    op.create_index(
        "ix_rsb_legal_dong_code",
        "region_serving_boundary",
        ["legal_dong_code"],
    )
    op.create_index(
        "ix_rsb_level_code",
        "region_serving_boundary",
        ["boundary_level", "region_code"],
    )
    op.create_index("ix_rsb_sido_code", "region_serving_boundary", ["sido_code"])
    op.create_index("ix_rsb_sigungu_code", "region_serving_boundary", ["sigungu_code"])
    op.create_index(
        "ix_rsb_geom",
        "region_serving_boundary",
        ["geom"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_rsb_geom", table_name="region_serving_boundary")
    op.drop_index("ix_rsb_sigungu_code", table_name="region_serving_boundary")
    op.drop_index("ix_rsb_sido_code", table_name="region_serving_boundary")
    op.drop_index("ix_rsb_level_code", table_name="region_serving_boundary")
    op.drop_index("ix_rsb_legal_dong_code", table_name="region_serving_boundary")
    op.drop_table("region_serving_boundary")

    op.drop_index("ix_rrvb_geom", table_name="region_raw_vworld_boundary")
    op.drop_index("ix_rrvb_bjcd", table_name="region_raw_vworld_boundary")
    op.drop_index("ix_rrvb_batch_id", table_name="region_raw_vworld_boundary")
    op.drop_table("region_raw_vworld_boundary")

    op.drop_table("region_boundary_import_batch")

    op.drop_index("ix_address_code_standard_sigungu_code", table_name="address_code_standard")
    op.drop_index("ix_address_code_standard_sido_code", table_name="address_code_standard")
    op.drop_column("address_code_standard", "sigungu_code")
    op.drop_column("address_code_standard", "sido_code")
