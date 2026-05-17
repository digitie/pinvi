from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

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


class ProviderSyncState(TimestampMixin, Base):
    __tablename__ = "provider_sync_state"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'paused', 'failed')",
            name=conv("ck_provider_sync_state_status"),
        ),
        UniqueConstraint(
            "provider",
            "dataset_key",
            "sync_scope",
            name="uq_provider_sync_state_provider_dataset_scope",
        ),
        Index("ix_provider_sync_state_provider_dataset", "provider", "dataset_key"),
        Index("ix_provider_sync_state_status_next", "status", "next_run_after"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    dataset_key: Mapped[str] = mapped_column(String(120), nullable=False)
    sync_scope: Mapped[str] = mapped_column(String(160), nullable=False, default="global")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    cursor: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class AdminNotification(TimestampMixin, Base):
    __tablename__ = "admin_notifications"
    __table_args__ = (
        Index("ix_admin_notifications_scope", "recipient_scope"),
        Index("ix_admin_notifications_unread", "is_read"),
        Index("ix_admin_notifications_dataset_key", "dataset_key"),
        Index("ix_admin_notifications_etl_run_log_id", "etl_run_log_id"),
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
        Index("ix_tg_sys_outbox_etl_run_log_id", "etl_run_log_id"),
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


class ApiCallLog(Base):
    __tablename__ = "api_call_log"
    __table_args__ = (
        Index("ix_api_call_log_occurred_brin", "occurred_at", postgresql_using="brin"),
        Index("ix_api_call_log_provider_time", "provider", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )


class EmailQueue(Base):
    __tablename__ = "email_queue"
    __table_args__ = (
        CheckConstraint(
            "template IN ('verify', 'reset', 'invite', 'system')",
            name=conv("ck_email_queue_template"),
        ),
        CheckConstraint(
            "status IN ('queued', 'sending', 'sent', 'failed')",
            name=conv("ck_email_queue_status"),
        ),
        CheckConstraint("attempts >= 0", name=conv("ck_email_queue_attempts")),
        Index("ix_email_queue_status_queued", "status", "queued_at"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    to_email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"
    __table_args__ = (
        Index("ix_admin_audit_log_admin_time", "admin_user_id", "occurred_at"),
        Index("ix_admin_audit_log_target", "target_type", "target_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admin_user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", name="fk_admin_audit_log_admin_user", ondelete="RESTRICT"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[str | None] = mapped_column(Text)
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
