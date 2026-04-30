"""add user registration profile and email verification tokens

Revision ID: 20260427_0016
Revises: 20260427_0015
Create Date: 2026-04-27 23:58:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260427_0016"
down_revision: str | None = "20260427_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True)))
    op.add_column(
        "users",
        sa.Column(
            "account_status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "system_role",
            sa.String(length=32),
            nullable=False,
            server_default="planner",
        ),
    )
    op.add_column("users", sa.Column("nickname", sa.String(length=80)))
    op.add_column("users", sa.Column("name", sa.String(length=80)))
    op.add_column("users", sa.Column("birth_year_month", sa.String(length=6)))
    op.add_column("users", sa.Column("gender", sa.String(length=32)))
    op.add_column("users", sa.Column("residence_sigungu_code", sa.String(length=10)))
    op.add_column("users", sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True)))

    op.execute(
        sa.text(
            """
            UPDATE users
            SET
                account_status = CASE WHEN is_active THEN 'active' ELSE 'disabled' END,
                system_role = CASE WHEN is_admin THEN 'admin' ELSE 'planner' END,
                nickname = COALESCE(display_name, split_part(email, '@', 1)),
                name = COALESCE(display_name, split_part(email, '@', 1)),
                email_verified_at = CASE WHEN is_active THEN now() ELSE NULL END
            """
        )
    )

    op.create_check_constraint(
        "ck_users_account_status",
        "users",
        "account_status IN "
        "('pending_email_verification', 'invited', 'active', 'disabled', 'deleted')",
    )
    op.create_check_constraint(
        "ck_users_system_role",
        "users",
        "system_role IN ('admin', 'planner', 'participant')",
    )
    op.create_check_constraint(
        "ck_users_birth_year_month_format",
        "users",
        "birth_year_month IS NULL OR birth_year_month ~ '^[0-9]{6}$'",
    )
    op.create_check_constraint(
        "ck_users_gender",
        "users",
        "gender IS NULL OR gender IN ('female', 'male', 'non_binary', 'no_answer')",
    )
    op.create_foreign_key(
        "fk_users_residence_sigungu_code",
        "users",
        "address_code_standard",
        ["residence_sigungu_code"],
        ["legal_dong_code"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_users_created_by_user_id",
        "users",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_account_status", "users", ["account_status"])
    op.create_index("ix_users_system_role", "users", ["system_role"])
    op.create_index("ix_users_residence_sigungu_code", "users", ["residence_sigungu_code"])
    op.create_index("ix_users_created_by_user_id", "users", ["created_by_user_id"])

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('register', 'invite_accept', 'email_change')",
            name="ck_email_verification_tokens_purpose",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_email_verification_tokens_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_email_verification_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_email_verification_tokens_token_hash"),
    )
    op.create_index(
        "ix_email_verification_tokens_user_id",
        "email_verification_tokens",
        ["user_id"],
    )
    op.create_index(
        "ix_email_verification_tokens_expires_at",
        "email_verification_tokens",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_email_verification_tokens_expires_at", table_name="email_verification_tokens")
    op.drop_index("ix_email_verification_tokens_user_id", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")

    op.drop_index("ix_users_created_by_user_id", table_name="users")
    op.drop_index("ix_users_residence_sigungu_code", table_name="users")
    op.drop_index("ix_users_system_role", table_name="users")
    op.drop_index("ix_users_account_status", table_name="users")
    op.drop_constraint("fk_users_created_by_user_id", "users", type_="foreignkey")
    op.drop_constraint("fk_users_residence_sigungu_code", "users", type_="foreignkey")
    op.drop_constraint("ck_users_gender", "users", type_="check")
    op.drop_constraint("ck_users_birth_year_month_format", "users", type_="check")
    op.drop_constraint("ck_users_system_role", "users", type_="check")
    op.drop_constraint("ck_users_account_status", "users", type_="check")

    op.drop_column("users", "last_login_at")
    op.drop_column("users", "created_by_user_id")
    op.drop_column("users", "residence_sigungu_code")
    op.drop_column("users", "gender")
    op.drop_column("users", "birth_year_month")
    op.drop_column("users", "name")
    op.drop_column("users", "nickname")
    op.drop_column("users", "system_role")
    op.drop_column("users", "account_status")
    op.drop_column("users", "email_verified_at")
