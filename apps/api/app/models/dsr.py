"""`app.dsr_requests` — PIPA data subject request workflow."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class DsrRequest(Base, TimestampMixin):
    """Data subject access/correction/delete/suspend request evidence row."""

    __tablename__ = "dsr_requests"
    __table_args__ = (
        CheckConstraint(
            "request_type IN ('access', 'correction', 'delete', 'suspend')",
            name="request_type_allowed",
        ),
        CheckConstraint(
            "status IN ('received', 'identity_check', 'processing', "
            "'completed', 'rejected', 'withdrawn')",
            name="status_allowed",
        ),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="SET NULL"),
    )
    request_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="received")
    request_summary: Mapped[str] = mapped_column(String(500), nullable=False)
    request_details: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    identity_proof_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    requester_email_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    requester_email_masked: Mapped[str] = mapped_column(String(320), nullable=False)
    assigned_cpo_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="SET NULL"),
    )
    result_notice_email_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.email_queue.email_id", ondelete="SET NULL"),
    )
    evidence_attachment_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now() + interval '10 days'"),
    )
    identity_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text())
    result_summary: Mapped[str | None] = mapped_column(Text())
    result_notice_hash: Mapped[str | None] = mapped_column(String(64))
    export_manifest: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    partial_response: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
