from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import conv

from app.core.json_types import JsonValue
from app.db.base import Base
from app.models.mixins import TimestampMixin, kst_now

if TYPE_CHECKING:
    from app.models.place import MapFeature
    from app.models.tour import TourServingPublicCulturalFestival
    from app.models.user import User


class Trip(TimestampMixin, Base):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint(
            "(start_date IS NULL AND end_date IS NULL) OR "
            "(start_date IS NOT NULL AND end_date IS NOT NULL AND end_date >= start_date)",
            name="date_range_order",
        ),
        Index("ix_trips_leader_id", "leader_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    leader_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", name="fk_trips_leader_id", ondelete="CASCADE"),
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    destination: Mapped[str] = mapped_column(String(120), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    fuel_types: Mapped[list[str] | None] = mapped_column(ARRAY(String(40)))
    planning_status: Mapped[str] = mapped_column(String(32), default="idea", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="trips", foreign_keys=[user_id])
    days: Mapped[list[TripDay]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="TripDay.day_index",
    )


class TripDay(TimestampMixin, Base):
    __tablename__ = "trip_days"
    __table_args__ = (
        UniqueConstraint("trip_id", "date", name="uq_trip_days_trip_id_date"),
        UniqueConstraint("trip_id", "day_index", name="uq_trip_days_trip_id_day_index"),
        CheckConstraint("day_index >= 1", name="positive_day_index"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    trip_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("trips.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[date | None] = mapped_column(Date)

    trip: Mapped[Trip] = relationship(back_populates="days")
    items: Mapped[list[TripPlanItem]] = relationship(
        back_populates="trip_day",
        cascade="all, delete-orphan",
        order_by="TripPlanItem.sort_order",
    )


class TripPlanItem(TimestampMixin, Base):
    __tablename__ = "trip_plan_items"
    __table_args__ = (
        UniqueConstraint("trip_day_id", "sort_order", name="uq_tpi_day_sort_order"),
        CheckConstraint(
            "resource_type IN ("
            "'place', 'event', 'route', 'area', 'notice', "
            "'festival', 'trail', 'scenic_road', 'custom'"
            ")",
            name=conv("ck_tpi_resource_type"),
        ),
        CheckConstraint("sort_order >= 1", name=conv("ck_tpi_positive_sort_order")),
        CheckConstraint(
            "map_feature_id IS NULL OR resource_type IN ("
            "'place', 'event', 'route', 'area', 'notice'"
            ")",
            name=conv("ck_tpi_map_feature_type_match"),
        ),
        CheckConstraint(
            "festival_id IS NULL OR resource_type = 'festival'",
            name=conv("ck_tpi_festival_type_match"),
        ),
        CheckConstraint(
            "NOT (map_feature_id IS NOT NULL AND festival_id IS NOT NULL)",
            name=conv("ck_tpi_single_fk_resource"),
        ),
        CheckConstraint(
            "resource_key IS NULL OR resource_type IN ('trail', 'scenic_road', 'route', 'custom')",
            name=conv("ck_tpi_resource_key_type"),
        ),
        Index("ix_tpi_trip_day_sort", "trip_day_id", "sort_order"),
        Index("ix_tpi_map_feature_id", "map_feature_id"),
        Index("ix_tpi_festival_id", "festival_id"),
        Index("ix_tpi_resource_type", "resource_type"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    trip_day_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("trip_days.id", name="fk_tpi_trip_day_id", ondelete="CASCADE"),
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    map_feature_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("map_features.id", name="fk_tpi_map_feature_id", ondelete="RESTRICT"),
    )
    festival_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "tour_serving_public_cultural_festival.id",
            name="fk_tpi_festival_id",
            ondelete="RESTRICT",
        ),
    )
    resource_key: Mapped[str | None] = mapped_column(String(180))
    title_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    address_snapshot: Mapped[str | None] = mapped_column(String(700))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    operating_hours_snapshot: Mapped[str | None] = mapped_column(String(255))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    note: Mapped[str | None] = mapped_column(String(1000))
    resource_metadata: Mapped[dict[str, JsonValue]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    trip_day: Mapped[TripDay] = relationship(back_populates="items")
    map_feature: Mapped[MapFeature | None] = relationship()
    festival: Mapped[TourServingPublicCulturalFestival | None] = relationship()


class TripMember(Base):
    __tablename__ = "trip_members"
    __table_args__ = (
        CheckConstraint(
            "user_id IS NOT NULL OR invited_email IS NOT NULL",
            name=conv("ck_trip_members_identity"),
        ),
        CheckConstraint("role IN ('companion')", name=conv("ck_trip_members_role")),
        CheckConstraint(
            "invited_birth_yyyymm IS NULL OR invited_birth_yyyymm ~ '^[0-9]{6}$'",
            name=conv("ck_trip_members_birth_yyyymm"),
        ),
        Index("ix_trip_members_trip_user", "trip_id", "user_id"),
        Index("ix_trip_members_user", "user_id"),
        Index(
            "uq_trip_members_trip_user",
            "trip_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_trip_members_trip_email",
            "trip_id",
            "invited_email",
            unique=True,
            postgresql_where=text("invited_email IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    trip_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("trips.id", name="fk_trip_members_trip_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", name="fk_trip_members_user_id", ondelete="CASCADE"),
    )
    invited_email: Mapped[str | None] = mapped_column(CITEXT)
    invited_nickname: Mapped[str | None] = mapped_column(Text)
    invited_gender: Mapped[str | None] = mapped_column(String(32))
    invited_birth_yyyymm: Mapped[str | None] = mapped_column(String(6))
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="companion")
    invited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=kst_now
    )
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TripPoi(TimestampMixin, Base):
    __tablename__ = "trip_pois"
    __table_args__ = (
        ForeignKeyConstraint(
            ["trip_id", "day_index"],
            ["trip_days.trip_id", "trip_days.day_index"],
            name="fk_trip_pois_trip_day",
            ondelete="CASCADE",
        ),
        CheckConstraint("version >= 1", name=conv("ck_trip_pois_version")),
        Index("ix_trip_pois_trip_day_sort", "trip_id", "day_index", "sort_order"),
        Index("ix_trip_pois_feature", "feature_id"),
        Index("ix_trip_pois_added_by", "added_by_user_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    trip_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("trips.id", name="fk_trip_pois_trip_id", ondelete="CASCADE"),
        nullable=False,
    )
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[str] = mapped_column(String(80, collation="C"), nullable=False)
    feature_id: Mapped[str | None] = mapped_column(
        String(120),
        ForeignKey("features.feature_id", name="fk_trip_pois_feature_id", ondelete="SET NULL"),
    )
    feature_link_broken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False, default=dict)
    custom_marker_color: Mapped[str | None] = mapped_column(String(16))
    custom_marker_icon: Mapped[str | None] = mapped_column(Text)
    added_by_user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", name="fk_trip_pois_added_by", ondelete="RESTRICT"),
        nullable=False,
    )
    memo: Mapped[str | None] = mapped_column(Text)
    budget: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    actual_spent: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KRW")
    user_url: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class NoticePlan(TimestampMixin, Base):
    __tablename__ = "notice_plans"
    __table_args__ = (
        CheckConstraint(
            "(starts_on IS NULL AND ends_on IS NULL) OR "
            "(starts_on IS NOT NULL AND ends_on IS NOT NULL AND ends_on >= starts_on)",
            name=conv("ck_notice_plans_date_range"),
        ),
        Index(
            "uq_notice_plans_slug_active",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_notice_plans_published", "is_published", "updated_at"),
        Index("ix_notice_plans_category", "category", "updated_at"),
        Index("ix_notice_plans_created_by_admin", "created_by_admin_id"),
        Index("ix_notice_plans_updated_by_admin", "updated_by_admin_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    source_name: Mapped[str | None] = mapped_column(String(200))
    destination: Mapped[str | None] = mapped_column(String(120))
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_admin_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", name="fk_notice_plans_created_by_admin_id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_by_admin_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", name="fk_notice_plans_updated_by_admin_id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NoticePoi(TimestampMixin, Base):
    __tablename__ = "notice_pois"
    __table_args__ = (
        CheckConstraint("day_index >= 1", name=conv("ck_notice_pois_day_index")),
        CheckConstraint("version >= 1", name=conv("ck_notice_pois_version")),
        Index("ix_notice_pois_plan_sort", "notice_plan_id", "day_index", "sort_order"),
        Index("ix_notice_pois_feature", "feature_id"),
        Index("ix_notice_pois_map_feature", "map_feature_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    notice_plan_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("notice_plans.id", name="fk_notice_pois_notice_plan_id", ondelete="CASCADE"),
        nullable=False,
    )
    day_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sort_order: Mapped[str] = mapped_column(String(80, collation="C"), nullable=False)
    feature_id: Mapped[str | None] = mapped_column(String(120))
    map_feature_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("map_features.id", name="fk_notice_pois_map_feature_id", ondelete="SET NULL"),
    )
    snapshot: Mapped[dict[str, JsonValue]] = mapped_column(JSONB, nullable=False, default=dict)
    memo: Mapped[str | None] = mapped_column(Text)
    budget: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KRW")
    user_url: Mapped[str | None] = mapped_column(Text)
    custom_marker_color: Mapped[str | None] = mapped_column(String(16))
    custom_marker_icon: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlanPoiAttachment(TimestampMixin, Base):
    __tablename__ = "plan_poi_attachments"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(trip_id, trip_poi_id, notice_plan_id, notice_poi_id) = 1",
            name=conv("ck_plan_poi_attachments_single_target"),
        ),
        CheckConstraint(
            "role IN ('attachment', 'image', 'document', 'reference')",
            name=conv("ck_plan_poi_attachments_role"),
        ),
        CheckConstraint("byte_size > 0", name=conv("ck_plan_poi_attachments_byte_size")),
        CheckConstraint("sort_order >= 0", name=conv("ck_plan_poi_attachments_sort_order")),
        Index("ix_plan_poi_attachments_trip", "trip_id", "sort_order"),
        Index("ix_plan_poi_attachments_trip_poi", "trip_poi_id", "sort_order"),
        Index("ix_plan_poi_attachments_notice_plan", "notice_plan_id", "sort_order"),
        Index("ix_plan_poi_attachments_notice_poi", "notice_poi_id", "sort_order"),
        Index("ix_plan_poi_attachments_source", "source_attachment_id"),
        Index("ix_plan_poi_attachments_storage_key", "bucket", "storage_key"),
        Index("ix_plan_poi_attachments_uploaded_by", "uploaded_by_user_id"),
        Index(
            "ix_plan_poi_attachments_active",
            "deleted_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    trip_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("trips.id", name="fk_plan_poi_attachments_trip_id", ondelete="CASCADE"),
    )
    trip_poi_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("trip_pois.id", name="fk_plan_poi_attachments_trip_poi_id", ondelete="CASCADE"),
    )
    notice_plan_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "notice_plans.id",
            name="fk_plan_poi_attachments_notice_plan_id",
            ondelete="CASCADE",
        ),
    )
    notice_poi_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "notice_pois.id",
            name="fk_plan_poi_attachments_notice_poi_id",
            ondelete="CASCADE",
        ),
    )
    source_attachment_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "plan_poi_attachments.id",
            name="fk_plan_poi_attachments_source_attachment_id",
            ondelete="SET NULL",
        ),
    )
    bucket: Mapped[str] = mapped_column(String(80), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    public_url: Mapped[str | None] = mapped_column(Text)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(40), nullable=False, default="attachment")
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", name="fk_plan_poi_attachments_uploaded_by_user_id"),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TripShareToken(Base):
    __tablename__ = "trip_share_tokens"
    __table_args__ = (
        CheckConstraint("permission IN ('view')", name=conv("ck_trip_share_tokens_permission")),
        Index(
            "ix_trip_share_tokens_active_trip",
            "trip_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_trip_share_tokens_created_by", "created_by"),
    )

    token: Mapped[str] = mapped_column(String(43), primary_key=True)
    trip_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("trips.id", name="fk_trip_share_tokens_trip_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", name="fk_trip_share_tokens_created_by", ondelete="RESTRICT"),
        nullable=False,
    )
    permission: Mapped[str] = mapped_column(String(20), nullable=False, default="view")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=kst_now
    )
