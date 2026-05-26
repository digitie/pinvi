"""`app.trip_share_links` — 256bit 공유 토큰."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class TripShareLink(Base, TimestampMixin):
    __tablename__ = "trip_share_links"

    share_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.trips.trip_id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="view_only"
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
