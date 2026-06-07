"""budget constraints

Revision ID: 20260606_0009
Revises: 20260606_0008
Create Date: 2026-06-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260606_0009"
down_revision: str | None = "20260606_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_trip_day_pois_budget_nonnegative",
        "trip_day_pois",
        "budget_amount IS NULL OR budget_amount >= 0",
        schema="app",
    )
    op.create_check_constraint(
        "ck_trip_day_pois_actual_nonnegative",
        "trip_day_pois",
        "actual_amount IS NULL OR actual_amount >= 0",
        schema="app",
    )
    op.create_check_constraint(
        "ck_trip_day_pois_currency",
        "trip_day_pois",
        "currency ~ '^[A-Z]{3}$'",
        schema="app",
    )
    op.create_check_constraint(
        "ck_notice_pois_budget_nonnegative",
        "notice_pois",
        "budget_amount IS NULL OR budget_amount >= 0",
        schema="app",
    )
    op.create_check_constraint(
        "ck_notice_pois_currency",
        "notice_pois",
        "currency ~ '^[A-Z]{3}$'",
        schema="app",
    )


def downgrade() -> None:
    op.drop_constraint("ck_notice_pois_currency", "notice_pois", schema="app")
    op.drop_constraint("ck_notice_pois_budget_nonnegative", "notice_pois", schema="app")
    op.drop_constraint("ck_trip_day_pois_currency", "trip_day_pois", schema="app")
    op.drop_constraint(
        "ck_trip_day_pois_actual_nonnegative",
        "trip_day_pois",
        schema="app",
    )
    op.drop_constraint(
        "ck_trip_day_pois_budget_nonnegative",
        "trip_day_pois",
        schema="app",
    )
