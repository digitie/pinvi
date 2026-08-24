"""동의/철회 이벤트 이력 테이블을 만든다 (T-326).

Revision ID: 20260824_0063
Revises: 20260824_0062
Create Date: 2026-08-24

`app.user_consents`는 type당 1행의 현재 상태만 담고, 재동의 시 같은 row가 in-place로 되살아나
철회 사실이 사라진다. `docs/legal/terms-of-service.md` 제4조가 이용자에게 "동의 이력은 시점·버전과
함께 기록된다"고 고지하므로 append 전용 이벤트 테이블로 그 진술을 참으로 만든다.

DDL과 백필을 분리한다(`docs/conventions/database.md`) — 백필은 다음 revision이 맡는다.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0063"
down_revision: str | None = "20260824_0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260824_0063'"
)
_PREV_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260824_0062'"
)


def _repin_boundary_contract(check: str) -> None:
    """head 마이그레이션마다 DB/service pin을 함께 전진시킨다(저장소 규약)."""
    op.drop_constraint(
        op.f("ck_ktm_ct_boundary_contract"),
        "ktm_cache_target_boundary_audits",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_ktm_ct_boundary_contract"),
        "ktm_cache_target_boundary_audits",
        check,
        schema="app",
    )


def upgrade() -> None:
    op.create_table(
        "user_consent_events",
        sa.Column(
            "event_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consent_type", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("event", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_user_consent_events")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.user_id"],
            name=op.f("fk_user_consent_events_user_id"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "consent_type IN ('tos', 'privacy', 'lbs_tos', 'location_collection', "
            "'demographic_use', 'marketing')",
            name=op.f("ck_user_consent_events_consent_type"),
        ),
        sa.CheckConstraint(
            "event IN ('agreed', 'withdrawn')",
            name=op.f("ck_user_consent_events_event"),
        ),
        sa.CheckConstraint(
            "source IN ('register', 'profile_complete', 'settings', 'backfill')",
            name=op.f("ck_user_consent_events_source"),
        ),
        schema="app",
    )
    op.create_index(
        "ix_user_consent_events_user_type_time",
        "user_consent_events",
        ["user_id", "consent_type", "occurred_at"],
        schema="app",
    )
    _repin_boundary_contract(_BOUNDARY_CONTRACT_CHECK)


def downgrade() -> None:
    op.drop_index(
        "ix_user_consent_events_user_type_time", table_name="user_consent_events", schema="app"
    )
    op.drop_table("user_consent_events", schema="app")
    _repin_boundary_contract(_PREV_BOUNDARY_CONTRACT_CHECK)
