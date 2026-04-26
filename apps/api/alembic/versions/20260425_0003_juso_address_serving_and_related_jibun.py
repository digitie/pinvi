"""add juso serving road address and related jibun tables

Revision ID: 20260425_0003
Revises: 20260424_0002
Create Date: 2026-04-25 09:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260425_0003"
down_revision: str | None = "20260424_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "address_serving_juso_road_address",
        sa.Column("road_address_management_no", sa.String(length=64), nullable=False),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=False),
        sa.Column("road_name_code", sa.String(length=12), nullable=False),
        sa.Column("administrative_dong_code", sa.String(length=10), nullable=True),
        sa.Column("sido_name", sa.String(length=40), nullable=False),
        sa.Column("sigungu_name", sa.String(length=80), nullable=False),
        sa.Column("legal_eupmyeondong_name", sa.String(length=80), nullable=False),
        sa.Column("legal_ri_name", sa.String(length=80), nullable=True),
        sa.Column("road_name", sa.String(length=120), nullable=False),
        sa.Column("administrative_dong_name", sa.String(length=80), nullable=True),
        sa.Column("mountain_yn", sa.String(length=1), nullable=False),
        sa.Column("jibun_main_no", sa.String(length=16), nullable=False),
        sa.Column("jibun_sub_no", sa.String(length=16), nullable=False),
        sa.Column("underground_yn", sa.String(length=1), nullable=False),
        sa.Column("building_main_no", sa.String(length=16), nullable=False),
        sa.Column("building_sub_no", sa.String(length=16), nullable=False),
        sa.Column("postal_code", sa.String(length=5), nullable=True),
        sa.Column("previous_road_address", sa.String(length=255), nullable=True),
        sa.Column("apartment_yn", sa.String(length=1), nullable=True),
        sa.Column("building_registry_name", sa.String(length=255), nullable=True),
        sa.Column("sigungu_building_name", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("full_legal_dong_name", sa.String(length=255), nullable=False),
        sa.Column("full_road_address", sa.String(length=255), nullable=False),
        sa.Column("source_effective_date", sa.String(length=8), nullable=False),
        sa.Column("source_change_reason_code", sa.String(length=2), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("source_year_month", sa.String(length=6), nullable=False),
        sa.Column("source_file_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "road_address_management_no", name="pk_address_serving_juso_road_address"
        ),
    )
    op.create_index(
        "ix_address_serving_juso_road_address_administrative_dong_code",
        "address_serving_juso_road_address",
        ["administrative_dong_code"],
        unique=False,
    )
    op.create_index(
        "ix_address_serving_juso_road_address_legal_dong_code",
        "address_serving_juso_road_address",
        ["legal_dong_code"],
        unique=False,
    )
    op.create_index(
        "ix_address_serving_juso_road_address_road_name_code",
        "address_serving_juso_road_address",
        ["road_name_code"],
        unique=False,
    )

    op.create_table(
        "address_raw_juso_related_jibun",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("source_year_month", sa.String(length=6), nullable=False),
        sa.Column("source_file_hash", sa.String(length=64), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("delimiter", sa.String(length=8), nullable=False),
        sa.Column("road_address_management_no", sa.String(length=64), nullable=False),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=False),
        sa.Column("sido_name", sa.String(length=40), nullable=False),
        sa.Column("sigungu_name", sa.String(length=80), nullable=False),
        sa.Column("legal_eupmyeondong_name", sa.String(length=80), nullable=False),
        sa.Column("legal_ri_name", sa.String(length=80), nullable=True),
        sa.Column("mountain_yn", sa.String(length=1), nullable=False),
        sa.Column("jibun_main_no", sa.String(length=16), nullable=False),
        sa.Column("jibun_sub_no", sa.String(length=16), nullable=False),
        sa.Column("road_name_code", sa.String(length=12), nullable=False),
        sa.Column("underground_yn", sa.String(length=1), nullable=False),
        sa.Column("building_main_no", sa.String(length=16), nullable=False),
        sa.Column("building_sub_no", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("raw_line", sa.Text(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_address_raw_juso_related_jibun"),
        sa.UniqueConstraint(
            "source_file_hash",
            "row_number",
            name="uq_address_raw_juso_related_jibun_source_file_hash_row_number",
        ),
    )
    op.create_index(
        "ix_address_raw_juso_related_jibun_legal_dong_code",
        "address_raw_juso_related_jibun",
        ["legal_dong_code"],
        unique=False,
    )
    op.create_index(
        "ix_address_raw_juso_related_jibun_source_file_hash",
        "address_raw_juso_related_jibun",
        ["source_file_hash"],
        unique=False,
    )
    op.create_index(
        "ix_address_raw_juso_related_jibun_source_year_month",
        "address_raw_juso_related_jibun",
        ["source_year_month"],
        unique=False,
    )

    op.create_table(
        "address_serving_juso_related_jibun",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("road_address_management_no", sa.String(length=64), nullable=False),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=False),
        sa.Column("road_name_code", sa.String(length=12), nullable=False),
        sa.Column("sido_name", sa.String(length=40), nullable=False),
        sa.Column("sigungu_name", sa.String(length=80), nullable=False),
        sa.Column("legal_eupmyeondong_name", sa.String(length=80), nullable=False),
        sa.Column("legal_ri_name", sa.String(length=80), nullable=True),
        sa.Column("mountain_yn", sa.String(length=1), nullable=False),
        sa.Column("jibun_main_no", sa.String(length=16), nullable=False),
        sa.Column("jibun_sub_no", sa.String(length=16), nullable=False),
        sa.Column("underground_yn", sa.String(length=1), nullable=False),
        sa.Column("building_main_no", sa.String(length=16), nullable=False),
        sa.Column("building_sub_no", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("full_legal_dong_name", sa.String(length=255), nullable=False),
        sa.Column("full_jibun_address", sa.String(length=255), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("source_year_month", sa.String(length=6), nullable=False),
        sa.Column("source_file_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["road_address_management_no"],
            ["address_serving_juso_road_address.road_address_management_no"],
            name="fk_addr_serv_rel_jibun_ramno",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_address_serving_juso_related_jibun"),
        sa.UniqueConstraint(
            "road_address_management_no",
            "legal_dong_code",
            "mountain_yn",
            "jibun_main_no",
            "jibun_sub_no",
            name="uq_address_serving_juso_related_jibun_relation",
        ),
    )
    op.create_index(
        "ix_address_serving_juso_related_jibun_legal_dong_code",
        "address_serving_juso_related_jibun",
        ["legal_dong_code"],
        unique=False,
    )
    op.create_index(
        "ix_asjrj_ramno",
        "address_serving_juso_related_jibun",
        ["road_address_management_no"],
        unique=False,
    )
    op.create_index(
        "ix_address_serving_juso_related_jibun_road_name_code",
        "address_serving_juso_related_jibun",
        ["road_name_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_address_serving_juso_related_jibun_road_name_code",
        table_name="address_serving_juso_related_jibun",
    )
    op.drop_index(
        "ix_asjrj_ramno",
        table_name="address_serving_juso_related_jibun",
    )
    op.drop_index(
        "ix_address_serving_juso_related_jibun_legal_dong_code",
        table_name="address_serving_juso_related_jibun",
    )
    op.drop_table("address_serving_juso_related_jibun")

    op.drop_index(
        "ix_address_raw_juso_related_jibun_source_year_month",
        table_name="address_raw_juso_related_jibun",
    )
    op.drop_index(
        "ix_address_raw_juso_related_jibun_source_file_hash",
        table_name="address_raw_juso_related_jibun",
    )
    op.drop_index(
        "ix_address_raw_juso_related_jibun_legal_dong_code",
        table_name="address_raw_juso_related_jibun",
    )
    op.drop_table("address_raw_juso_related_jibun")

    op.drop_index(
        "ix_address_serving_juso_road_address_road_name_code",
        table_name="address_serving_juso_road_address",
    )
    op.drop_index(
        "ix_address_serving_juso_road_address_legal_dong_code",
        table_name="address_serving_juso_road_address",
    )
    op.drop_index(
        "ix_address_serving_juso_road_address_administrative_dong_code",
        table_name="address_serving_juso_road_address",
    )
    op.drop_table("address_serving_juso_road_address")
