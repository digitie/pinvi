"""`app.curated_trip_plans` + `app.curated_plan_pois` — Admin 추천 여행.

외부 `/notice-plans` API 이름은 Sprint 4 호환을 위해 유지하지만, 저장소 schema는
ADR-029에 따라 system notice와 분리된 curated-trip 이름을 쓴다.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from app.db.base import Base
from app.models.mixins import TimestampMixin


class CuratedTripPlan(Base, TimestampMixin):
    __tablename__ = "curated_trip_plans"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(source_curation_collection_id, "
            "source_curation_collection_revision, source_curation_collection_etag, "
            "source_curation_item_set_hash_version, source_curation_item_set_hash, "
            "source_curation_item_count) = 0 OR "
            "(source_system = 'kor-travel-map' AND "
            "num_nonnulls(source_curation_collection_id, "
            "source_curation_collection_revision, source_curation_collection_etag, "
            "source_curation_item_set_hash_version, source_curation_item_set_hash, "
            "source_curation_item_count) = 6 AND "
            "source_curation_collection_revision > 0 AND "
            "source_curation_collection_etag ~ '^\"sha256:[0-9a-f]{64}\"$' AND "
            "source_curation_item_set_hash_version = 'ktm-db-item-set-v1' AND "
            "source_curation_item_set_hash ~ '^[0-9a-f]{64}$' AND "
            "source_curation_item_count BETWEEN 0 AND 2000)",
            name=conv("ck_curated_trip_plans_curation_source"),
        ),
        Index(
            "uq_curated_trip_plans_curation_collection_active",
            "source_system",
            "source_curation_collection_id",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND source_system = 'kor-travel-map' "
                "AND source_curation_collection_id IS NOT NULL"
            ),
        ),
        UniqueConstraint(
            "curated_plan_id",
            "source_curation_collection_id",
            name="uq_curated_trip_plans_curation_identity",
        ),
    )

    curated_plan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False, server_default="recommended")
    summary: Mapped[str | None] = mapped_column(Text())
    source_name: Mapped[str | None] = mapped_column(String(200))
    destination: Mapped[str | None] = mapped_column(String(120))
    starts_on: Mapped[date | None] = mapped_column(Date())
    ends_on: Mapped[date | None] = mapped_column(Date())
    source_system: Mapped[str | None] = mapped_column(String(80))
    source_curated_feature_id: Mapped[str | None] = mapped_column(Text())
    source_curated_feature_version: Mapped[int | None] = mapped_column(Integer)
    source_etag: Mapped[str | None] = mapped_column(String(128))
    source_curation_collection_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    source_curation_collection_revision: Mapped[int | None] = mapped_column(BigInteger)
    source_curation_collection_etag: Mapped[str | None] = mapped_column(String(128))
    source_curation_item_set_hash_version: Mapped[str | None] = mapped_column(String(64))
    source_curation_item_set_hash: Mapped[str | None] = mapped_column(String(64))
    source_curation_item_count: Mapped[int | None] = mapped_column(BigInteger)
    source_imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def notice_plan_id(self) -> uuid.UUID:
        """Deprecated API alias retained for `/notice-plans` response compatibility."""

        return self.curated_plan_id


class CuratedPlanPoi(Base, TimestampMixin):
    __tablename__ = "curated_plan_pois"
    __table_args__ = (
        CheckConstraint(
            "budget_amount IS NULL OR budget_amount >= 0",
            name=conv("ck_curated_plan_pois_budget_nonnegative"),
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name=conv("ck_curated_plan_pois_currency"),
        ),
        CheckConstraint(
            "num_nonnulls(source_curation_import_receipt_id, "
            "source_curation_collection_id, source_curation_item_id, "
            "source_curation_item_revision, source_curation_item_etag) = 0 OR "
            "(num_nonnulls(source_curation_import_receipt_id, "
            "source_curation_collection_id, source_curation_item_id, "
            "source_curation_item_revision, source_curation_item_etag) = 5 AND "
            "feature_uuid IS NOT NULL AND source_curation_item_revision > 0 AND "
            "source_curation_item_etag ~ '^\"sha256:[0-9a-f]{64}\"$')",
            name=conv("ck_curated_plan_pois_curation_source"),
        ),
        UniqueConstraint(
            "curated_plan_id",
            "source_curation_item_id",
            name="uq_curated_plan_pois_curation_item",
        ),
        ForeignKeyConstraint(
            ["curated_plan_id", "source_curation_collection_id"],
            [
                "app.curated_trip_plans.curated_plan_id",
                "app.curated_trip_plans.source_curation_collection_id",
            ],
            name="fk_curated_plan_pois_curation_parent",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "source_curation_import_receipt_id",
                "source_curation_collection_id",
                "source_curation_item_id",
                "source_curation_item_revision",
                "source_curation_item_etag",
                "feature_uuid",
            ],
            [
                "app.ktm_curation_import_receipt_items.receipt_id",
                "app.ktm_curation_import_receipt_items.source_curation_collection_id",
                "app.ktm_curation_import_receipt_items.source_curation_item_id",
                "app.ktm_curation_import_receipt_items.source_curation_item_revision",
                "app.ktm_curation_import_receipt_items.source_curation_item_etag",
                "app.ktm_curation_import_receipt_items.feature_uuid",
            ],
            name="fk_curated_plan_pois_curation_receipt_item",
            ondelete="RESTRICT",
        ),
    )

    curated_poi_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    curated_plan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app.curated_trip_plans.curated_plan_id", ondelete="CASCADE"),
        nullable=False,
    )
    day_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    # LexoRank — COLLATE "C"
    sort_order: Mapped[str] = mapped_column(Text(collation="C"), nullable=False)
    feature_id: Mapped[str | None] = mapped_column(Text(), nullable=True)
    # T-VN-32C(Map ADR-068): legacy f_* 참조의 UUID shadow — 검증된 alias map
    # 이관만 채운다.
    feature_uuid: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    feature_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    memo: Mapped[str | None] = mapped_column(Text())
    budget_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="KRW")
    user_url: Mapped[str | None] = mapped_column(Text())
    custom_marker_color: Mapped[str | None] = mapped_column(String(16))
    custom_marker_icon: Mapped[str | None] = mapped_column(String(64))
    source_curated_feature_id: Mapped[str | None] = mapped_column(Text())
    source_curated_feature_item_id: Mapped[str | None] = mapped_column(Text())
    source_curation_import_receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True)
    )
    source_curation_collection_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    source_curation_item_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    source_curation_item_revision: Mapped[int | None] = mapped_column(BigInteger)
    source_curation_item_etag: Mapped[str | None] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def notice_poi_id(self) -> uuid.UUID:
        """Deprecated API alias retained for `/notice-plans` response compatibility."""

        return self.curated_poi_id

    @property
    def notice_plan_id(self) -> uuid.UUID:
        """Deprecated API alias retained for `/notice-plans` response compatibility."""

        return self.curated_plan_id


class KtmCurationImportReceipt(Base, TimestampMixin):
    """Map canonical collection import의 actor-scoped terminal replay 영수증."""

    __tablename__ = "ktm_curation_import_receipts"
    __table_args__ = (
        UniqueConstraint(
            "actor_admin_id",
            "idempotency_key",
            name="uq_ktm_curation_import_receipts_actor_key",
        ),
        UniqueConstraint(
            "receipt_id",
            "source_curation_collection_id",
            name="uq_ktm_curation_import_receipts_collection",
        ),
        ForeignKeyConstraint(
            ["result_plan_id", "source_curation_collection_id"],
            [
                "app.curated_trip_plans.curated_plan_id",
                "app.curated_trip_plans.source_curation_collection_id",
            ],
            name="fk_ktm_curation_import_receipts_result_source",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name=conv("ck_ktm_curation_import_receipts_fingerprint"),
        ),
        CheckConstraint(
            "source_system = 'kor-travel-map' AND "
            "mode IN ('create', 'refresh', 'cutover-backfill')",
            name=conv("ck_ktm_curation_import_receipts_request"),
        ),
        CheckConstraint(
            "source_curation_collection_revision > 0 AND "
            "source_curation_collection_etag ~ '^\"sha256:[0-9a-f]{64}\"$' AND "
            "source_curation_item_set_hash_version = 'ktm-db-item-set-v1' AND "
            "source_curation_item_set_hash ~ '^[0-9a-f]{64}$' AND "
            "source_curation_item_count BETWEEN 0 AND 2000",
            name=conv("ck_ktm_curation_import_receipts_source"),
        ),
        CheckConstraint(
            "(status = 'pending' AND result_plan_id IS NULL AND response_status IS NULL "
            "AND response_body IS NULL AND completed_at IS NULL) OR "
            "(status = 'completed' AND result_plan_id IS NOT NULL "
            "AND response_status IN (200, 201) AND jsonb_typeof(response_body) = 'object' "
            "AND response_body ->> 'notice_plan_id' = result_plan_id::text "
            "AND response_body ->> 'source_curation_collection_id' = "
            "source_curation_collection_id::text "
            "AND completed_at IS NOT NULL)",
            name=conv("ck_ktm_curation_import_receipts_terminal"),
        ),
        Index(
            "ix_ktm_curation_import_receipts_collection_created",
            "source_curation_collection_id",
            "created_at",
        ),
    )

    receipt_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    actor_admin_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "app.users.user_id",
            name="fk_ktm_curation_import_receipts_actor",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    idempotency_key: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_system: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="kor-travel-map"
    )
    source_curation_collection_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False
    )
    source_curation_collection_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_curation_collection_etag: Mapped[str] = mapped_column(String(128), nullable=False)
    source_curation_item_set_hash_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_curation_item_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_curation_item_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_is_published: Mapped[bool | None] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    result_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
    )
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KtmCurationImportReceiptItem(Base, TimestampMixin):
    """한 import receipt가 검증한 exact Map item membership."""

    __tablename__ = "ktm_curation_import_receipt_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["receipt_id", "source_curation_collection_id"],
            [
                "app.ktm_curation_import_receipts.receipt_id",
                "app.ktm_curation_import_receipts.source_curation_collection_id",
            ],
            name="fk_ktm_curation_import_receipt_items_receipt",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "source_curation_item_revision > 0 AND "
            "source_curation_item_etag ~ '^\"sha256:[0-9a-f]{64}\"$'",
            name=conv("ck_ktm_curation_import_receipt_items_source"),
        ),
        UniqueConstraint(
            "receipt_id",
            "source_curation_collection_id",
            "source_curation_item_id",
            "source_curation_item_revision",
            "source_curation_item_etag",
            "feature_uuid",
            name="uq_ktm_curation_import_receipt_items_proof",
        ),
    )

    receipt_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
    )
    source_curation_collection_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False
    )
    source_curation_item_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
    )
    source_curation_item_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_curation_item_etag: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_uuid: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)


class KtmCurationCutoverMappingReceipt(Base, TimestampMixin):
    """T-VN-40C legacy identity backfill 전 Map mapping export의 sealed receipt."""

    __tablename__ = "ktm_curation_cutover_mapping_receipts"
    __table_args__ = (
        UniqueConstraint(
            "map_release_revision",
            "mapping_root_version",
            "mapping_root",
            name="uq_ktm_curation_cutover_mapping_receipts_map_root",
        ),
        UniqueConstraint(
            "map_release_revision",
            name="uq_ktm_curation_cutover_mapping_receipts_map_release",
        ),
        CheckConstraint(
            "map_release_revision ~ '^[0-9a-f]{40}$'",
            name=conv("ck_ktm_curation_cutover_mapping_receipts_release"),
        ),
        CheckConstraint(
            "mapping_root_version = 'ktm-curation-cutover-mapping-v1' AND "
            "mapping_root ~ '^[0-9a-f]{64}$' AND mapping_count >= 0",
            name=conv("ck_ktm_curation_cutover_mapping_receipts_root"),
        ),
        CheckConstraint(
            "(status = 'pending' AND completed_at IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL)",
            name=conv("ck_ktm_curation_cutover_mapping_receipts_terminal"),
        ),
        Index(
            "ix_ktm_curation_cutover_mapping_receipts_actor_created",
            "actor_admin_id",
            "created_at",
        ),
    )

    receipt_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    actor_admin_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "app.users.user_id",
            name="fk_ktm_curation_cutover_mapping_receipts_actor",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    map_release_revision: Mapped[str] = mapped_column(String(40), nullable=False)
    mapping_root_version: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_root: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KtmCurationCutoverMappingReceiptItem(Base, TimestampMixin):
    """Sealed mapping receipt의 legacy UUID→canonical UUID one-to-one member."""

    __tablename__ = "ktm_curation_cutover_mapping_receipt_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["receipt_id"],
            ["app.ktm_curation_cutover_mapping_receipts.receipt_id"],
            name="fk_ktm_curation_cutover_mapping_receipt_items_receipt",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "mapping_kind IN "
            "('legacy_projection', 'official_membership', 'manual_membership') AND "
            "source_row_hash ~ '^[0-9a-f]{64}$'",
            name=conv("ck_ktm_curation_cutover_mapping_receipt_items_source"),
        ),
        UniqueConstraint(
            "receipt_id",
            "curation_item_id",
            name="uq_ktm_curation_cutover_mapping_receipt_items_curation_item",
        ),
    )

    receipt_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
    )
    legacy_curated_feature_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    curation_item_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    mapping_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_row_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class KtmCurationCutoverBackfillReceipt(Base, TimestampMixin):
    """legacy Map plan을 canonical collection import로 전환한 immutable command receipt."""

    __tablename__ = "ktm_curation_cutover_backfill_receipts"
    __table_args__ = (
        UniqueConstraint(
            "actor_admin_id",
            "idempotency_key",
            name="uq_ktm_curation_cutover_backfill_receipts_actor_key",
        ),
        UniqueConstraint(
            "curated_plan_id",
            name="uq_ktm_curation_cutover_backfill_receipts_plan",
        ),
        UniqueConstraint(
            "import_receipt_id",
            name="uq_ktm_curation_cutover_backfill_receipts_import",
        ),
        ForeignKeyConstraint(
            ["actor_admin_id"],
            ["app.users.user_id"],
            name="fk_ktm_curation_cutover_backfill_receipts_actor",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["mapping_receipt_id"],
            ["app.ktm_curation_cutover_mapping_receipts.receipt_id"],
            name="fk_ktm_curation_cutover_backfill_receipts_mapping",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["mapping_receipt_id", "legacy_curated_feature_id"],
            [
                "app.ktm_curation_cutover_mapping_receipt_items.receipt_id",
                "app.ktm_curation_cutover_mapping_receipt_items.legacy_curated_feature_id",
            ],
            name="fk_ktm_curation_cutover_backfill_receipts_mapping_item",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["curated_plan_id"],
            ["app.curated_trip_plans.curated_plan_id"],
            name="fk_ktm_curation_cutover_backfill_receipts_plan",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["import_receipt_id"],
            ["app.ktm_curation_import_receipts.receipt_id"],
            name="fk_ktm_curation_cutover_backfill_receipts_import",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name=conv("ck_ktm_curation_cutover_backfill_receipts_fingerprint"),
        ),
        CheckConstraint(
            "(status = 'pending' AND import_receipt_id IS NULL AND completed_at IS NULL) OR "
            "(status = 'completed' AND import_receipt_id IS NOT NULL AND completed_at IS NOT NULL)",
            name=conv("ck_ktm_curation_cutover_backfill_receipts_terminal"),
        ),
        Index(
            "ix_ktm_curation_cutover_backfill_receipts_mapping_created",
            "mapping_receipt_id",
            "created_at",
        ),
    )

    receipt_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    actor_admin_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_receipt_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    legacy_curated_feature_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    curated_plan_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    import_receipt_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
