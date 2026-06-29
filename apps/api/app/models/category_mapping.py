"""`app.category_mappings` — Pinvi-local category presentation overrides."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class CategoryMappingOverride(Base, TimestampMixin):
    __tablename__ = "category_mappings"
    __table_args__ = (
        CheckConstraint(
            "display_name_ko IS NULL OR length(btrim(display_name_ko)) BETWEEN 1 AND 120",
            name="ck_category_mappings_display_name",
        ),
        CheckConstraint(
            "marker_color IS NULL OR marker_color ~ '^P-(0[1-9]|1[0-6])$'",
            name="ck_category_mappings_marker_color",
        ),
        CheckConstraint(
            "marker_icon IS NULL OR marker_icon ~ '^[a-z0-9_-]{1,64}$'",
            name="ck_category_mappings_marker_icon",
        ),
        Index("ix_category_mappings_updated_at", "updated_at"),
    )

    category_key: Mapped[str] = mapped_column(Text(), primary_key=True)
    display_name_ko: Mapped[str | None] = mapped_column(Text())
    marker_color: Mapped[str | None] = mapped_column(Text())
    marker_icon: Mapped[str | None] = mapped_column(Text())
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="SET NULL"),
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="SET NULL"),
    )
