"""`app.content_reports` / `app.content_moderation_actions` — 신고·제재 원장."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class ContentReport(Base, TimestampMixin):
    """Trip/comment/attachment/share link 신고와 심사 상태."""

    __tablename__ = "content_reports"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('trip', 'comment', 'attachment', 'share_link')",
            name="target_type_allowed",
        ),
        CheckConstraint(
            "reason_code IN ('spam', 'harassment', 'privacy', 'illegal', 'safety', 'other')",
            name="reason_code_allowed",
        ),
        CheckConstraint(
            "status IN ('received', 'reviewing', 'hidden', 'taken_down', "
            "'rejected', 'appealed', 'restored')",
            name="status_allowed",
        ),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    target_trip_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.trips.trip_id", ondelete="SET NULL"),
    )
    target_owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="SET NULL"),
    )
    reporter_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="SET NULL"),
    )
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_text: Mapped[str] = mapped_column(Text(), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="received")
    target_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="SET NULL"),
    )
    resolution_summary: Mapped[str | None] = mapped_column(Text())
    appeal_summary: Mapped[str | None] = mapped_column(Text())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    appealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContentModerationAction(Base):
    """신고별 조치 이력. 사용자 appeal도 같은 action log에 남긴다."""

    __tablename__ = "content_moderation_actions"
    __table_args__ = (
        CheckConstraint(
            "action IN ('review', 'hide', 'takedown', 'restore', 'reject', 'appeal')",
            name="action_allowed",
        ),
    )

    action_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.content_reports.report_id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="SET NULL"),
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    action_reason: Mapped[str] = mapped_column(Text(), nullable=False)
    before_state: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    after_state: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
