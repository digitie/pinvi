"""`app.data_integrity_violations` — Pinvi app-owned integrity source."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class DataIntegrityViolation(Base, TimestampMixin):
    __tablename__ = "data_integrity_violations"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('info', 'warning', 'error', 'critical')",
            name="ck_data_integrity_violations_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved', 'ignored')",
            name="ck_data_integrity_violations_status",
        ),
        Index(
            "ix_data_integrity_violations_status_severity_detected",
            "status",
            "severity",
            "detected_at",
        ),
        Index("ix_data_integrity_violations_entity", "entity_kind", "entity_id"),
        Index(
            "uq_data_integrity_violations_active_rule_entity",
            "rule_key",
            "entity_kind",
            "entity_id",
            unique=True,
            postgresql_where=text("status IN ('open', 'acknowledged') AND resolved_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_key: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(Text(), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, server_default="warning")
    message: Mapped[str] = mapped_column(Text(), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auto_fixable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
