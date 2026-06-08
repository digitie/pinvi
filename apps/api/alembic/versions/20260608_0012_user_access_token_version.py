"""user access token version

Revision ID: 20260608_0012
Revises: 20260607_0011
Create Date: 2026-06-08 13:00:00

T-163: 비밀번호 재설정 후 기존 access JWT도 즉시 무효화할 수 있도록
사용자별 access token version을 둔다.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260608_0012"
down_revision: str | None = "20260607_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "access_token_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema="app",
    )
    op.create_check_constraint(
        "ck_users_access_token_version_nonnegative",
        "users",
        "access_token_version >= 0",
        schema="app",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_users_access_token_version_nonnegative",
        "users",
        schema="app",
    )
    op.drop_column("users", "access_token_version", schema="app")
