"""security incident workflow fields

Revision ID: 20260628_0028
Revises: 20260628_0027
Create Date: 2026-06-28 22:10:00

Sprint 6 T-275: `/admin/incidents` CPO review, subject notification, and
KISA/PIPC 72h report evidence.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260628_0028"
down_revision: str | None = "20260628_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_STATUS_CHECK = "status IN ('detected', 'triage', 'notification_decision', 'reported', 'closed')"
OLD_STATUS_CHECK = "status IN ('open', 'acknowledged', 'resolved', 'false_positive')"


def upgrade() -> None:
    op.drop_constraint(
        "ck_security_incidents_status_allowed",
        "security_incidents",
        schema="app",
        type_="check",
    )
    op.alter_column(
        "security_incidents",
        "status",
        schema="app",
        type_=sa.String(length=32),
        existing_type=sa.String(length=24),
        server_default="detected",
        existing_nullable=False,
    )
    op.execute(
        """
        UPDATE app.security_incidents
        SET status = CASE status
          WHEN 'open' THEN 'detected'
          WHEN 'acknowledged' THEN 'triage'
          WHEN 'resolved' THEN 'closed'
          WHEN 'false_positive' THEN 'closed'
          ELSE status
        END
        """
    )
    op.create_check_constraint(
        "ck_security_incidents_status_allowed",
        "security_incidents",
        NEW_STATUS_CHECK,
        schema="app",
    )

    op.add_column(
        "security_incidents",
        sa.Column("cpo_review_due_at", sa.DateTime(timezone=True), nullable=True),
        schema="app",
    )
    op.add_column(
        "security_incidents",
        sa.Column("external_report_due_at", sa.DateTime(timezone=True), nullable=True),
        schema="app",
    )
    op.add_column(
        "security_incidents",
        sa.Column("cpo_notified_at", sa.DateTime(timezone=True), nullable=True),
        schema="app",
    )
    op.add_column(
        "security_incidents",
        sa.Column("notification_decision_at", sa.DateTime(timezone=True), nullable=True),
        schema="app",
    )
    op.add_column(
        "security_incidents",
        sa.Column("notification_payload_hash", sa.String(length=64), nullable=True),
        schema="app",
    )
    op.add_column(
        "security_incidents",
        sa.Column("external_report_receipt_ref", sa.String(length=160), nullable=True),
        schema="app",
    )
    op.add_column(
        "security_incidents",
        sa.Column("evidence_attachment_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="app",
    )

    op.execute(
        """
        UPDATE app.security_incidents
        SET
          cpo_review_due_at = COALESCE(cpo_review_due_at, detected_at + interval '30 minutes'),
          external_report_due_at = COALESCE(external_report_due_at, detected_at + interval '72 hours'),
          notification_decision_at = CASE
            WHEN notification_required AND notification_decision_at IS NULL THEN acknowledged_at
            ELSE notification_decision_at
          END
        """
    )
    op.alter_column(
        "security_incidents",
        "cpo_review_due_at",
        schema="app",
        nullable=False,
        server_default=sa.text("now() + interval '30 minutes'"),
    )
    op.alter_column(
        "security_incidents",
        "external_report_due_at",
        schema="app",
        nullable=False,
        server_default=sa.text("now() + interval '72 hours'"),
    )
    op.create_index(
        "ix_security_incidents_external_report_due_at",
        "security_incidents",
        ["external_report_due_at"],
        schema="app",
        postgresql_where=sa.text("status <> 'closed'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_security_incidents_external_report_due_at",
        table_name="security_incidents",
        schema="app",
    )
    op.drop_constraint(
        "ck_security_incidents_status_allowed",
        "security_incidents",
        schema="app",
        type_="check",
    )
    op.execute(
        """
        UPDATE app.security_incidents
        SET status = CASE status
          WHEN 'detected' THEN 'open'
          WHEN 'triage' THEN 'acknowledged'
          WHEN 'notification_decision' THEN 'acknowledged'
          WHEN 'reported' THEN 'acknowledged'
          WHEN 'closed' THEN 'resolved'
          ELSE status
        END
        """
    )
    op.alter_column(
        "security_incidents",
        "status",
        schema="app",
        type_=sa.String(length=24),
        existing_type=sa.String(length=32),
        server_default="open",
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_security_incidents_status_allowed",
        "security_incidents",
        OLD_STATUS_CHECK,
        schema="app",
    )
    op.drop_column("security_incidents", "evidence_attachment_id", schema="app")
    op.drop_column("security_incidents", "external_report_receipt_ref", schema="app")
    op.drop_column("security_incidents", "notification_payload_hash", schema="app")
    op.drop_column("security_incidents", "notification_decision_at", schema="app")
    op.drop_column("security_incidents", "cpo_notified_at", schema="app")
    op.drop_column("security_incidents", "external_report_due_at", schema="app")
    op.drop_column("security_incidents", "cpo_review_due_at", schema="app")
