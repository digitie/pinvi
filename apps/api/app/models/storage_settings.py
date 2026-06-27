"""전역 객체 저장소 설정."""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class StorageSettings(Base, TimestampMixin):
    __tablename__ = "storage_settings"
    __table_args__ = (
        CheckConstraint("settings_id = 1", name="storage_settings_singleton"),
        CheckConstraint(
            "avatar_max_upload_bytes > 0",
            name="storage_settings_avatar_max_upload_bytes_positive",
        ),
    )

    settings_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        server_default=text("1"),
    )
    avatar_max_upload_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("2097152"),
    )
