"""`app.users` 모델."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, BigInteger, Boolean, DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    nickname: Mapped[str | None] = mapped_column(String(80))
    avatar_url: Mapped[str | None] = mapped_column(String(1024))
    avatar_kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="default")
    avatar_bucket: Mapped[str | None] = mapped_column(String(80))
    avatar_storage_key: Mapped[str | None] = mapped_column(String(1024))
    avatar_content_type: Mapped[str | None] = mapped_column(String(255))
    avatar_byte_size: Mapped[int | None] = mapped_column(BigInteger)
    avatar_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 선택 정보 — `demographic_use` 동의 시에만 저장
    gender: Mapped[str | None] = mapped_column(String(16))
    birth_year_month: Mapped[str | None] = mapped_column(String(6))
    residence_sigungu_code: Mapped[str | None] = mapped_column(String(5))

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="pending_verification",
    )
    roles: Mapped[list[str]] = mapped_column(
        ARRAY(String(16)),
        nullable=False,
        server_default=text("ARRAY['user']::varchar[]"),
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="active",
    )
    access_token_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
