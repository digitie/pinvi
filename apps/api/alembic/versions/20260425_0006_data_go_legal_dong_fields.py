"""add data.go.kr legal dong code fields

Revision ID: 20260425_0006
Revises: 20260425_0005
Create Date: 2026-04-25 18:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260425_0006"
down_revision: str | None = "20260425_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("address_code_standard", sa.Column("source_sort_order", sa.Integer()))
    op.add_column("address_code_standard", sa.Column("source_created_date", sa.String(10)))
    op.add_column("address_code_standard", sa.Column("source_deleted_date", sa.String(10)))
    op.add_column("address_code_standard", sa.Column("previous_legal_dong_code", sa.String(10)))
    op.create_index(
        "ix_address_code_standard_previous_legal_dong_code",
        "address_code_standard",
        ["previous_legal_dong_code"],
    )

    op.add_column("address_raw_legal_dong_code", sa.Column("sido_name", sa.String(40)))
    op.add_column("address_raw_legal_dong_code", sa.Column("sigungu_name", sa.String(80)))
    op.add_column(
        "address_raw_legal_dong_code",
        sa.Column("legal_eupmyeondong_name", sa.String(80)),
    )
    op.add_column("address_raw_legal_dong_code", sa.Column("legal_ri_name", sa.String(80)))
    op.add_column("address_raw_legal_dong_code", sa.Column("source_sort_order", sa.Integer()))
    op.add_column("address_raw_legal_dong_code", sa.Column("source_created_date", sa.String(10)))
    op.add_column("address_raw_legal_dong_code", sa.Column("source_deleted_date", sa.String(10)))
    op.add_column(
        "address_raw_legal_dong_code",
        sa.Column("previous_legal_dong_code", sa.String(10)),
    )


def downgrade() -> None:
    op.drop_column("address_raw_legal_dong_code", "previous_legal_dong_code")
    op.drop_column("address_raw_legal_dong_code", "source_deleted_date")
    op.drop_column("address_raw_legal_dong_code", "source_created_date")
    op.drop_column("address_raw_legal_dong_code", "source_sort_order")
    op.drop_column("address_raw_legal_dong_code", "legal_ri_name")
    op.drop_column("address_raw_legal_dong_code", "legal_eupmyeondong_name")
    op.drop_column("address_raw_legal_dong_code", "sigungu_name")
    op.drop_column("address_raw_legal_dong_code", "sido_name")

    op.drop_index(
        "ix_address_code_standard_previous_legal_dong_code",
        table_name="address_code_standard",
    )
    op.drop_column("address_code_standard", "previous_legal_dong_code")
    op.drop_column("address_code_standard", "source_deleted_date")
    op.drop_column("address_code_standard", "source_created_date")
    op.drop_column("address_code_standard", "source_sort_order")
