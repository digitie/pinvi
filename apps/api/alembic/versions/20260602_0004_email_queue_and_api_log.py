"""email_queue + api_call_log + user_oauth_identities + oauth_login_states

Revision ID: 20260602_0004
Revises: 20260602_0003
Create Date: 2026-06-02 12:00:00

`docs/integrations/resend.md` §3 / `docs/integrations/social-login.md` §4 /
`docs/data-model.md` §8.3, §8.4.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260602_0004"
down_revision: str | None = "20260602_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ─────────────────────────────────────────────
    # email_queue — Resend outbox
    # ─────────────────────────────────────────────
    op.create_table(
        "email_queue",
        sa.Column(
            "email_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("to_email", sa.String(length=320), nullable=False),
        sa.Column("template", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("resend_id", sa.String(length=128)),
        sa.Column("bounce_type", sa.String(length=16)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("bounced_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("email_id", name="pk_email_queue"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.user_id"],
            name="fk_email_queue_user_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'delivered', 'bounced', 'complained', 'failed')",
            name="ck_email_queue_status",
        ),
        sa.CheckConstraint(
            "bounce_type IS NULL OR bounce_type IN ('hard', 'soft')",
            name="ck_email_queue_bounce_type",
        ),
        schema="app",
    )
    op.create_index(
        "ix_email_queue_pending",
        "email_queue",
        ["scheduled_at"],
        schema="app",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_email_queue_to_email",
        "email_queue",
        ["to_email"],
        schema="app",
    )
    op.execute(
        "CREATE TRIGGER trg_email_queue_touch_updated_at "
        "BEFORE UPDATE ON app.email_queue FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )

    # ─────────────────────────────────────────────
    # api_call_log — 외부 provider 호출 추적
    # ─────────────────────────────────────────────
    op.create_table(
        "api_call_log",
        sa.Column("log_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("error_class", sa.String(length=64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("request_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("log_id", name="pk_api_call_log"),
        schema="app",
    )
    op.execute("CREATE INDEX ix_api_call_log_occurred ON app.api_call_log USING brin (occurred_at)")
    op.create_index(
        "ix_api_call_log_provider_time",
        "api_call_log",
        ["provider", sa.text("occurred_at DESC")],
        schema="app",
    )

    # ─────────────────────────────────────────────
    # user_oauth_identities — Google / Naver / Kakao
    # ─────────────────────────────────────────────
    op.create_table(
        "user_oauth_identities",
        sa.Column(
            "identity_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("provider_email", sa.String(length=320)),
        sa.Column("provider_email_verified", sa.Boolean()),
        sa.Column("display_name_snapshot", sa.String(length=120)),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("identity_id", name="pk_user_oauth_identities"),
        sa.UniqueConstraint(
            "provider",
            "provider_user_id",
            name="uq_user_oauth_identities_provider_subject",
        ),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            name="uq_user_oauth_identities_user_provider",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.user_id"],
            name="fk_user_oauth_identities_user_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "provider IN ('google', 'naver', 'kakao')",
            name="ck_user_oauth_identities_provider",
        ),
        schema="app",
    )

    # ─────────────────────────────────────────────
    # oauth_login_states — state / nonce / PKCE hash (TTL 10분)
    # ─────────────────────────────────────────────
    op.create_table(
        "oauth_login_states",
        sa.Column("state_hash", sa.String(length=128), nullable=False),
        sa.Column("nonce_hash", sa.String(length=128)),
        sa.Column("pkce_code_verifier_hash", sa.String(length=128)),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="login"),
        sa.Column("return_to_path", sa.String(length=255)),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("state_hash", name="pk_oauth_login_states"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.user_id"],
            name="fk_oauth_login_states_user_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("mode IN ('login', 'link')", name="ck_oauth_login_states_mode"),
        sa.CheckConstraint(
            "provider IN ('google', 'naver', 'kakao')",
            name="ck_oauth_login_states_provider",
        ),
        schema="app",
    )
    op.create_index(
        "ix_oauth_login_states_active",
        "oauth_login_states",
        ["expires_at"],
        schema="app",
        postgresql_where=sa.text("consumed_at IS NULL"),
    )

    # users.password_hash nullable 전환 — provider-only 계정 허용
    # (이미 nullable이지만 명시적 ADR 트레일을 위해 빈 op)


def downgrade() -> None:
    op.drop_index("ix_oauth_login_states_active", table_name="oauth_login_states", schema="app")
    op.drop_table("oauth_login_states", schema="app")
    op.drop_table("user_oauth_identities", schema="app")
    op.drop_index("ix_api_call_log_provider_time", table_name="api_call_log", schema="app")
    op.execute("DROP INDEX IF EXISTS app.ix_api_call_log_occurred")
    op.drop_table("api_call_log", schema="app")
    op.execute("DROP TRIGGER IF EXISTS trg_email_queue_touch_updated_at ON app.email_queue")
    op.drop_index("ix_email_queue_to_email", table_name="email_queue", schema="app")
    op.drop_index("ix_email_queue_pending", table_name="email_queue", schema="app")
    op.drop_table("email_queue", schema="app")
