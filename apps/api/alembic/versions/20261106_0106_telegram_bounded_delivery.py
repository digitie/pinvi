"""Telegram planner 순환 cursor·전송 claim token·본문 보존 기한.

모두 nullable 열 추가와 부분 index라 기존 행·이전 코드와 함께 동작한다(forward-safe).
- telegram_notification_preferences.last_planned_at: 시간 예산 안에서 오래 기다린 사용자부터 처리
- telegram_notification_deliveries.claim_token: Trip 잠금 없이 Telegram을 호출하는 동안의 짧은 lease
- telegram_notifications.body_purged_at: 보존 기한이 지난 본문을 지운 시각(발생키·상태는 남긴다)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "20261106_0106"
down_revision: str | None = "20261105_0105"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRIOR = "contract_version = 'pinvi-cache-target-final-boundary/v1' AND status = 'succeeded' AND (schema_revision = '20260824_0101' OR schema_revision = '20260917_0102' OR schema_revision = '20261105_0103' OR schema_revision = '20261105_0104' OR schema_revision = '20261105_0105')"
_CHECK = _PRIOR[:-1] + " OR schema_revision = '20261106_0106')"


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
    op.add_column(
        "telegram_notification_preferences",
        sa.Column("last_planned_at", sa.DateTime(timezone=True)),
        schema="app",
    )
    op.add_column(
        "telegram_notification_deliveries",
        sa.Column("claim_token", pg.UUID(as_uuid=True)),
        schema="app",
    )
    op.add_column(
        "telegram_notifications",
        sa.Column("body_purged_at", sa.DateTime(timezone=True)),
        schema="app",
    )
    op.create_index(
        "ix_telegram_notifications_body_retained",
        "telegram_notifications",
        ["created_at"],
        schema="app",
        postgresql_where=sa.text("body_purged_at IS NULL"),
    )
    _boundary(_CHECK)


def downgrade() -> None:
    op.execute(
        "DELETE FROM app.ktm_cache_target_boundary_audits WHERE schema_revision = '20261106_0106'"
    )
    _boundary(_PRIOR)
    op.drop_index(
        "ix_telegram_notifications_body_retained",
        table_name="telegram_notifications",
        schema="app",
    )
    op.drop_column("telegram_notifications", "body_purged_at", schema="app")
    op.drop_column("telegram_notification_deliveries", "claim_token", schema="app")
    op.drop_column("telegram_notification_preferences", "last_planned_at", schema="app")
