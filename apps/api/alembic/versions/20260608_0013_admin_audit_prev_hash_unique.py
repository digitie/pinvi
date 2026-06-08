"""admin_audit_log prev_hash unique guard

Revision ID: 20260608_0013
Revises: 20260608_0012
Create Date: 2026-06-08 16:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260608_0013"
down_revision: str | None = "20260608_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_admin_audit_log_prev_hash",
        "admin_audit_log",
        ["prev_hash"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_admin_audit_log_prev_hash",
        "admin_audit_log",
        schema="app",
        type_="unique",
    )
