"""첨부 업로드 예약과 영구 폐기 객체 큐."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AttachmentUploadIntent(Base):
    __tablename__ = "attachment_upload_intents"

    bucket: Mapped[str] = mapped_column(String(80), primary_key=True)
    storage_key: Mapped[str] = mapped_column(String(1024), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app.users.user_id", ondelete="RESTRICT"), index=True
    )
    byte_size: Mapped[int] = mapped_column(BigInteger)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    write_token: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    write_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_bytes: Mapped[int | None] = mapped_column(BigInteger)
    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AttachmentGcObject(Base):
    __tablename__ = "attachment_gc_objects"

    bucket: Mapped[str] = mapped_column(String(80), primary_key=True)
    storage_key: Mapped[str] = mapped_column(String(1024), primary_key=True)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verification_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(Text)
