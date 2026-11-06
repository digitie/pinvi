"""일정 알림 발생과 대상별 chunk 진행 상태. 기존 시스템 outbox와 별도 큐다."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TelegramPreferences(Base):
    __tablename__ = "telegram_notification_preferences"
    __table_args__ = (
        CheckConstraint("send_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'", name="telegram_send_time"),
        CheckConstraint("weekly_day BETWEEN 0 AND 6", name="telegram_weekly_day"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app.users.user_id", ondelete="CASCADE"), primary_key=True
    )
    daily_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    weekly_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    weather_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    weather_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    send_time: Mapped[str] = mapped_column(String(5), nullable=False, server_default="08:00")
    weekly_day: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    weekly_target_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app.telegram_targets.id", ondelete="SET NULL")
    )
    generation: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, server_default=text("gen_random_uuid()")
    )
    # planner 순환 cursor. 시간 예산을 넘긴 tick 뒤에도 오래 기다린 사용자부터 처리한다.
    # 동의(generation)와 무관한 운영 상태라 preferences_body 비교에 넣지 않는다.
    last_planned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TelegramNotification(Base):
    __tablename__ = "telegram_notifications"
    __table_args__ = (UniqueConstraint("user_id", "occurrence_key"),)
    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app.users.user_id", ondelete="CASCADE"), nullable=False
    )
    occurrence_key: Mapped[str] = mapped_column(String(240), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    trip_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    chunks: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    schedule_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    consent_generation: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # 보존 기한 뒤 본문(chunks)·스냅샷을 지운 시각. 발생키·상태·시각은 중복 방지와 감사용으로 남긴다.
    body_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TelegramDelivery(Base):
    __tablename__ = "telegram_notification_deliveries"
    __table_args__ = (
        UniqueConstraint("notification_id", "target_id"),
        CheckConstraint(
            "status IN ('pending', 'sent', 'skipped', 'failed')", name="telegram_delivery_status"
        ),
        CheckConstraint("next_chunk >= 0 AND attempts >= 0", name="telegram_delivery_progress"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    notification_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.telegram_notifications.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app.telegram_targets.id", ondelete="SET NULL")
    )
    target_generation: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    link_generation: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    next_chunk: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    # Telegram 호출 중 lease. scheduled_at이 lease 만료 시각이며, 결과 기록은 같은 token일 때만 한다.
    claim_token: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))


class TelegramWeatherObservation(Base):
    """Trip 잠금 아래만 변경한다. 취소와 모호성은 관측 순서와 무관하게 유지한다."""

    __tablename__ = "telegram_weather_observations"
    trip_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app.trips.trip_id", ondelete="CASCADE"), primary_key=True
    )
    announcement_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    cancelled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ambiguous: Mapped[bool] = mapped_column(Boolean, nullable=False)
    generation: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, server_default=text("gen_random_uuid()")
    )
