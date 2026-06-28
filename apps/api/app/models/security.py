"""Security incident tracking for PIPA breach response."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class SecurityIncident(Base, TimestampMixin):
    """`app.security_incidents` — PIPA incident review and notification state."""

    __tablename__ = "security_incidents"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="severity_allowed",
        ),
        CheckConstraint(
            "status IN ('detected', 'triage', 'notification_decision', 'reported', 'closed')",
            name="status_allowed",
        ),
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    incident_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="detected")
    source: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(String(240), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    affected_user_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    notification_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    assigned_cpo_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="SET NULL"),
    )
    request_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    cpo_review_due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now() + interval '30 minutes'"),
    )
    external_report_due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now() + interval '72 hours'"),
    )
    cpo_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notification_decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kisa_reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notification_payload_hash: Mapped[str | None] = mapped_column(String(64))
    external_report_receipt_ref: Mapped[str | None] = mapped_column(String(160))
    evidence_attachment_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
