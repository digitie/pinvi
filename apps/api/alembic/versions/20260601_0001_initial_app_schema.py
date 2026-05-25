"""initial app schema — users / sessions / consents / email verifications

Revision ID: 20260601_0001
Revises:
Create Date: 2026-06-01 09:00:00

`docs/postgres-schema.md` + `docs/data-model.md` §2.1 ~ §2.4 mirror.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260601_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ─────────────────────────────────────────────
    # schema + extension
    # ─────────────────────────────────────────────
    op.execute("CREATE SCHEMA IF NOT EXISTS app")
    op.execute("CREATE SCHEMA IF NOT EXISTS x_extension")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto SCHEMA x_extension")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA x_extension")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext SCHEMA x_extension")

    # search_path 가 검색 가능하도록 — 운영 환경은 별도 ALTER ROLE 권장.
    op.execute("SET search_path TO app, x_extension, public")

    # ─────────────────────────────────────────────
    # touch_updated_at trigger 함수
    # ─────────────────────────────────────────────
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.touch_updated_at()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          NEW.updated_at := now();
          RETURN NEW;
        END;
        $$;
        """
    )

    # ─────────────────────────────────────────────
    # users
    # ─────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255)),
        sa.Column("nickname", sa.String(length=80)),
        sa.Column("avatar_url", sa.String(length=1024)),
        sa.Column("avatar_kind", sa.String(length=16), nullable=False, server_default="default"),
        sa.Column("gender", sa.String(length=16)),
        sa.Column("birth_year_month", sa.String(length=6)),
        sa.Column("residence_sigungu_code", sa.String(length=5)),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending_verification",
        ),
        sa.Column(
            "roles",
            postgresql.ARRAY(sa.String(length=16)),
            nullable=False,
            server_default=sa.text("ARRAY['user']::varchar[]"),
        ),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column(
            "email_status",
            sa.String(length=16),
            nullable=False,
            server_default="active",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint(
            "status IN ('pending_verification', 'pending_profile', 'active', 'disabled', 'deleted')",
            name="ck_users_status",
        ),
        sa.CheckConstraint(
            "email_status IN ('active', 'bounced', 'complained')",
            name="ck_users_email_status",
        ),
        sa.CheckConstraint(
            "gender IS NULL OR gender IN ('female', 'male', 'non_binary', 'no_answer')",
            name="ck_users_gender",
        ),
        schema="app",
    )
    op.create_index("ix_users_status", "users", ["status"], schema="app")
    op.execute(
        "CREATE TRIGGER trg_users_touch_updated_at "
        "BEFORE UPDATE ON app.users FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )

    # ─────────────────────────────────────────────
    # user_sessions
    # ─────────────────────────────────────────────
    op.create_table(
        "user_sessions",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("user_agent", sa.String(length=512)),
        sa.Column("ip_address", postgresql.INET()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("session_id", name="pk_user_sessions"),
        sa.UniqueConstraint("session_token_hash", name="uq_user_sessions_session_token_hash"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.user_id"],
            name="fk_user_sessions_user_id",
            ondelete="CASCADE",
        ),
        schema="app",
    )
    op.create_index(
        "ix_user_sessions_user_active",
        "user_sessions",
        ["user_id", "expires_at"],
        schema="app",
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    # ─────────────────────────────────────────────
    # user_email_verifications
    # ─────────────────────────────────────────────
    op.create_table(
        "user_email_verifications",
        sa.Column(
            "verification_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False, server_default="signup"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("verification_id", name="pk_user_email_verifications"),
        sa.UniqueConstraint("token_hash", name="uq_user_email_verifications_token_hash"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.user_id"],
            name="fk_user_email_verifications_user_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "purpose IN ('signup', 'password_reset', 'email_change')",
            name="ck_user_email_verifications_purpose",
        ),
        schema="app",
    )
    op.create_index(
        "ix_user_email_verifications_user_id",
        "user_email_verifications",
        ["user_id"],
        schema="app",
    )

    # ─────────────────────────────────────────────
    # user_consents (4 분리 동의 + 선택 동의)
    # ─────────────────────────────────────────────
    op.create_table(
        "user_consents",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consent_type", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("agreed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id", "consent_type", "version", name="pk_user_consents"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.user_id"],
            name="fk_user_consents_user_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "consent_type IN ('tos', 'privacy', 'lbs_tos', 'location_collection', "
            "'demographic_use', 'marketing')",
            name="ck_user_consents_consent_type",
        ),
        schema="app",
    )


def downgrade() -> None:
    op.drop_table("user_consents", schema="app")
    op.drop_index(
        "ix_user_email_verifications_user_id",
        table_name="user_email_verifications",
        schema="app",
    )
    op.drop_table("user_email_verifications", schema="app")
    op.drop_index("ix_user_sessions_user_active", table_name="user_sessions", schema="app")
    op.drop_table("user_sessions", schema="app")
    op.execute("DROP TRIGGER IF EXISTS trg_users_touch_updated_at ON app.users")
    op.drop_index("ix_users_status", table_name="users", schema="app")
    op.drop_table("users", schema="app")
    op.execute("DROP FUNCTION IF EXISTS app.touch_updated_at()")
