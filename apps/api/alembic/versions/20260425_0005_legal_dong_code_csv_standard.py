"""add legal dong code csv standard loader support

Revision ID: 20260425_0005
Revises: 20260425_0004
Create Date: 2026-04-25 16:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260425_0005"
down_revision: str | None = "20260425_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("address_code_standard", sa.Column("code_level", sa.String(32)))
    op.add_column("address_code_standard", sa.Column("code_name", sa.String(255)))
    op.add_column("address_code_standard", sa.Column("source_provider", sa.String(32)))
    op.add_column("address_code_standard", sa.Column("source_status", sa.String(40)))
    op.add_column(
        "address_code_standard",
        sa.Column("is_discontinued", sa.Boolean(), server_default=sa.text("false")),
    )
    op.execute(
        "UPDATE address_code_standard "
        "SET code_level = CASE "
        "WHEN substring(legal_dong_code from 3) = '00000000' THEN 'sido' "
        "WHEN substring(legal_dong_code from 6) = '00000' THEN 'sigungu' "
        "ELSE 'legal_dong' END, "
        "code_name = full_legal_dong_name, "
        "source_provider = 'juso_road_address', "
        "source_status = 'derived_from_juso', "
        "is_discontinued = false"
    )
    op.alter_column("address_code_standard", "code_level", nullable=False)
    op.alter_column("address_code_standard", "code_name", nullable=False)
    op.alter_column("address_code_standard", "source_provider", nullable=False)
    op.alter_column("address_code_standard", "source_status", nullable=False)
    op.alter_column("address_code_standard", "is_discontinued", nullable=False)
    op.alter_column("address_code_standard", "sido_name", nullable=True)
    op.alter_column("address_code_standard", "sigungu_name", nullable=True)
    op.alter_column("address_code_standard", "legal_eupmyeondong_name", nullable=True)
    op.create_index("ix_address_code_standard_code_level", "address_code_standard", ["code_level"])

    op.create_table(
        "address_raw_legal_dong_code",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_file_name", sa.String(255), nullable=False),
        sa.Column("source_file_hash", sa.String(64), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("legal_dong_code", sa.String(10), nullable=False),
        sa.Column("legal_dong_name", sa.String(255), nullable=False),
        sa.Column("discontinued_status", sa.String(40), nullable=False),
        sa.Column("raw_line", sa.Text(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_address_raw_legal_dong_code"),
        sa.UniqueConstraint("source_file_hash", "row_number", name="uq_arlc_file_row"),
    )
    op.create_index(
        "ix_address_raw_legal_dong_code_legal_dong_code",
        "address_raw_legal_dong_code",
        ["legal_dong_code"],
    )
    op.create_index(
        "ix_address_raw_legal_dong_code_source_file_hash",
        "address_raw_legal_dong_code",
        ["source_file_hash"],
    )

    op.create_foreign_key(
        "fk_asjra_legal_code",
        "address_serving_juso_road_address",
        "address_code_standard",
        ["legal_dong_code"],
        ["legal_dong_code"],
    )
    op.create_foreign_key(
        "fk_asjrj_legal_code",
        "address_serving_juso_related_jibun",
        "address_code_standard",
        ["legal_dong_code"],
        ["legal_dong_code"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_asjrj_legal_code",
        "address_serving_juso_related_jibun",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_asjra_legal_code",
        "address_serving_juso_road_address",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_address_raw_legal_dong_code_source_file_hash",
        table_name="address_raw_legal_dong_code",
    )
    op.drop_index(
        "ix_address_raw_legal_dong_code_legal_dong_code",
        table_name="address_raw_legal_dong_code",
    )
    op.drop_table("address_raw_legal_dong_code")

    op.drop_index("ix_address_code_standard_code_level", table_name="address_code_standard")
    op.alter_column("address_code_standard", "legal_eupmyeondong_name", nullable=False)
    op.alter_column("address_code_standard", "sigungu_name", nullable=False)
    op.alter_column("address_code_standard", "sido_name", nullable=False)
    op.drop_column("address_code_standard", "is_discontinued")
    op.drop_column("address_code_standard", "source_status")
    op.drop_column("address_code_standard", "source_provider")
    op.drop_column("address_code_standard", "code_name")
    op.drop_column("address_code_standard", "code_level")
