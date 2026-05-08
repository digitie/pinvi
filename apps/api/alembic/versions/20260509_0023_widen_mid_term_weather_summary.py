"""widen mid-term weather summary

Revision ID: 20260509_0023
Revises: 20260429_0022
Create Date: 2026-05-09 00:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260509_0023"
down_revision: str | None = "20260429_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "weather_serving_mid_term",
        "weather_summary",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "weather_serving_mid_term",
        "weather_summary",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
