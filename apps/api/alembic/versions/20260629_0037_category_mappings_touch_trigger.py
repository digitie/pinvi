"""category_mappings updated_at touch trigger

Revision ID: 20260629_0037
Revises: 20260629_0036
Create Date: 2026-06-29 10:30:00

T-264 후속: `app.category_mappings`에 `trg_*_touch_updated_at` 트리거를 추가한다.
ORM PATCH는 `TimestampMixin` `onupdate`로 `updated_at`을 갱신하지만, ADR-052
후속 bulk-import 등 non-ORM/raw-SQL UPDATE는 갱신되지 않아 docs/postgres-schema.md
§5.4가 문서화한 스키마와 drift가 생긴다. 다른 16개 테이블과 동일한 패턴으로 정렬.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260629_0037"
down_revision: str | None = "20260629_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TRIGGER trg_category_mappings_touch_updated_at "
        "BEFORE UPDATE ON app.category_mappings "
        "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_category_mappings_touch_updated_at ON app.category_mappings"
    )
