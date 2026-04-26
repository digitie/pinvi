from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, kst_now


class EtlRunLog(TimestampMixin, Base):
    __tablename__ = "etl_run_logs"
    __table_args__ = (
        Index("ix_etl_run_logs_dataset_key", "dataset_key"),
        Index("ix_etl_run_logs_dataset_run_key", "dataset_key", "run_key"),
        Index("ix_etl_run_logs_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    dataset_key: Mapped[str] = mapped_column(String(80), nullable=False)
    run_key: Mapped[str | None] = mapped_column(String(80))
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_date: Mapped[date | None] = mapped_column(Date)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_interval_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    error_type: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)
    log_file_path: Mapped[str | None] = mapped_column(String(500))
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class AdminNotification(TimestampMixin, Base):
    __tablename__ = "admin_notifications"
    __table_args__ = (
        Index("ix_admin_notifications_scope", "recipient_scope"),
        Index("ix_admin_notifications_unread", "is_read"),
        Index("ix_admin_notifications_dataset_key", "dataset_key"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    recipient_scope: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    dataset_key: Mapped[str | None] = mapped_column(String(80))
    etl_run_log_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("etl_run_logs.id", name="fk_admin_notifications_etl_run", ondelete="SET NULL"),
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class TelegramSystemNotificationOutbox(TimestampMixin, Base):
    __tablename__ = "telegram_system_notification_outbox"
    __table_args__ = (
        Index("ix_tg_sys_outbox_status", "status"),
        Index("ix_tg_sys_outbox_dataset_key", "dataset_key"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    recipient_scope: Mapped[str] = mapped_column(String(40), nullable=False)
    dataset_key: Mapped[str | None] = mapped_column(String(80))
    etl_run_log_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("etl_run_logs.id", name="fk_tg_sys_outbox_etl_run", ondelete="SET NULL"),
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
