"""`app.trip_comments` — trip 협업 댓글."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class TripComment(Base, TimestampMixin):
    __tablename__ = "trip_comments"

    comment_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.trips.trip_id", ondelete="CASCADE"),
        nullable=False,
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="SET NULL"),
    )
    body: Mapped[str] = mapped_column(Text(), nullable=False)
    target_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="trip",
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    day_index: Mapped[int | None] = mapped_column(Integer)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
