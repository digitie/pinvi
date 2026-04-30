"""seed default admin user

Revision ID: 20260427_0013
Revises: 20260427_0012
Create Date: 2026-04-27 22:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260427_0013"
down_revision: str | None = "20260427_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_ADMIN_ID = "00000000-0000-4000-8000-000000000001"
DEFAULT_ADMIN_EMAIL = "admin@ad.min"
DEFAULT_ADMIN_PASSWORD_HASH = (
    "pbkdf2_sha256$260000$tripmate_admin_default$xOxEP0s53rNT2dm8-6JHfrxjMoKzxbPGl8JoxF6G2_o"
)


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO users (
                id,
                email,
                password_hash,
                display_name,
                is_active,
                is_admin,
                is_privileged,
                created_at,
                updated_at
            )
            VALUES (
                :id,
                :email,
                :password_hash,
                'TripMate 관리자',
                true,
                true,
                true,
                now(),
                now()
            )
            ON CONFLICT (email) DO UPDATE
            SET
                is_active = true,
                is_admin = true,
                is_privileged = true,
                updated_at = now()
            """
        ).bindparams(
            sa.bindparam("id", DEFAULT_ADMIN_ID, type_=postgresql.UUID()),
            sa.bindparam("email", DEFAULT_ADMIN_EMAIL),
            sa.bindparam("password_hash", DEFAULT_ADMIN_PASSWORD_HASH),
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM users WHERE id = :id AND email = :email").bindparams(
            sa.bindparam("id", DEFAULT_ADMIN_ID, type_=postgresql.UUID()),
            sa.bindparam("email", DEFAULT_ADMIN_EMAIL),
        )
    )
