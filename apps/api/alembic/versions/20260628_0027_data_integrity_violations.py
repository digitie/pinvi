"""data integrity violations

Revision ID: 20260628_0027
Revises: 20260627_0026
Create Date: 2026-06-28 14:50:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260628_0027"
down_revision: str | None = "20260627_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_integrity_violations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("rule_key", sa.String(length=120), nullable=False),
        sa.Column("entity_kind", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), server_default="warning", nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_fixable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'error', 'critical')",
            name="ck_data_integrity_violations_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved', 'ignored')",
            name="ck_data_integrity_violations_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_integrity_violations"),
        schema="app",
    )
    op.create_index(
        "ix_data_integrity_violations_status_severity_detected",
        "data_integrity_violations",
        ["status", "severity", "detected_at"],
        schema="app",
    )
    op.create_index(
        "ix_data_integrity_violations_entity",
        "data_integrity_violations",
        ["entity_kind", "entity_id"],
        schema="app",
    )
    op.create_index(
        "uq_data_integrity_violations_active_rule_entity",
        "data_integrity_violations",
        ["rule_key", "entity_kind", "entity_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("status IN ('open', 'acknowledged') AND resolved_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_data_integrity_violations_active_rule_entity",
        table_name="data_integrity_violations",
        schema="app",
    )
    op.drop_index(
        "ix_data_integrity_violations_entity",
        table_name="data_integrity_violations",
        schema="app",
    )
    op.drop_index(
        "ix_data_integrity_violations_status_severity_detected",
        table_name="data_integrity_violations",
        schema="app",
    )
    op.drop_table("data_integrity_violations", schema="app")
