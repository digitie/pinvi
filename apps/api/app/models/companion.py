"""`app.trip_companions` — 동반자."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class TripCompanion(Base, TimestampMixin):
    __tablename__ = "trip_companions"

    companion_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.trips.trip_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="SET NULL"),
    )
    invited_email: Mapped[str | None] = mapped_column(String(320))
    invited_nickname: Mapped[str | None] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(16), nullable=False, server_default="editor")
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
