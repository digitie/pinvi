"""add juso raw road address and legal dong code tables

Revision ID: 20260424_0002
Revises: 20260418_0001
Create Date: 2026-04-24 10:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260424_0002"
down_revision: str | None = "20260418_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "address_raw_juso_road_address",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("source_year_month", sa.String(length=6), nullable=False),
        sa.Column("source_file_hash", sa.String(length=64), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("delimiter", sa.String(length=8), nullable=False),
        sa.Column("road_address_management_no", sa.String(length=64), nullable=False),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=False),
        sa.Column("road_name_code", sa.String(length=12), nullable=False),
        sa.Column("administrative_dong_code", sa.String(length=10), nullable=True),
        sa.Column("effective_date", sa.String(length=8), nullable=False),
        sa.Column("change_reason_code", sa.String(length=2), nullable=False),
        sa.Column("raw_line", sa.Text(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_address_raw_juso_road_address"),
        sa.UniqueConstraint(
            "source_file_hash",
            "row_number",
            name="uq_address_raw_juso_road_address_source_file_hash_row_number",
        ),
    )
    op.create_index(
        "ix_address_raw_juso_road_address_legal_dong_code",
        "address_raw_juso_road_address",
        ["legal_dong_code"],
        unique=False,
    )
    op.create_index(
        "ix_address_raw_juso_road_address_source_file_hash",
        "address_raw_juso_road_address",
        ["source_file_hash"],
        unique=False,
    )
    op.create_index(
        "ix_address_raw_juso_road_address_source_year_month",
        "address_raw_juso_road_address",
        ["source_year_month"],
        unique=False,
    )

    op.create_table(
        "address_code_standard",
        sa.Column("legal_dong_code", sa.String(length=10), nullable=False),
        sa.Column("sido_name", sa.String(length=40), nullable=False),
        sa.Column("sigungu_name", sa.String(length=80), nullable=False),
        sa.Column("legal_eupmyeondong_name", sa.String(length=80), nullable=False),
        sa.Column("legal_ri_name", sa.String(length=80), nullable=True),
        sa.Column("full_legal_dong_name", sa.String(length=255), nullable=False),
        sa.Column("source_effective_date", sa.String(length=8), nullable=False),
        sa.Column("source_change_reason_code", sa.String(length=2), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("source_year_month", sa.String(length=6), nullable=False),
        sa.Column("source_file_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("legal_dong_code", name="pk_address_code_standard"),
    )


def downgrade() -> None:
    op.drop_table("address_code_standard")
    op.drop_index(
        "ix_address_raw_juso_road_address_source_year_month",
        table_name="address_raw_juso_road_address",
    )
    op.drop_index(
        "ix_address_raw_juso_road_address_source_file_hash",
        table_name="address_raw_juso_road_address",
    )
    op.drop_index(
        "ix_address_raw_juso_road_address_legal_dong_code",
        table_name="address_raw_juso_road_address",
    )
    op.drop_table("address_raw_juso_road_address")
