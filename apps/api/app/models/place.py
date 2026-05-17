from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from app.core.krtour_map_contract import (
    FEATURE_KIND_VALUES,
    FEATURE_STATUS_VALUES,
    FORECAST_STYLE_VALUES,
    MAP_FEATURE_STATUS_VALUES,
    MAP_FEATURE_TYPE_VALUES,
    SOURCE_ROLE_VALUES,
    WEATHER_DOMAIN_VALUES,
    sql_in_values,
)
from app.db.base import Base
from app.models.mixins import TimestampMixin, kst_now


class PlaceCategory(TimestampMixin, Base):
    __tablename__ = "place_categories"
    __table_args__ = (
        CheckConstraint("category_code ~ '^[0-9]{8}$'", name=conv("ck_place_category_code_format")),
        Index("ix_place_categories_parent", "parent_category_code"),
    )

    category_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    tier1_code: Mapped[str] = mapped_column(String(2), nullable=False)
    tier2_code: Mapped[str] = mapped_column(String(2), nullable=False)
    tier3_code: Mapped[str] = mapped_column(String(2), nullable=False)
    tier4_code: Mapped[str] = mapped_column(String(2), nullable=False)
    tier1_name: Mapped[str] = mapped_column(String(80), nullable=False)
    tier2_name: Mapped[str | None] = mapped_column(String(80))
    tier3_name: Mapped[str | None] = mapped_column(String(80))
    tier4_name: Mapped[str | None] = mapped_column(String(120))
    depth: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    parent_category_code: Mapped[str | None] = mapped_column(
        String(8),
        ForeignKey(
            "place_categories.category_code",
            name="fk_place_categories_parent_category_code",
            ondelete="SET NULL",
        ),
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "dataset_key",
            "source_entity_type",
            "source_entity_id",
            "raw_payload_hash",
            name="uq_source_records_provider_dataset_entity_hash",
        ),
        Index("ix_source_records_provider_dataset", "provider", "dataset_key"),
        Index("ix_source_records_entity", "source_entity_type", "source_entity_id"),
        Index("ix_source_records_imported_at", "imported_at"),
        Index("ix_source_records_raw_geom", "raw_geom", postgresql_using="gist"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    dataset_key: Mapped[str] = mapped_column(String(120), nullable=False)
    source_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(80))
    raw_name: Mapped[str | None] = mapped_column(String(255))
    raw_address: Mapped[str | None] = mapped_column(String(700))
    raw_longitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    raw_latitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    raw_geom: Mapped[Any | None] = mapped_column(
        Geometry("GEOMETRY", srid=4326, spatial_index=False),
    )
    raw_start_date: Mapped[date | None] = mapped_column(Date)
    raw_end_date: Mapped[date | None] = mapped_column(Date)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    raw_payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BjdLookup(Base):
    __tablename__ = "bjd_lookup"
    __table_args__ = (
        Index(
            "ix_bjd_lookup_sido_trgm",
            "sido",
            postgresql_using="gin",
            postgresql_ops={"sido": "gin_trgm_ops"},
        ),
    )

    bjd_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    sido: Mapped[str] = mapped_column(Text, nullable=False)
    sigungu: Mapped[str | None] = mapped_column(Text)
    eupmyeondong: Mapped[str | None] = mapped_column(Text)
    ri: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at_src: Mapped[date | None] = mapped_column(Date)
    deleted_at_src: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=kst_now
    )


class Feature(Base):
    __tablename__ = "features"
    __table_args__ = (
        CheckConstraint(
            f"kind IN {sql_in_values(FEATURE_KIND_VALUES)}",
            name=conv("ck_features_kind"),
        ),
        CheckConstraint(
            f"status IN {sql_in_values(FEATURE_STATUS_VALUES)}",
            name=conv("ck_features_status"),
        ),
        Index("ix_features_coord", "coord", postgresql_using="gist"),
        Index("ix_features_geom", "geom", postgresql_using="gist"),
        Index("ix_features_kind_category", "kind", "category"),
        Index("ix_features_parent", "parent_feature_id"),
        Index("ix_features_sibling_group", "sibling_group_id"),
        Index("ix_features_bjd_code", "bjd_code"),
        Index(
            "ix_features_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    feature_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    bjd_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey("bjd_lookup.bjd_code", name="fk_features_bjd_code", ondelete="SET NULL"),
    )
    coord: Mapped[Any] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False),
        nullable=False,
    )
    geom: Mapped[Any | None] = mapped_column(
        Geometry("GEOMETRY", srid=4326, spatial_index=False),
    )
    address_road: Mapped[str | None] = mapped_column(Text)
    address_jibun: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    parent_feature_id: Mapped[str | None] = mapped_column(
        String(120),
        ForeignKey("features.feature_id", name="fk_features_parent", ondelete="SET NULL"),
    )
    sibling_group_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    urls: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    marker_icon: Mapped[str] = mapped_column(Text, nullable=False)
    marker_color: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    raw_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=kst_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=kst_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PricePoint(Base):
    __tablename__ = "price_points"

    feature_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("features.feature_id", name="fk_price_points_feature", ondelete="CASCADE"),
        primary_key=True,
    )
    price_category: Mapped[str] = mapped_column(String(40), nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3650)


class PriceValue(Base):
    __tablename__ = "price_values"
    __table_args__ = (Index("ix_price_values_observed_at", "observed_at", postgresql_using="brin"),)

    feature_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("price_points.feature_id", name="fk_price_values_feature", ondelete="CASCADE"),
        primary_key=True,
    )
    item_key: Mapped[str] = mapped_column(Text, primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KRW")


class WeatherObservation(Base):
    __tablename__ = "weather_observations"
    __table_args__ = (
        CheckConstraint(
            "forecast_kind IN ('nowcast', 'short', 'mid', 'observed', 'warning')",
            name=conv("ck_weather_observations_kind"),
        ),
        Index("ix_weather_obs_valid_at", "valid_at", postgresql_using="brin"),
    )

    feature_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("features.feature_id", name="fk_weather_obs_feature", ondelete="CASCADE"),
        primary_key=True,
    )
    forecast_kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class MapFeature(TimestampMixin, Base):
    __tablename__ = "map_features"
    __table_args__ = (
        CheckConstraint(
            f"feature_type IN {sql_in_values(MAP_FEATURE_TYPE_VALUES)}",
            name=conv("ck_map_features_feature_type"),
        ),
        CheckConstraint(
            "geometry_kind IN ('point', 'line', 'polygon', 'mixed')",
            name=conv("ck_map_features_geometry_kind"),
        ),
        CheckConstraint(
            f"status IN {sql_in_values(MAP_FEATURE_STATUS_VALUES)}",
            name=conv("ck_map_features_status"),
        ),
        CheckConstraint(
            "parent_feature_id IS NULL OR parent_feature_id <> id",
            name=conv("ck_map_features_not_self_parent"),
        ),
        Index("ix_map_features_public_id", "public_id"),
        Index("ix_map_features_parent_feature_id", "parent_feature_id"),
        Index("ix_map_features_type", "feature_type"),
        Index("ix_map_features_status_visible", "status", "is_visible"),
        Index("ix_map_features_category", "category_code"),
        Index("ix_map_features_legal_dong", "legal_dong_code"),
        Index("ix_map_features_sigungu", "sigungu_code"),
        Index("ix_map_features_primary_source_record", "primary_source_record_id"),
        Index("ix_map_features_geom", "geom", postgresql_using="gist"),
        Index("ix_map_features_centroid", "centroid", postgresql_using="gist"),
        Index("ix_map_features_search", "search_text", postgresql_using="gin"),
        Index(
            "ix_map_features_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    feature_type: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_feature_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "map_features.id", name="fk_map_features_parent_feature_id", ondelete="SET NULL"
        ),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    category_code: Mapped[str | None] = mapped_column(
        String(8),
        ForeignKey("place_categories.category_code", name="fk_map_features_category_code"),
    )
    category_name: Mapped[str | None] = mapped_column(String(120))
    geom: Mapped[Any] = mapped_column(
        Geometry("GEOMETRY", srid=4326, spatial_index=False),
        nullable=False,
    )
    geometry_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    centroid: Mapped[Any] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False),
        nullable=False,
    )
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    address: Mapped[str | None] = mapped_column(String(700))
    road_address: Mapped[str | None] = mapped_column(String(500))
    jibun_address: Mapped[str | None] = mapped_column(String(500))
    sido_code: Mapped[str | None] = mapped_column(String(10))
    sigungu_code: Mapped[str | None] = mapped_column(String(10))
    legal_dong_code: Mapped[str | None] = mapped_column(
        String(10),
        ForeignKey(
            "address_code_standard.legal_dong_code",
            name="fk_map_features_legal_dong_code",
            ondelete="SET NULL",
        ),
    )
    admin_dong_code: Mapped[str | None] = mapped_column(String(10))
    road_name_code: Mapped[str | None] = mapped_column(String(12))
    road_address_management_no: Mapped[str | None] = mapped_column(String(64))
    phone: Mapped[str | None] = mapped_column(String(120))
    website_url: Mapped[str | None] = mapped_column(Text)
    search_text: Mapped[Any | None] = mapped_column(TSVECTOR)
    popularity_score: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False, default=0)
    priority_score: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    primary_source_record_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "source_records.id",
            name="fk_map_features_primary_source_record_id",
            ondelete="SET NULL",
        ),
    )
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=kst_now,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlaceDetail(TimestampMixin, Base):
    __tablename__ = "place_details"
    __table_args__ = (
        CheckConstraint(
            "place_kind IN ("
            "'tourist_spot', 'restaurant', 'cafe', 'hotel', "
            "'parking', 'toilet', 'ev_charger', 'viewpoint'"
            ")",
            name=conv("ck_place_details_place_kind"),
        ),
        CheckConstraint(
            "price_level IS NULL OR price_level BETWEEN 0 AND 5",
            name=conv("ck_place_details_price_level"),
        ),
        CheckConstraint(
            "recommended_duration_min IS NULL OR recommended_duration_min >= 0",
            name=conv("ck_place_details_recommended_duration"),
        ),
        Index("ix_place_details_place_kind", "place_kind"),
    )

    feature_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("map_features.id", name="fk_place_details_feature_id", ondelete="CASCADE"),
        primary_key=True,
    )
    place_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    opening_hours: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    closed_days: Mapped[str | None] = mapped_column(Text)
    admission_fee: Mapped[str | None] = mapped_column(Text)
    price_level: Mapped[int | None] = mapped_column(SmallInteger)
    reservation_required: Mapped[bool | None] = mapped_column(Boolean)
    reservation_url: Mapped[str | None] = mapped_column(Text)
    parking_available: Mapped[bool | None] = mapped_column(Boolean)
    pet_allowed: Mapped[bool | None] = mapped_column(Boolean)
    stroller_accessible: Mapped[bool | None] = mapped_column(Boolean)
    wheelchair_accessible: Mapped[bool | None] = mapped_column(Boolean)
    indoor: Mapped[bool | None] = mapped_column(Boolean)
    outdoor: Mapped[bool | None] = mapped_column(Boolean)
    checkin_time: Mapped[time | None] = mapped_column(Time)
    checkout_time: Mapped[time | None] = mapped_column(Time)
    recommended_duration_min: Mapped[int | None] = mapped_column(Integer)
    operation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    address_resolution_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unresolved"
    )
    verification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unverified"
    )
    quality_score: Mapped[int | None] = mapped_column(Integer)
    opened_on: Mapped[date | None] = mapped_column(Date)
    closed_on: Mapped[date | None] = mapped_column(Date)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class EventDetail(TimestampMixin, Base):
    __tablename__ = "event_details"
    __table_args__ = (
        CheckConstraint(
            "event_kind IN ('festival', 'performance', 'exhibition', 'market', 'activity')",
            name=conv("ck_event_details_event_kind"),
        ),
        CheckConstraint("end_date >= start_date", name=conv("ck_event_details_date_range")),
        CheckConstraint(
            "end_time IS NULL OR start_time IS NULL OR end_time >= start_time",
            name=conv("ck_event_details_time_range"),
        ),
        Index("ix_event_details_event_kind", "event_kind"),
        Index("ix_event_details_period", "start_date", "end_date"),
        Index("ix_event_details_venue_feature_id", "venue_feature_id"),
    )

    feature_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("map_features.id", name="fk_event_details_feature_id", ondelete="CASCADE"),
        primary_key=True,
    )
    event_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    venue_name: Mapped[str | None] = mapped_column(Text)
    venue_feature_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "map_features.id", name="fk_event_details_venue_feature_id", ondelete="SET NULL"
        ),
    )
    organizer: Mapped[str | None] = mapped_column(Text)
    host: Mapped[str | None] = mapped_column(Text)
    sponsor: Mapped[str | None] = mapped_column(Text)
    contact_phone: Mapped[str | None] = mapped_column(Text)
    official_url: Mapped[str | None] = mapped_column(Text)
    reservation_url: Mapped[str | None] = mapped_column(Text)
    fee_info: Mapped[str | None] = mapped_column(Text)
    is_free: Mapped[bool | None] = mapped_column(Boolean)
    age_limit: Mapped[str | None] = mapped_column(Text)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    recurrence_rule: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class RouteDetail(TimestampMixin, Base):
    __tablename__ = "route_details"
    __table_args__ = (
        CheckConstraint(
            "route_kind IN ('walking', 'hiking', 'cycling', 'driving', 'scenic')",
            name=conv("ck_route_details_route_kind"),
        ),
        CheckConstraint(
            "distance_m IS NULL OR distance_m >= 0", name=conv("ck_route_details_distance")
        ),
        CheckConstraint(
            "duration_min IS NULL OR duration_min >= 0", name=conv("ck_route_details_duration")
        ),
        Index("ix_route_details_route_kind", "route_kind"),
        Index("ix_route_details_start_feature_id", "start_feature_id"),
        Index("ix_route_details_end_feature_id", "end_feature_id"),
    )

    feature_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("map_features.id", name="fk_route_details_feature_id", ondelete="CASCADE"),
        primary_key=True,
    )
    route_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    distance_m: Mapped[int | None] = mapped_column(Integer)
    duration_min: Mapped[int | None] = mapped_column(Integer)
    difficulty: Mapped[str | None] = mapped_column(String(32))
    start_name: Mapped[str | None] = mapped_column(Text)
    end_name: Mapped[str | None] = mapped_column(Text)
    start_feature_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "map_features.id", name="fk_route_details_start_feature_id", ondelete="SET NULL"
        ),
    )
    end_feature_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("map_features.id", name="fk_route_details_end_feature_id", ondelete="SET NULL"),
    )
    elevation_gain_m: Mapped[int | None] = mapped_column(Integer)
    elevation_loss_m: Mapped[int | None] = mapped_column(Integer)
    min_elevation_m: Mapped[int | None] = mapped_column(Integer)
    max_elevation_m: Mapped[int | None] = mapped_column(Integer)
    is_loop: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recommended_season: Mapped[str | None] = mapped_column(Text)
    surface_type: Mapped[str | None] = mapped_column(String(32))
    accessibility_note: Mapped[str | None] = mapped_column(Text)
    safety_note: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class RouteWaypoint(Base):
    __tablename__ = "route_waypoints"
    __table_args__ = (
        UniqueConstraint("route_feature_id", "seq", name="uq_route_waypoints_route_seq"),
        CheckConstraint("seq >= 1", name=conv("ck_route_waypoints_positive_seq")),
        Index("ix_route_waypoints_route_seq", "route_feature_id", "seq"),
        Index("ix_route_waypoints_related_feature_id", "related_feature_id"),
        Index("ix_route_waypoints_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    route_feature_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "route_details.feature_id",
            name="fk_route_waypoints_route_feature_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[Any] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=False
    )
    related_feature_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "map_features.id", name="fk_route_waypoints_related_feature_id", ondelete="SET NULL"
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=kst_now
    )


class AreaDetail(TimestampMixin, Base):
    __tablename__ = "area_details"
    __table_args__ = (
        CheckConstraint(
            "area_kind IN ("
            "'national_park', 'beach', 'tourism_zone', "
            "'market_area', 'restricted_area'"
            ")",
            name=conv("ck_area_details_area_kind"),
        ),
        CheckConstraint(
            "area_size_m2 IS NULL OR area_size_m2 >= 0", name=conv("ck_area_details_size")
        ),
        Index("ix_area_details_area_kind", "area_kind"),
        Index("ix_area_details_restricted", "is_restricted"),
    )

    feature_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("map_features.id", name="fk_area_details_feature_id", ondelete="CASCADE"),
        primary_key=True,
    )
    area_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    managing_org: Mapped[str | None] = mapped_column(Text)
    contact_phone: Mapped[str | None] = mapped_column(Text)
    website_url: Mapped[str | None] = mapped_column(Text)
    rules: Mapped[str | None] = mapped_column(Text)
    fee_info: Mapped[str | None] = mapped_column(Text)
    open_season_start: Mapped[date | None] = mapped_column(Date)
    open_season_end: Mapped[date | None] = mapped_column(Date)
    area_size_m2: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    is_restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    restriction_note: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class NoticeDetail(TimestampMixin, Base):
    __tablename__ = "notice_details"
    __table_args__ = (
        CheckConstraint(
            "notice_kind IN ("
            "'closure', 'construction', 'traffic_control', "
            "'congestion', 'weather_warning'"
            ")",
            name=conv("ck_notice_details_notice_kind"),
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name=conv("ck_notice_details_severity"),
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name=conv("ck_notice_details_valid_period"),
        ),
        CheckConstraint(
            "resolved_at IS NULL OR is_resolved = true",
            name=conv("ck_notice_details_resolved_at"),
        ),
        Index("ix_notice_details_notice_kind", "notice_kind"),
        Index("ix_notice_details_severity", "severity"),
        Index("ix_notice_details_related_feature_id", "related_feature_id"),
        Index("ix_notice_details_active", "is_resolved", "valid_from", "valid_to"),
    )

    feature_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("map_features.id", name="fk_notice_details_feature_id", ondelete="CASCADE"),
        primary_key=True,
    )
    notice_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    related_feature_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "map_features.id", name="fk_notice_details_related_feature_id", ondelete="SET NULL"
        ),
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ContentItem(TimestampMixin, Base):
    __tablename__ = "content_items"
    __table_args__ = (
        CheckConstraint(
            "content_kind IN ('article', 'curated_list', 'itinerary_template', 'guide')",
            name=conv("ck_content_items_content_kind"),
        ),
        Index("ix_content_items_kind", "content_kind"),
        Index("ix_content_items_published", "is_published", "publish_start_at", "publish_end_at"),
        Index("ix_content_items_slug", "slug"),
        Index(
            "ix_content_items_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    content_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    slug: Mapped[str | None] = mapped_column(String(255), unique=True)
    author_name: Mapped[str | None] = mapped_column(String(120))
    source_provider: Mapped[str | None] = mapped_column(String(40))
    source_url: Mapped[str | None] = mapped_column(Text)
    publish_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    priority_score: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False, default=0)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ContentFeatureLink(Base):
    __tablename__ = "content_feature_links"
    __table_args__ = (
        CheckConstraint(
            "role IN ('main', 'stop', 'related', 'nearby', 'recommended')",
            name=conv("ck_content_feature_links_role"),
        ),
        Index("ix_content_feature_links_content", "content_id", "sort_order"),
        Index("ix_content_feature_links_feature", "feature_id"),
    )

    content_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "content_items.id", name="fk_content_feature_links_content_id", ondelete="CASCADE"
        ),
        primary_key=True,
    )
    feature_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "map_features.id", name="fk_content_feature_links_feature_id", ondelete="CASCADE"
        ),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(32), primary_key=True, default="related")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(Text)


class MapFeatureSourceLink(Base):
    __tablename__ = "map_feature_source_links"
    __table_args__ = (
        UniqueConstraint(
            "feature_id", "source_record_id", name="uq_map_feature_source_links_feature_source"
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 100",
            name=conv("ck_map_feature_source_links_confidence"),
        ),
        CheckConstraint(
            f"source_role IN {sql_in_values(SOURCE_ROLE_VALUES)}",
            name=conv("ck_map_feature_source_links_role"),
        ),
        Index("ix_map_feature_source_links_feature", "feature_id"),
        Index("ix_map_feature_source_links_source", "source_record_id"),
        Index("ix_map_feature_source_links_role", "source_role"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    feature_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "map_features.id", name="fk_map_feature_source_links_feature_id", ondelete="CASCADE"
        ),
        nullable=False,
    )
    source_record_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "source_records.id",
            name="fk_map_feature_source_links_source_record_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    source_role: Mapped[str] = mapped_column(String(40), nullable=False, default="enrichment")
    match_method: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    is_primary_source: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=kst_now
    )


class MapFeatureOverride(Base):
    __tablename__ = "map_feature_overrides"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_review', 'active', 'rejected', 'superseded')",
            name=conv("ck_map_feature_overrides_status"),
        ),
        CheckConstraint("field_path <> ''", name=conv("ck_map_feature_overrides_field_path")),
        Index("ix_map_feature_overrides_feature", "feature_id"),
        Index("ix_map_feature_overrides_provider", "provider"),
        Index("ix_map_feature_overrides_source", "source_record_id"),
        Index("ix_map_feature_overrides_status", "status"),
        Index("ix_map_feature_overrides_reviewer", "reviewed_by_user_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    feature_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "map_features.id",
            name="fk_map_feature_overrides_feature_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_dataset_key: Mapped[str | None] = mapped_column(String(120))
    source_record_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "source_records.id",
            name="fk_map_feature_overrides_source_record_id",
            ondelete="SET NULL",
        ),
    )
    field_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    override_value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", name="fk_map_feature_overrides_reviewed_by", ondelete="SET NULL"),
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=kst_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=kst_now
    )


class MapFeatureWeatherValue(Base):
    __tablename__ = "map_feature_weather_values"
    __table_args__ = (
        CheckConstraint(
            f"weather_domain IN {sql_in_values(WEATHER_DOMAIN_VALUES)}",
            name=conv("ck_map_feature_weather_values_domain"),
        ),
        CheckConstraint(
            f"forecast_style IN {sql_in_values(FORECAST_STYLE_VALUES)}",
            name=conv("ck_map_feature_weather_values_style"),
        ),
        UniqueConstraint(
            "feature_id",
            "provider",
            "weather_domain",
            "forecast_style",
            "metric_key",
            "issued_at",
            "valid_at",
            "observed_at",
            name="uq_map_feature_weather_values_feature_provider_time",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_map_feature_weather_values_feature_valid", "feature_id", "valid_at"),
        Index("ix_map_feature_weather_values_provider_domain", "provider", "weather_domain"),
        Index("ix_map_feature_weather_values_valid_at", "valid_at", postgresql_using="brin"),
        Index("ix_map_feature_weather_values_observed_at", "observed_at", postgresql_using="brin"),
        Index("ix_map_feature_weather_values_source", "source_record_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    feature_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "map_features.id",
            name="fk_map_feature_weather_values_feature_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    weather_domain: Mapped[str] = mapped_column(String(40), nullable=False)
    forecast_style: Mapped[str] = mapped_column(String(32), nullable=False)
    source_record_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "source_records.id",
            name="fk_map_feature_weather_values_source_record_id",
            ondelete="SET NULL",
        ),
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metric_key: Mapped[str] = mapped_column(String(80), nullable=False)
    metric_name: Mapped[str | None] = mapped_column(String(120))
    value_number: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    value_text: Mapped[str | None] = mapped_column(String(120))
    unit: Mapped[str | None] = mapped_column(String(24))
    severity: Mapped[str | None] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=kst_now
    )


class ContentSourceLink(Base):
    __tablename__ = "content_source_links"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 100", name=conv("ck_content_source_links_confidence")
        ),
        Index("ix_content_source_links_content", "content_id"),
        Index("ix_content_source_links_source", "source_record_id"),
    )

    content_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "content_items.id", name="fk_content_source_links_content_id", ondelete="CASCADE"
        ),
        primary_key=True,
    )
    source_record_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "source_records.id", name="fk_content_source_links_source_record_id", ondelete="CASCADE"
        ),
        primary_key=True,
    )
    match_method: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    is_primary_source: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=kst_now
    )


class FeatureMappingCandidate(Base):
    __tablename__ = "feature_mapping_candidates"
    __table_args__ = (
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 100",
            name=conv("ck_feature_mapping_candidates_confidence"),
        ),
        CheckConstraint(
            "source_record_id_a <> source_record_id_b",
            name=conv("ck_feature_mapping_candidates_different_records"),
        ),
        CheckConstraint(
            "decision IN ('pending', 'auto_approved', 'approved', 'rejected')",
            name=conv("ck_feature_mapping_candidates_decision"),
        ),
        CheckConstraint(
            "candidate_feature_type IN ('place', 'event', 'route', 'area', 'notice')",
            name=conv("ck_feature_mapping_candidates_feature_type"),
        ),
        UniqueConstraint(
            "source_record_id_a",
            "source_record_id_b",
            name="uq_feature_mapping_candidates_record_pair",
        ),
        Index("ix_feature_mapping_candidates_a", "source_record_id_a"),
        Index("ix_feature_mapping_candidates_b", "source_record_id_b"),
        Index("ix_feature_mapping_candidates_decision", "decision"),
        Index("ix_feature_mapping_candidates_score", "confidence_score"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_record_id_a: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "source_records.id", name="fk_feature_mapping_candidates_record_a", ondelete="CASCADE"
        ),
        nullable=False,
    )
    source_record_id_b: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "source_records.id", name="fk_feature_mapping_candidates_record_b", ondelete="CASCADE"
        ),
        nullable=False,
    )
    candidate_feature_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    name_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    date_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    address_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    distance_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    org_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    decision: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_by_user_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=kst_now
    )


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (Index("ix_tags_slug", "slug"),)

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=kst_now
    )


class MapFeatureTag(Base):
    __tablename__ = "map_feature_tags"
    __table_args__ = (Index("ix_map_feature_tags_tag", "tag_id"),)

    feature_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("map_features.id", name="fk_map_feature_tags_feature_id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tags.id", name="fk_map_feature_tags_tag_id", ondelete="CASCADE"),
        primary_key=True,
    )


class ContentTag(Base):
    __tablename__ = "content_tags"
    __table_args__ = (Index("ix_content_tags_tag", "tag_id"),)

    content_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("content_items.id", name="fk_content_tags_content_id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tags.id", name="fk_content_tags_tag_id", ondelete="CASCADE"),
        primary_key=True,
    )


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint(
            "media_type IN ('image', 'video', 'icon')", name=conv("ck_media_assets_media_type")
        ),
        CheckConstraint("width IS NULL OR width > 0", name=conv("ck_media_assets_width")),
        CheckConstraint("height IS NULL OR height > 0", name=conv("ck_media_assets_height")),
        Index("ix_media_assets_source", "source_provider"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    media_type: Mapped[str] = mapped_column(String(32), nullable=False, default="image")
    url: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(Text)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(Text)
    alt_text: Mapped[str | None] = mapped_column(Text)
    source_provider: Mapped[str | None] = mapped_column(String(40))
    source_url: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(Text)
    credit: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=kst_now
    )


class MapFeatureMedia(Base):
    __tablename__ = "map_feature_media"
    __table_args__ = (
        Index("ix_map_feature_media_feature", "feature_id", "sort_order"),
        Index("ix_map_feature_media_media", "media_id"),
    )

    feature_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("map_features.id", name="fk_map_feature_media_feature_id", ondelete="CASCADE"),
        primary_key=True,
    )
    media_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("media_assets.id", name="fk_map_feature_media_media_id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(32), primary_key=True, default="gallery")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ContentMedia(Base):
    __tablename__ = "content_media"
    __table_args__ = (
        Index("ix_content_media_content", "content_id", "sort_order"),
        Index("ix_content_media_media", "media_id"),
    )

    content_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("content_items.id", name="fk_content_media_content_id", ondelete="CASCADE"),
        primary_key=True,
    )
    media_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("media_assets.id", name="fk_content_media_media_id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(32), primary_key=True, default="body")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class MapFeatureProviderRef(TimestampMixin, Base):
    __tablename__ = "map_feature_provider_refs"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_dataset_key",
            "provider_feature_id",
            name="uq_map_feature_provider_refs_provider_dataset_feature",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_map_feature_provider_refs_feature", "feature_id"),
        Index("ix_map_feature_provider_refs_provider_feature", "provider", "provider_feature_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    feature_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "map_features.id", name="fk_map_feature_provider_refs_feature_id", ondelete="CASCADE"
        ),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_feature_id: Mapped[str | None] = mapped_column(String(255))
    provider_dataset_key: Mapped[str | None] = mapped_column(String(120))
    url: Mapped[str | None] = mapped_column(Text)
    stable_name: Mapped[str | None] = mapped_column(String(255))
    stable_address: Mapped[str | None] = mapped_column(String(500))
    stable_phone: Mapped[str | None] = mapped_column(String(120))
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MapFeatureWebLink(TimestampMixin, Base):
    __tablename__ = "map_feature_web_links"
    __table_args__ = (
        UniqueConstraint("feature_id", "url", name="uq_map_feature_web_links_feature_url"),
        Index("ix_map_feature_web_links_feature", "feature_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    feature_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "map_features.id", name="fk_map_feature_web_links_feature_id", ondelete="CASCADE"
        ),
        nullable=False,
    )
    link_type: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(40))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
