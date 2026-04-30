"""add canonical place tables for public data ETL

Revision ID: 20260427_0015
Revises: 20260427_0013
Create Date: 2026-04-27 23:40:00
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260427_0015"
down_revision: str | None = "20260427_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "place_categories",
        sa.Column("category_code", sa.String(length=8), nullable=False),
        sa.Column("tier1_code", sa.String(length=2), nullable=False),
        sa.Column("tier2_code", sa.String(length=2), nullable=False),
        sa.Column("tier3_code", sa.String(length=2), nullable=False),
        sa.Column("tier4_code", sa.String(length=2), nullable=False),
        sa.Column("tier1_name", sa.String(length=80), nullable=False),
        sa.Column("tier2_name", sa.String(length=80), nullable=True),
        sa.Column("tier3_name", sa.String(length=80), nullable=True),
        sa.Column("tier4_name", sa.String(length=120), nullable=True),
        sa.Column("depth", sa.SmallInteger(), nullable=False),
        sa.Column("parent_category_code", sa.String(length=8), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("category_code ~ '^[0-9]{8}$'", name="ck_place_category_code_format"),
        sa.ForeignKeyConstraint(
            ["parent_category_code"],
            ["place_categories.category_code"],
            name="fk_place_categories_parent_category_code",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("category_code", name="pk_place_categories"),
    )
    op.create_index("ix_place_categories_parent", "place_categories", ["parent_category_code"])
    _seed_place_categories()

    op.create_table(
        "places",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("parent_place_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("place_kind", sa.String(length=40), nullable=False),
        sa.Column("primary_category_code", sa.String(length=8), nullable=False),
        sa.Column("legal_dong_code", sa.String(length=10), nullable=True),
        sa.Column("road_name_code", sa.String(length=12), nullable=True),
        sa.Column("administrative_dong_code", sa.String(length=10), nullable=True),
        sa.Column("road_address_management_no", sa.String(length=64), nullable=True),
        sa.Column("road_address", sa.String(length=500), nullable=True),
        sa.Column("jibun_address", sa.String(length=500), nullable=True),
        sa.Column("detail_address", sa.String(length=255), nullable=True),
        sa.Column("address_snapshot", sa.String(length=700), nullable=False),
        sa.Column("address_resolution_status", sa.String(length=32), nullable=False),
        sa.Column("longitude", sa.Numeric(12, 8), nullable=False),
        sa.Column("latitude", sa.Numeric(12, 8), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.Column("business_registration_no", sa.String(length=20), nullable=True),
        sa.Column("opened_on", sa.Date(), nullable=True),
        sa.Column("closed_on", sa.Date(), nullable=True),
        sa.Column("operation_status", sa.String(length=32), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("quality_score", sa.Integer(), nullable=True),
        sa.Column("is_searchable", sa.Boolean(), nullable=False),
        sa.Column("is_map_visible", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "source_specific_attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "parent_place_id IS NULL OR parent_place_id <> id", name="ck_place_not_self"
        ),
        sa.ForeignKeyConstraint(
            ["legal_dong_code"],
            ["address_code_standard.legal_dong_code"],
            name="fk_places_legal_dong_code",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["parent_place_id"],
            ["places.id"],
            name="fk_places_parent_place_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["primary_category_code"],
            ["place_categories.category_code"],
            name="fk_places_primary_category_code",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_places"),
        sa.UniqueConstraint("public_id", name="uq_places_public_id"),
    )
    op.create_index("ix_places_public_id", "places", ["public_id"])
    op.create_index("ix_places_parent_place_id", "places", ["parent_place_id"])
    op.create_index("ix_places_primary_category", "places", ["primary_category_code"])
    op.create_index("ix_places_legal_dong", "places", ["legal_dong_code"])
    op.create_index("ix_places_road_name_code", "places", ["road_name_code"])
    op.create_index("ix_places_searchable_status", "places", ["operation_status", "is_searchable"])
    op.create_index("ix_places_geom", "places", ["geom"], postgresql_using="gist")

    op.create_table(
        "place_source_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_key", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("source_record_id", sa.String(length=255), nullable=False),
        sa.Column("source_version", sa.String(length=80), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_payload_hash", sa.String(length=128), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_place_source_records"),
        sa.UniqueConstraint(
            "dataset_key",
            "source_record_id",
            "raw_payload_hash",
            name="uq_place_source_records_dataset_record_hash",
        ),
    )
    op.create_index(
        "ix_place_source_records_dataset_record",
        "place_source_records",
        ["dataset_key", "source_record_id"],
    )
    op.create_index(
        "ix_place_source_records_collected_at",
        "place_source_records",
        ["collected_at"],
    )

    op.create_table(
        "place_source_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("place_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_method", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("is_primary_source", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["place_id"],
            ["places.id"],
            name="fk_place_source_links_place_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["place_source_records.id"],
            name="fk_place_source_links_source_record_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_place_source_links"),
        sa.UniqueConstraint(
            "place_id", "source_record_id", name="uq_place_source_links_place_source"
        ),
    )
    op.create_index("ix_place_source_links_place_id", "place_source_links", ["place_id"])
    op.create_index(
        "ix_place_source_links_source_record_id",
        "place_source_links",
        ["source_record_id"],
    )

    op.create_table(
        "place_provider_refs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("place_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_place_id", sa.String(length=255), nullable=True),
        sa.Column("provider_dataset_key", sa.String(length=120), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("stable_name", sa.String(length=255), nullable=True),
        sa.Column("stable_address", sa.String(length=500), nullable=True),
        sa.Column("stable_phone", sa.String(length=80), nullable=True),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["place_id"],
            ["places.id"],
            name="fk_place_provider_refs_place_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_place_provider_refs"),
        sa.UniqueConstraint(
            "provider",
            "provider_dataset_key",
            "provider_place_id",
            name="uq_place_provider_refs_provider_dataset_place",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_place_provider_refs_place_id", "place_provider_refs", ["place_id"])
    op.create_index(
        "ix_place_provider_refs_provider_place",
        "place_provider_refs",
        ["provider", "provider_place_id"],
    )

    op.create_table(
        "place_web_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("place_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_type", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["place_id"],
            ["places.id"],
            name="fk_place_web_links_place_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_place_web_links"),
        sa.UniqueConstraint("place_id", "url", name="uq_place_web_links_place_url"),
    )
    op.create_index("ix_place_web_links_place_id", "place_web_links", ["place_id"])


def downgrade() -> None:
    op.drop_index("ix_place_web_links_place_id", table_name="place_web_links")
    op.drop_table("place_web_links")
    op.drop_index("ix_place_provider_refs_provider_place", table_name="place_provider_refs")
    op.drop_index("ix_place_provider_refs_place_id", table_name="place_provider_refs")
    op.drop_table("place_provider_refs")
    op.drop_index("ix_place_source_links_source_record_id", table_name="place_source_links")
    op.drop_index("ix_place_source_links_place_id", table_name="place_source_links")
    op.drop_table("place_source_links")
    op.drop_index("ix_place_source_records_collected_at", table_name="place_source_records")
    op.drop_index("ix_place_source_records_dataset_record", table_name="place_source_records")
    op.drop_table("place_source_records")
    op.drop_index("ix_places_geom", table_name="places")
    op.drop_index("ix_places_searchable_status", table_name="places")
    op.drop_index("ix_places_road_name_code", table_name="places")
    op.drop_index("ix_places_legal_dong", table_name="places")
    op.drop_index("ix_places_primary_category", table_name="places")
    op.drop_index("ix_places_parent_place_id", table_name="places")
    op.drop_index("ix_places_public_id", table_name="places")
    op.drop_table("places")
    op.drop_index("ix_place_categories_parent", table_name="place_categories")
    op.drop_table("place_categories")


def _seed_place_categories() -> None:
    table = sa.table(
        "place_categories",
        sa.column("category_code"),
        sa.column("tier1_code"),
        sa.column("tier2_code"),
        sa.column("tier3_code"),
        sa.column("tier4_code"),
        sa.column("tier1_name"),
        sa.column("tier2_name"),
        sa.column("tier3_name"),
        sa.column("tier4_name"),
        sa.column("depth"),
        sa.column("parent_category_code"),
        sa.column("sort_order"),
        sa.column("is_active"),
        sa.column("created_at"),
        sa.column("updated_at"),
    )
    now = datetime.now(UTC)
    rows = [
        _cat("00000000", "미분류", None, None, None, 0, None, 0, now),
        _cat("01000000", "관광", None, None, None, 1, None, 10, now),
        _cat("01030000", "관광", "수목원·식물원", None, None, 2, "01000000", 30, now),
        _cat("01030100", "관광", "수목원·식물원", "수목원", None, 3, "01030000", 31, now),
        _cat("01030101", "관광", "수목원·식물원", "수목원", "국립수목원", 4, "01030100", 311, now),
        _cat("01030102", "관광", "수목원·식물원", "수목원", "공립수목원", 4, "01030100", 312, now),
        _cat("01030103", "관광", "수목원·식물원", "수목원", "사립수목원", 4, "01030100", 313, now),
        _cat("01040000", "관광", "문화시설", None, None, 2, "01000000", 40, now),
        _cat("01040100", "관광", "문화시설", "박물관", None, 3, "01040000", 41, now),
        _cat("01040101", "관광", "문화시설", "박물관", "국공립 박물관", 4, "01040100", 411, now),
        _cat("01040102", "관광", "문화시설", "박물관", "사립 박물관", 4, "01040100", 412, now),
        _cat("01040103", "관광", "문화시설", "박물관", "테마 박물관", 4, "01040100", 413, now),
        _cat("01040200", "관광", "문화시설", "미술관·갤러리", None, 3, "01040000", 42, now),
        _cat("01040201", "관광", "문화시설", "미술관·갤러리", "미술관", 4, "01040200", 421, now),
        _cat("01040202", "관광", "문화시설", "미술관·갤러리", "갤러리", 4, "01040200", 422, now),
        _cat("03000000", "숙박", None, None, None, 1, None, 300, now),
        _cat("03030000", "숙박", "휴양림", None, None, 2, "03000000", 330, now),
        _cat("03030100", "숙박", "휴양림", "국립휴양림", None, 3, "03030000", 331, now),
        _cat("03030101", "숙박", "휴양림", "국립휴양림", "산림청 운영", 4, "03030100", 3311, now),
        _cat("03030200", "숙박", "휴양림", "공립휴양림", None, 3, "03030000", 332, now),
        _cat("03030201", "숙박", "휴양림", "공립휴양림", "지자체 운영", 4, "03030200", 3321, now),
        _cat("03030300", "숙박", "휴양림", "사립휴양림", None, 3, "03030000", 333, now),
        _cat("03030301", "숙박", "휴양림", "사립휴양림", "민간 운영", 4, "03030300", 3331, now),
        _cat("03060000", "숙박", "캠핑장", None, None, 2, "03000000", 360, now),
        _cat("03060100", "숙박", "캠핑장", "오토캠핑장", None, 3, "03060000", 361, now),
        _cat("03060101", "숙박", "캠핑장", "오토캠핑장", "일반 사이트", 4, "03060100", 3611, now),
        _cat(
            "03060102",
            "숙박",
            "캠핑장",
            "오토캠핑장",
            "카라반·캠핑카 사이트",
            4,
            "03060100",
            3612,
            now,
        ),
        _cat("03060200", "숙박", "캠핑장", "글램핑·카라반", None, 3, "03060000", 362, now),
        _cat("03060201", "숙박", "캠핑장", "글램핑·카라반", "글램핑", 4, "03060200", 3621, now),
        _cat(
            "03060202", "숙박", "캠핑장", "글램핑·카라반", "카라반 대여", 4, "03060200", 3622, now
        ),
    ]
    op.bulk_insert(table, rows)


def _cat(
    category_code: str,
    tier1_name: str,
    tier2_name: str | None,
    tier3_name: str | None,
    tier4_name: str | None,
    depth: int,
    parent_category_code: str | None,
    sort_order: int,
    now: datetime,
) -> dict[str, object]:
    return {
        "category_code": category_code,
        "tier1_code": category_code[0:2],
        "tier2_code": category_code[2:4],
        "tier3_code": category_code[4:6],
        "tier4_code": category_code[6:8],
        "tier1_name": tier1_name,
        "tier2_name": tier2_name,
        "tier3_name": tier3_name,
        "tier4_name": tier4_name,
        "depth": depth,
        "parent_category_code": parent_category_code,
        "sort_order": sort_order,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
