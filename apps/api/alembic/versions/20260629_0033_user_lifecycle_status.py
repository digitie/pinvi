"""user lifecycle pending-delete status

Revision ID: 20260629_0033
Revises: 20260628_0032
Create Date: 2026-06-29 06:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260629_0033"
down_revision: str | None = "20260628_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_users_status", "users", schema="app", type_="check")
    op.create_check_constraint(
        "ck_users_status",
        "users",
        "status IN ('pending_verification', 'pending_profile', 'active', 'disabled', "
        "'pending_delete', 'deleted')",
        schema="app",
    )


def downgrade() -> None:
    op.execute("UPDATE app.users SET status = 'deleted' WHERE status = 'pending_delete'")
    op.drop_constraint("ck_users_status", "users", schema="app", type_="check")
    op.create_check_constraint(
        "ck_users_status",
        "users",
        "status IN ('pending_verification', 'pending_profile', 'active', 'disabled', 'deleted')",
        schema="app",
    )
