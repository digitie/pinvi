"""feature suggestion dedup includes type + target_feature_id

Revision ID: 20260609_0015
Revises: 20260609_0014
Create Date: 2026-06-09 12:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260609_0015"
down_revision: str | None = "20260609_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # new_place와 correction/closure(기존 feature 참조)는 같은 name/좌표여도 별개 제안이다.
    # dedup 유니크 키에 type + target_feature_id를 포함해 잘못된 병합을 막는다.
    op.execute("DROP INDEX IF EXISTS app.ux_feature_suggestions_user_pending_dedup")
    op.execute(
        """
        CREATE UNIQUE INDEX ux_feature_suggestions_user_pending_dedup
        ON app.feature_suggestions (
            requester_user_id, type, kind, lower(name), lng, lat,
            COALESCE(target_feature_id, '')
        )
        WHERE status = 'pending'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS app.ux_feature_suggestions_user_pending_dedup")
    op.execute(
        """
        CREATE UNIQUE INDEX ux_feature_suggestions_user_pending_dedup
        ON app.feature_suggestions (requester_user_id, kind, lower(name), lng, lat)
        WHERE status = 'pending'
        """
    )
