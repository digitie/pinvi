"""#636/#638: 알림 동의·발생키·대상별 재개 지점."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "20261105_0104"
down_revision: str | None = "20261105_0103"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRIOR = "contract_version = 'pinvi-cache-target-final-boundary/v1' AND status = 'succeeded' AND (schema_revision = '20260824_0101' OR schema_revision = '20260917_0102' OR schema_revision = '20261105_0103')"
_CHECK = _PRIOR[:-1] + " OR schema_revision = '20261105_0104')"


def _boundary(check: str) -> None:
    op.drop_constraint(
        op.f("ck_ktm_ct_boundary_contract"),
        "ktm_cache_target_boundary_audits",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_ktm_ct_boundary_contract"), "ktm_cache_target_boundary_audits", check, schema="app"
    )


def upgrade() -> None:
    for table in ("telegram_targets", "trip_telegram_targets"):
        op.add_column(
            table,
            sa.Column(
                "generation",
                pg.UUID(as_uuid=True),
                nullable=False,
                server_default=sa.text("gen_random_uuid()"),
            ),
            schema="app",
        )
    op.create_table(
        "telegram_notification_preferences",
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("app.users.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("daily_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("weekly_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("send_time", sa.String(5), nullable=False, server_default="08:00"),
        sa.Column("weekly_day", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "weekly_target_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("app.telegram_targets.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "generation",
            pg.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.CheckConstraint(
            "send_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'", name="telegram_send_time"
        ),
        sa.CheckConstraint("weekly_day BETWEEN 0 AND 6", name="telegram_weekly_day"),
        schema="app",
    )
    op.create_table(
        "telegram_notifications",
        sa.Column(
            "id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("app.users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("occurrence_key", sa.String(240), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("trip_ids", pg.JSONB(), nullable=False),
        sa.Column("chunks", pg.JSONB(), nullable=False),
        sa.Column(
            "schedule_snapshot", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("consent_generation", pg.UUID(as_uuid=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "occurrence_key"),
        schema="app",
    )
    op.create_table(
        "telegram_notification_deliveries",
        sa.Column(
            "id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "notification_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("app.telegram_notifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("app.telegram_targets.id", ondelete="SET NULL"),
        ),
        sa.Column("target_generation", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("link_generation", pg.UUID(as_uuid=True)),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("next_chunk", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.UniqueConstraint("notification_id", "target_id"),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'skipped', 'failed')", name="telegram_delivery_status"
        ),
        sa.CheckConstraint("next_chunk >= 0 AND attempts >= 0", name="telegram_delivery_progress"),
        schema="app",
    )
    op.create_index(
        "ix_telegram_notification_deliveries_scheduled_at",
        "telegram_notification_deliveries",
        ["scheduled_at"],
        schema="app",
    )
    _boundary(_CHECK)


def downgrade() -> None:
    _boundary(_PRIOR)
    op.drop_table("telegram_notification_deliveries", schema="app")
    op.drop_table("telegram_notifications", schema="app")
    op.drop_table("telegram_notification_preferences", schema="app")
    for table in ("trip_telegram_targets", "telegram_targets"):
        op.drop_column(table, "generation", schema="app")
