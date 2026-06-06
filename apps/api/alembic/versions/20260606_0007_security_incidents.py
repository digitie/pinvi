"""security incidents table

Revision ID: 20260606_0007
Revises: 20260605_0006
Create Date: 2026-06-06 22:30:00

`docs/compliance/pipa.md` §3 breach notification trigger foundation.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260606_0007"
down_revision: str | None = "20260605_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "security_incidents",
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("incident_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("source", sa.String(length=64)),
        sa.Column("summary", sa.String(length=240), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("affected_user_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "notification_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("assigned_cpo_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("request_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("notified_at", sa.DateTime(timezone=True)),
        sa.Column("kisa_reported_at", sa.DateTime(timezone=True)),
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
        sa.PrimaryKeyConstraint("incident_id", name="pk_security_incidents"),
        sa.ForeignKeyConstraint(
            ["assigned_cpo_user_id"],
            ["app.users.user_id"],
            name="fk_security_incidents_assigned_cpo_user_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_security_incidents_severity_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved', 'false_positive')",
            name="ck_security_incidents_status_allowed",
        ),
        schema="app",
    )
    op.create_index(
        "ix_security_incidents_status_detected_at",
        "security_incidents",
        ["status", "detected_at"],
        schema="app",
    )
    op.create_index(
        "ix_security_incidents_severity_detected_at",
        "security_incidents",
        ["severity", "detected_at"],
        schema="app",
    )
    op.execute(
        "CREATE TRIGGER trg_security_incidents_touch_updated_at "
        "BEFORE UPDATE ON app.security_incidents "
        "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_security_incidents_touch_updated_at ON app.security_incidents"
    )
    op.drop_index(
        "ix_security_incidents_severity_detected_at",
        table_name="security_incidents",
        schema="app",
    )
    op.drop_index(
        "ix_security_incidents_status_detected_at",
        table_name="security_incidents",
        schema="app",
    )
    op.drop_table("security_incidents", schema="app")
