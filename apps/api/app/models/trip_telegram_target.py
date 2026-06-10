"""`app.trip_telegram_targets` — trip ↔ Telegram 대상 연결 — `docs/integrations/telegram.md` §2.2.

trip은 user 소유 target을 **참조**만 한다(복사 X). trip별 연결 수는 ≤3 (§6.5 — 응용
레이어에서 enforce). target/trip soft delete 시 FK CASCADE로 함께 정리된다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TripTelegramTarget(Base):
    __tablename__ = "trip_telegram_targets"

    trip_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.trips.trip_id", ondelete="CASCADE"),
        primary_key=True,
    )
    telegram_target_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.telegram_targets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
