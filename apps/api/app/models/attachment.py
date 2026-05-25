"""`app.plan_poi_attachments` — 단일 테이블 4 대상."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class PlanPoiAttachment(Base, TimestampMixin):
    """trip / trip_poi / notice_plan / notice_poi 중 정확히 하나."""

    __tablename__ = "plan_poi_attachments"

    attachment_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.trips.trip_id", ondelete="CASCADE"),
    )
    trip_poi_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.trip_day_pois.attachment_id", ondelete="CASCADE"),
    )
    notice_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.notice_plans.notice_plan_id", ondelete="CASCADE"),
    )
    notice_poi_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.notice_pois.notice_poi_id", ondelete="CASCADE"),
    )
    source_attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.plan_poi_attachments.attachment_id", ondelete="SET NULL"),
    )
    bucket: Mapped[str] = mapped_column(String(80), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    public_url: Mapped[str | None] = mapped_column(Text())
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(40), nullable=False, server_default="attachment")
    description: Mapped[str | None] = mapped_column(Text())
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
