"""replace places with map feature schema

Revision ID: 20260429_0021
Revises: 20260428_0020
Create Date: 2026-04-29 16:00:00
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260429_0021"
down_revision: str | None = "20260428_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    _rename_place_source_records()
    _rename_places_to_map_features()
    _rename_place_link_tables()
    _create_map_feature_detail_tables()
    _create_content_and_support_tables()
    _retarget_existing_feature_references()


def downgrade() -> None:
    raise NotImplementedError(
        "map feature schema replacement is destructive and has no automated downgrade."
    )


def _rename_place_source_records() -> None:
    op.rename_table("place_source_records", "source_records")
    op.drop_index("ix_place_source_records_dataset_record", table_name="source_records")
    op.drop_index("ix_place_source_records_collected_at", table_name="source_records")
    op.drop_constraint(
        "uq_place_source_records_dataset_record_hash",
        "source_records",
        type_="unique",
    )
    op.alter_column(
        "source_records",
        "source_record_id",
        new_column_name="source_entity_id",
        existing_type=sa.String(length=255),
    )
    op.alter_column(
        "source_records",
        "raw_payload",
        new_column_name="raw_data",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
    )
    op.alter_column(
        "source_records",
        "collected_at",
        new_column_name="fetched_at",
        existing_type=sa.DateTime(timezone=True),
    )
    op.add_column(
        "source_records",
        sa.Column("source_entity_type", sa.String(length=32), server_default="place"),
    )
    op.add_column("source_records", sa.Column("raw_name", sa.String(length=255)))
    op.add_column("source_records", sa.Column("raw_address", sa.String(length=700)))
    op.add_column("source_records", sa.Column("raw_longitude", sa.Numeric(12, 8)))
    op.add_column("source_records", sa.Column("raw_latitude", sa.Numeric(12, 8)))
    op.add_column(
        "source_records",
        sa.Column(
            "raw_geom",
            geoalchemy2.Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
        ),
    )
    op.add_column("source_records", sa.Column("raw_start_date", sa.Date()))
    op.add_column("source_records", sa.Column("raw_end_date", sa.Date()))
    op.add_column("source_records", sa.Column("imported_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE source_records SET imported_at = fetched_at")
    op.alter_column("source_records", "source_entity_type", nullable=False)
    op.alter_column("source_records", "imported_at", nullable=False)
    op.alter_column("source_records", "source_entity_type", server_default=None)
    op.drop_column("source_records", "created_at")
    op.drop_column("source_records", "updated_at")
    op.create_unique_constraint(
        "uq_source_records_provider_dataset_entity_hash",
        "source_records",
        [
            "provider",
            "dataset_key",
            "source_entity_type",
            "source_entity_id",
            "raw_payload_hash",
        ],
    )
    op.create_index(
        "ix_source_records_provider_dataset",
        "source_records",
        ["provider", "dataset_key"],
    )
    op.create_index(
        "ix_source_records_entity",
        "source_records",
        ["source_entity_type", "source_entity_id"],
    )
    op.create_index("ix_source_records_imported_at", "source_records", ["imported_at"])
    op.create_index(
        "ix_source_records_raw_geom",
        "source_records",
        ["raw_geom"],
        postgresql_using="gist",
    )


def _rename_places_to_map_features() -> None:
    op.rename_table("places", "map_features")
    op.drop_index("ix_places_public_id", table_name="map_features")
    op.drop_index("ix_places_parent_place_id", table_name="map_features")
    op.drop_index("ix_places_primary_category", table_name="map_features")
    op.drop_index("ix_places_legal_dong", table_name="map_features")
    op.drop_index("ix_places_road_name_code", table_name="map_features")
    op.drop_index("ix_places_searchable_status", table_name="map_features")
    op.drop_index("ix_places_geom", table_name="map_features")
    op.drop_constraint(op.f("ck_places_ck_place_not_self"), "map_features", type_="check")
    op.drop_constraint("fk_places_parent_place_id", "map_features", type_="foreignkey")
    op.drop_constraint("fk_places_primary_category_code", "map_features", type_="foreignkey")
    op.drop_constraint("fk_places_legal_dong_code", "map_features", type_="foreignkey")
    op.drop_constraint("uq_places_public_id", "map_features", type_="unique")

    op.alter_column(
        "map_features",
        "parent_place_id",
        new_column_name="parent_feature_id",
        existing_type=postgresql.UUID(as_uuid=True),
    )
    op.alter_column(
        "map_features",
        "primary_category_code",
        new_column_name="category_code",
        existing_type=sa.String(length=8),
    )
    op.alter_column(
        "map_features",
        "administrative_dong_code",
        new_column_name="admin_dong_code",
        existing_type=sa.String(length=10),
    )
    op.alter_column(
        "map_features",
        "address_snapshot",
        new_column_name="address",
        existing_type=sa.String(length=700),
    )
    op.alter_column(
        "map_features",
        "is_map_visible",
        new_column_name="is_visible",
        existing_type=sa.Boolean(),
    )
    op.alter_column(
        "map_features",
        "source_specific_attributes",
        new_column_name="extra",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
    )
    op.add_column("map_features", sa.Column("feature_type", sa.String(length=32)))
    op.add_column("map_features", sa.Column("subtitle", sa.String(length=255)))
    op.add_column("map_features", sa.Column("summary", sa.Text()))
    op.add_column("map_features", sa.Column("description", sa.Text()))
    op.add_column("map_features", sa.Column("category_name", sa.String(length=120)))
    op.add_column("map_features", sa.Column("geometry_kind", sa.String(length=16)))
    op.add_column(
        "map_features",
        sa.Column(
            "centroid",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        ),
    )
    op.add_column("map_features", sa.Column("sido_code", sa.String(length=10)))
    op.add_column("map_features", sa.Column("sigungu_code", sa.String(length=10)))
    op.add_column("map_features", sa.Column("website_url", sa.Text()))
    op.add_column("map_features", sa.Column("search_text", postgresql.TSVECTOR()))
    op.add_column("map_features", sa.Column("popularity_score", sa.Numeric(10, 3)))
    op.add_column("map_features", sa.Column("priority_score", sa.Numeric(10, 3)))
    op.add_column("map_features", sa.Column("status", sa.String(length=32)))
    op.add_column(
        "map_features",
        sa.Column("primary_source_record_id", postgresql.UUID(as_uuid=True)),
    )
    op.execute(
        """
        UPDATE map_features
        SET
            feature_type = 'place',
            geometry_kind = 'point',
            centroid = geom,
            popularity_score = 0,
            priority_score = 0,
            status = CASE
                WHEN is_active IS FALSE THEN 'deleted'
                WHEN operation_status = 'closed' THEN 'inactive'
                ELSE 'active'
            END,
            is_visible = is_visible AND is_searchable,
            sido_code = CASE
                WHEN legal_dong_code IS NULL THEN NULL
                ELSE substring(legal_dong_code from 1 for 2) || '00000000'
            END,
            sigungu_code = CASE
                WHEN legal_dong_code IS NULL THEN NULL
                ELSE substring(legal_dong_code from 1 for 5) || '00000'
            END
        """
    )
    op.alter_column("map_features", "feature_type", nullable=False)
    op.alter_column("map_features", "geometry_kind", nullable=False)
    op.alter_column("map_features", "centroid", nullable=False)
    op.alter_column("map_features", "popularity_score", nullable=False)
    op.alter_column("map_features", "priority_score", nullable=False)
    op.alter_column("map_features", "status", nullable=False)
    op.alter_column(
        "map_features",
        "name",
        type_=sa.String(length=255),
        existing_type=sa.String(length=200),
    )
    op.alter_column(
        "map_features",
        "display_name",
        type_=sa.String(length=255),
        existing_type=sa.String(length=200),
    )
    op.alter_column(
        "map_features",
        "normalized_name",
        type_=sa.String(length=255),
        existing_type=sa.String(length=200),
    )
    op.alter_column(
        "map_features",
        "phone",
        type_=sa.String(length=120),
        existing_type=sa.String(length=80),
    )
    op.create_check_constraint(
        op.f("ck_map_features_feature_type"),
        "map_features",
        "feature_type IN ('place', 'event', 'route', 'area', 'notice')",
    )
    op.create_check_constraint(
        op.f("ck_map_features_geometry_kind"),
        "map_features",
        "geometry_kind IN ('point', 'line', 'polygon', 'mixed')",
    )
    op.create_check_constraint(
        op.f("ck_map_features_status"),
        "map_features",
        "status IN ('draft', 'active', 'inactive', 'temporarily_closed', 'deleted')",
    )
    op.create_check_constraint(
        op.f("ck_map_features_not_self_parent"),
        "map_features",
        "parent_feature_id IS NULL OR parent_feature_id <> id",
    )
    op.create_foreign_key(
        "fk_map_features_parent_feature_id",
        "map_features",
        "map_features",
        ["parent_feature_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_map_features_category_code",
        "map_features",
        "place_categories",
        ["category_code"],
        ["category_code"],
    )
    op.create_foreign_key(
        "fk_map_features_legal_dong_code",
        "map_features",
        "address_code_standard",
        ["legal_dong_code"],
        ["legal_dong_code"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_map_features_primary_source_record_id",
        "map_features",
        "source_records",
        ["primary_source_record_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint("uq_map_features_public_id", "map_features", ["public_id"])
    op.create_index("ix_map_features_public_id", "map_features", ["public_id"])
    op.create_index("ix_map_features_parent_feature_id", "map_features", ["parent_feature_id"])
    op.create_index("ix_map_features_type", "map_features", ["feature_type"])
    op.create_index("ix_map_features_status_visible", "map_features", ["status", "is_visible"])
    op.create_index("ix_map_features_category", "map_features", ["category_code"])
    op.create_index("ix_map_features_legal_dong", "map_features", ["legal_dong_code"])
    op.create_index("ix_map_features_sigungu", "map_features", ["sigungu_code"])
    op.create_index(
        "ix_map_features_primary_source_record",
        "map_features",
        ["primary_source_record_id"],
    )
    op.create_index("ix_map_features_geom", "map_features", ["geom"], postgresql_using="gist")
    op.create_index(
        "ix_map_features_centroid",
        "map_features",
        ["centroid"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_map_features_search",
        "map_features",
        ["search_text"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_map_features_name_trgm",
        "map_features",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )


def _rename_place_link_tables() -> None:
    op.rename_table("place_source_links", "map_feature_source_links")
    op.rename_table("place_provider_refs", "map_feature_provider_refs")
    op.rename_table("place_web_links", "map_feature_web_links")

    op.drop_index("ix_place_source_links_place_id", table_name="map_feature_source_links")
    op.drop_index(
        "ix_place_source_links_source_record_id",
        table_name="map_feature_source_links",
    )
    op.drop_constraint(
        "uq_place_source_links_place_source",
        "map_feature_source_links",
        type_="unique",
    )
    op.drop_constraint(
        "fk_place_source_links_place_id",
        "map_feature_source_links",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_place_source_links_source_record_id",
        "map_feature_source_links",
        type_="foreignkey",
    )
    op.alter_column(
        "map_feature_source_links",
        "place_id",
        new_column_name="feature_id",
        existing_type=postgresql.UUID(as_uuid=True),
    )
    op.create_foreign_key(
        "fk_map_feature_source_links_feature_id",
        "map_feature_source_links",
        "map_features",
        ["feature_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_map_feature_source_links_source_record_id",
        "map_feature_source_links",
        "source_records",
        ["source_record_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_map_feature_source_links_feature_source",
        "map_feature_source_links",
        ["feature_id", "source_record_id"],
    )
    op.create_check_constraint(
        op.f("ck_map_feature_source_links_confidence"),
        "map_feature_source_links",
        "confidence >= 0 AND confidence <= 100",
    )
    op.create_index(
        "ix_map_feature_source_links_feature",
        "map_feature_source_links",
        ["feature_id"],
    )
    op.create_index(
        "ix_map_feature_source_links_source",
        "map_feature_source_links",
        ["source_record_id"],
    )

    op.drop_index("ix_place_provider_refs_place_id", table_name="map_feature_provider_refs")
    op.drop_index(
        "ix_place_provider_refs_provider_place",
        table_name="map_feature_provider_refs",
    )
    op.drop_constraint(
        "uq_place_provider_refs_provider_dataset_place",
        "map_feature_provider_refs",
        type_="unique",
    )
    op.drop_constraint(
        "fk_place_provider_refs_place_id",
        "map_feature_provider_refs",
        type_="foreignkey",
    )
    op.alter_column(
        "map_feature_provider_refs",
        "place_id",
        new_column_name="feature_id",
        existing_type=postgresql.UUID(as_uuid=True),
    )
    op.alter_column(
        "map_feature_provider_refs",
        "provider_place_id",
        new_column_name="provider_feature_id",
        existing_type=sa.String(length=255),
    )
    op.alter_column(
        "map_feature_provider_refs",
        "stable_phone",
        type_=sa.String(length=120),
        existing_type=sa.String(length=80),
    )
    op.create_foreign_key(
        "fk_map_feature_provider_refs_feature_id",
        "map_feature_provider_refs",
        "map_features",
        ["feature_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_map_feature_provider_refs_provider_dataset_feature",
        "map_feature_provider_refs",
        ["provider", "provider_dataset_key", "provider_feature_id"],
        postgresql_nulls_not_distinct=True,
    )
    op.create_index(
        "ix_map_feature_provider_refs_feature",
        "map_feature_provider_refs",
        ["feature_id"],
    )
    op.create_index(
        "ix_map_feature_provider_refs_provider_feature",
        "map_feature_provider_refs",
        ["provider", "provider_feature_id"],
    )

    op.drop_index("ix_place_web_links_place_id", table_name="map_feature_web_links")
    op.drop_constraint(
        "uq_place_web_links_place_url",
        "map_feature_web_links",
        type_="unique",
    )
    op.drop_constraint(
        "fk_place_web_links_place_id",
        "map_feature_web_links",
        type_="foreignkey",
    )
    op.alter_column(
        "map_feature_web_links",
        "place_id",
        new_column_name="feature_id",
        existing_type=postgresql.UUID(as_uuid=True),
    )
    op.create_foreign_key(
        "fk_map_feature_web_links_feature_id",
        "map_feature_web_links",
        "map_features",
        ["feature_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_map_feature_web_links_feature_url",
        "map_feature_web_links",
        ["feature_id", "url"],
    )
    op.create_index(
        "ix_map_feature_web_links_feature",
        "map_feature_web_links",
        ["feature_id"],
    )

    op.execute(
        """
        UPDATE map_features mf
        SET primary_source_record_id = link.source_record_id
        FROM map_feature_source_links link
        WHERE link.feature_id = mf.id
          AND link.is_primary_source IS TRUE
        """
    )


def _create_map_feature_detail_tables() -> None:
    op.create_table(
        "place_details",
        sa.Column("feature_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("place_kind", sa.String(length=40), nullable=False),
        sa.Column("opening_hours", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("closed_days", sa.Text()),
        sa.Column("admission_fee", sa.Text()),
        sa.Column("price_level", sa.SmallInteger()),
        sa.Column("reservation_required", sa.Boolean()),
        sa.Column("reservation_url", sa.Text()),
        sa.Column("parking_available", sa.Boolean()),
        sa.Column("pet_allowed", sa.Boolean()),
        sa.Column("stroller_accessible", sa.Boolean()),
        sa.Column("wheelchair_accessible", sa.Boolean()),
        sa.Column("indoor", sa.Boolean()),
        sa.Column("outdoor", sa.Boolean()),
        sa.Column("checkin_time", sa.Time()),
        sa.Column("checkout_time", sa.Time()),
        sa.Column("recommended_duration_min", sa.Integer()),
        sa.Column("operation_status", sa.String(length=32), nullable=False),
        sa.Column("address_resolution_status", sa.String(length=32), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("quality_score", sa.Integer()),
        sa.Column("opened_on", sa.Date()),
        sa.Column("closed_on", sa.Date()),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "place_kind IN ("
            "'tourist_spot', 'restaurant', 'cafe', 'hotel', "
            "'parking', 'toilet', 'ev_charger', 'viewpoint'"
            ")",
            name=op.f("ck_place_details_place_kind"),
        ),
        sa.CheckConstraint(
            "price_level IS NULL OR price_level BETWEEN 0 AND 5",
            name=op.f("ck_place_details_price_level"),
        ),
        sa.CheckConstraint(
            "recommended_duration_min IS NULL OR recommended_duration_min >= 0",
            name=op.f("ck_place_details_recommended_duration"),
        ),
        sa.ForeignKeyConstraint(
            ["feature_id"],
            ["map_features.id"],
            name="fk_place_details_feature_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("feature_id", name="pk_place_details"),
    )
    op.create_index("ix_place_details_place_kind", "place_details", ["place_kind"])
    op.execute(
        """
        INSERT INTO place_details (
            feature_id,
            place_kind,
            operation_status,
            address_resolution_status,
            verification_status,
            quality_score,
            opened_on,
            closed_on,
            extra,
            created_at,
            updated_at
        )
        SELECT
            id,
            CASE WHEN category_code LIKE '03%' THEN 'hotel' ELSE 'tourist_spot' END,
            operation_status,
            address_resolution_status,
            verification_status,
            quality_score,
            opened_on,
            closed_on,
            extra,
            created_at,
            updated_at
        FROM map_features
        WHERE feature_type = 'place'
        """
    )
    op.drop_column("map_features", "place_kind")
    op.drop_column("map_features", "detail_address")
    op.drop_column("map_features", "business_registration_no")
    op.drop_column("map_features", "opened_on")
    op.drop_column("map_features", "closed_on")
    op.drop_column("map_features", "operation_status")
    op.drop_column("map_features", "address_resolution_status")
    op.drop_column("map_features", "verification_status")
    op.drop_column("map_features", "quality_score")
    op.drop_column("map_features", "is_searchable")
    op.drop_column("map_features", "is_active")

    op.create_table(
        "event_details",
        sa.Column("feature_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_kind", sa.String(length=40), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time()),
        sa.Column("end_time", sa.Time()),
        sa.Column("venue_name", sa.Text()),
        sa.Column("venue_feature_id", postgresql.UUID(as_uuid=True)),
        sa.Column("organizer", sa.Text()),
        sa.Column("host", sa.Text()),
        sa.Column("sponsor", sa.Text()),
        sa.Column("contact_phone", sa.Text()),
        sa.Column("official_url", sa.Text()),
        sa.Column("reservation_url", sa.Text()),
        sa.Column("fee_info", sa.Text()),
        sa.Column("is_free", sa.Boolean()),
        sa.Column("age_limit", sa.Text()),
        sa.Column("is_cancelled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cancellation_reason", sa.Text()),
        sa.Column("recurrence_rule", sa.Text()),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_kind IN ('festival', 'performance', 'exhibition', 'market', 'activity')",
            name=op.f("ck_event_details_event_kind"),
        ),
        sa.CheckConstraint("end_date >= start_date", name=op.f("ck_event_details_date_range")),
        sa.CheckConstraint(
            "end_time IS NULL OR start_time IS NULL OR end_time >= start_time",
            name=op.f("ck_event_details_time_range"),
        ),
        sa.ForeignKeyConstraint(
            ["feature_id"],
            ["map_features.id"],
            name="fk_event_details_feature_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["venue_feature_id"],
            ["map_features.id"],
            name="fk_event_details_venue_feature_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("feature_id", name="pk_event_details"),
    )
    op.create_index("ix_event_details_event_kind", "event_details", ["event_kind"])
    op.create_index("ix_event_details_period", "event_details", ["start_date", "end_date"])
    op.create_index(
        "ix_event_details_venue_feature_id",
        "event_details",
        ["venue_feature_id"],
    )

    op.create_table(
        "route_details",
        sa.Column("feature_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("route_kind", sa.String(length=40), nullable=False),
        sa.Column("distance_m", sa.Integer()),
        sa.Column("duration_min", sa.Integer()),
        sa.Column("difficulty", sa.String(length=32)),
        sa.Column("start_name", sa.Text()),
        sa.Column("end_name", sa.Text()),
        sa.Column("start_feature_id", postgresql.UUID(as_uuid=True)),
        sa.Column("end_feature_id", postgresql.UUID(as_uuid=True)),
        sa.Column("elevation_gain_m", sa.Integer()),
        sa.Column("elevation_loss_m", sa.Integer()),
        sa.Column("min_elevation_m", sa.Integer()),
        sa.Column("max_elevation_m", sa.Integer()),
        sa.Column("is_loop", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("recommended_season", sa.Text()),
        sa.Column("surface_type", sa.String(length=32)),
        sa.Column("accessibility_note", sa.Text()),
        sa.Column("safety_note", sa.Text()),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "route_kind IN ('walking', 'hiking', 'cycling', 'driving', 'scenic')",
            name=op.f("ck_route_details_route_kind"),
        ),
        sa.CheckConstraint(
            "distance_m IS NULL OR distance_m >= 0",
            name=op.f("ck_route_details_distance"),
        ),
        sa.CheckConstraint(
            "duration_min IS NULL OR duration_min >= 0",
            name=op.f("ck_route_details_duration"),
        ),
        sa.ForeignKeyConstraint(
            ["feature_id"],
            ["map_features.id"],
            name="fk_route_details_feature_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["start_feature_id"],
            ["map_features.id"],
            name="fk_route_details_start_feature_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["end_feature_id"],
            ["map_features.id"],
            name="fk_route_details_end_feature_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("feature_id", name="pk_route_details"),
    )
    op.create_index("ix_route_details_route_kind", "route_details", ["route_kind"])
    op.create_index("ix_route_details_start_feature_id", "route_details", ["start_feature_id"])
    op.create_index("ix_route_details_end_feature_id", "route_details", ["end_feature_id"])

    op.create_table(
        "route_waypoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("route_feature_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("related_feature_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("seq >= 1", name=op.f("ck_route_waypoints_positive_seq")),
        sa.ForeignKeyConstraint(
            ["route_feature_id"],
            ["route_details.feature_id"],
            name="fk_route_waypoints_route_feature_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["related_feature_id"],
            ["map_features.id"],
            name="fk_route_waypoints_related_feature_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_route_waypoints"),
        sa.UniqueConstraint(
            "route_feature_id",
            "seq",
            name="uq_route_waypoints_route_seq",
        ),
    )
    op.create_index("ix_route_waypoints_route_seq", "route_waypoints", ["route_feature_id", "seq"])
    op.create_index(
        "ix_route_waypoints_related_feature_id",
        "route_waypoints",
        ["related_feature_id"],
    )
    op.create_index(
        "ix_route_waypoints_geom",
        "route_waypoints",
        ["geom"],
        postgresql_using="gist",
    )

    op.create_table(
        "area_details",
        sa.Column("feature_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("area_kind", sa.String(length=40), nullable=False),
        sa.Column("managing_org", sa.Text()),
        sa.Column("contact_phone", sa.Text()),
        sa.Column("website_url", sa.Text()),
        sa.Column("rules", sa.Text()),
        sa.Column("fee_info", sa.Text()),
        sa.Column("open_season_start", sa.Date()),
        sa.Column("open_season_end", sa.Date()),
        sa.Column("area_size_m2", sa.Numeric(16, 2)),
        sa.Column("is_restricted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("restriction_note", sa.Text()),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "area_kind IN ("
            "'national_park', 'beach', 'tourism_zone', "
            "'market_area', 'restricted_area'"
            ")",
            name=op.f("ck_area_details_area_kind"),
        ),
        sa.CheckConstraint(
            "area_size_m2 IS NULL OR area_size_m2 >= 0",
            name=op.f("ck_area_details_size"),
        ),
        sa.ForeignKeyConstraint(
            ["feature_id"],
            ["map_features.id"],
            name="fk_area_details_feature_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("feature_id", name="pk_area_details"),
    )
    op.create_index("ix_area_details_area_kind", "area_details", ["area_kind"])
    op.create_index("ix_area_details_restricted", "area_details", ["is_restricted"])

    op.create_table(
        "notice_details",
        sa.Column("feature_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notice_kind", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("related_feature_id", postgresql.UUID(as_uuid=True)),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("source_url", sa.Text()),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "notice_kind IN ("
            "'closure', 'construction', 'traffic_control', "
            "'congestion', 'weather_warning'"
            ")",
            name=op.f("ck_notice_details_notice_kind"),
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name=op.f("ck_notice_details_severity"),
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name=op.f("ck_notice_details_valid_period"),
        ),
        sa.CheckConstraint(
            "resolved_at IS NULL OR is_resolved = true",
            name=op.f("ck_notice_details_resolved_at"),
        ),
        sa.ForeignKeyConstraint(
            ["feature_id"],
            ["map_features.id"],
            name="fk_notice_details_feature_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["related_feature_id"],
            ["map_features.id"],
            name="fk_notice_details_related_feature_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("feature_id", name="pk_notice_details"),
    )
    op.create_index("ix_notice_details_notice_kind", "notice_details", ["notice_kind"])
    op.create_index("ix_notice_details_severity", "notice_details", ["severity"])
    op.create_index(
        "ix_notice_details_related_feature_id",
        "notice_details",
        ["related_feature_id"],
    )
    op.create_index(
        "ix_notice_details_active",
        "notice_details",
        ["is_resolved", "valid_from", "valid_to"],
    )


def _create_content_and_support_tables() -> None:
    op.create_table(
        "content_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("subtitle", sa.String(length=255)),
        sa.Column("summary", sa.Text()),
        sa.Column("body", sa.Text()),
        sa.Column("slug", sa.String(length=255)),
        sa.Column("author_name", sa.String(length=120)),
        sa.Column("source_provider", sa.String(length=40)),
        sa.Column("source_url", sa.Text()),
        sa.Column("publish_start_at", sa.DateTime(timezone=True)),
        sa.Column("publish_end_at", sa.DateTime(timezone=True)),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("priority_score", sa.Numeric(10, 3), nullable=False, server_default="0"),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "content_kind IN ('article', 'curated_list', 'itinerary_template', 'guide')",
            name=op.f("ck_content_items_content_kind"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_content_items"),
        sa.UniqueConstraint("slug", name="uq_content_items_slug"),
    )
    op.create_index("ix_content_items_kind", "content_items", ["content_kind"])
    op.create_index(
        "ix_content_items_published",
        "content_items",
        ["is_published", "publish_start_at", "publish_end_at"],
    )
    op.create_index("ix_content_items_slug", "content_items", ["slug"])
    op.create_index(
        "ix_content_items_title_trgm",
        "content_items",
        ["title"],
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )

    op.create_table(
        "content_feature_links",
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.CheckConstraint(
            "role IN ('main', 'stop', 'related', 'nearby', 'recommended')",
            name=op.f("ck_content_feature_links_role"),
        ),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["content_items.id"],
            name="fk_content_feature_links_content_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["feature_id"],
            ["map_features.id"],
            name="fk_content_feature_links_feature_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "content_id",
            "feature_id",
            "role",
            name="pk_content_feature_links",
        ),
    )
    op.create_index(
        "ix_content_feature_links_content",
        "content_feature_links",
        ["content_id", "sort_order"],
    )
    op.create_index(
        "ix_content_feature_links_feature",
        "content_feature_links",
        ["feature_id"],
    )

    op.create_table(
        "content_source_links",
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_method", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("is_primary_source", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 100",
            name=op.f("ck_content_source_links_confidence"),
        ),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["content_items.id"],
            name="fk_content_source_links_content_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["source_records.id"],
            name="fk_content_source_links_source_record_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("content_id", "source_record_id", name="pk_content_source_links"),
    )
    op.create_index("ix_content_source_links_content", "content_source_links", ["content_id"])
    op.create_index(
        "ix_content_source_links_source",
        "content_source_links",
        ["source_record_id"],
    )

    op.create_table(
        "feature_mapping_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_record_id_a", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_record_id_b", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_feature_type", sa.String(length=32), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("name_score", sa.Numeric(5, 2)),
        sa.Column("date_score", sa.Numeric(5, 2)),
        sa.Column("address_score", sa.Numeric(5, 2)),
        sa.Column("distance_score", sa.Numeric(5, 2)),
        sa.Column("org_score", sa.Numeric(5, 2)),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("decision_reason", sa.Text()),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 100",
            name=op.f("ck_feature_mapping_candidates_confidence"),
        ),
        sa.CheckConstraint(
            "source_record_id_a <> source_record_id_b",
            name=op.f("ck_feature_mapping_candidates_different_records"),
        ),
        sa.CheckConstraint(
            "decision IN ('pending', 'auto_approved', 'approved', 'rejected')",
            name=op.f("ck_feature_mapping_candidates_decision"),
        ),
        sa.CheckConstraint(
            "candidate_feature_type IN ('place', 'event', 'route', 'area', 'notice')",
            name=op.f("ck_feature_mapping_candidates_feature_type"),
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id_a"],
            ["source_records.id"],
            name="fk_feature_mapping_candidates_record_a",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id_b"],
            ["source_records.id"],
            name="fk_feature_mapping_candidates_record_b",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_feature_mapping_candidates"),
        sa.UniqueConstraint(
            "source_record_id_a",
            "source_record_id_b",
            name="uq_feature_mapping_candidates_record_pair",
        ),
    )
    op.create_index(
        "ix_feature_mapping_candidates_a",
        "feature_mapping_candidates",
        ["source_record_id_a"],
    )
    op.create_index(
        "ix_feature_mapping_candidates_b",
        "feature_mapping_candidates",
        ["source_record_id_b"],
    )
    op.create_index(
        "ix_feature_mapping_candidates_decision",
        "feature_mapping_candidates",
        ["decision"],
    )
    op.create_index(
        "ix_feature_mapping_candidates_score",
        "feature_mapping_candidates",
        ["confidence_score"],
    )

    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_tags"),
        sa.UniqueConstraint("name", name="uq_tags_name"),
        sa.UniqueConstraint("slug", name="uq_tags_slug"),
    )
    op.create_index("ix_tags_slug", "tags", ["slug"])

    op.create_table(
        "map_feature_tags",
        sa.Column("feature_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["feature_id"],
            ["map_features.id"],
            name="fk_map_feature_tags_feature_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["tags.id"],
            name="fk_map_feature_tags_tag_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("feature_id", "tag_id", name="pk_map_feature_tags"),
    )
    op.create_index("ix_map_feature_tags_tag", "map_feature_tags", ["tag_id"])

    op.create_table(
        "content_tags",
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["content_items.id"],
            name="fk_content_tags_content_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["tags.id"],
            name="fk_content_tags_tag_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("content_id", "tag_id", name="pk_content_tags"),
    )
    op.create_index("ix_content_tags_tag", "content_tags", ["tag_id"])

    op.create_table(
        "media_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("media_type", sa.String(length=32), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("thumbnail_url", sa.Text()),
        sa.Column("storage_key", sa.Text()),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("title", sa.Text()),
        sa.Column("alt_text", sa.Text()),
        sa.Column("source_provider", sa.String(length=40)),
        sa.Column("source_url", sa.Text()),
        sa.Column("license", sa.Text()),
        sa.Column("credit", sa.Text()),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "media_type IN ('image', 'video', 'icon')",
            name=op.f("ck_media_assets_media_type"),
        ),
        sa.CheckConstraint("width IS NULL OR width > 0", name=op.f("ck_media_assets_width")),
        sa.CheckConstraint(
            "height IS NULL OR height > 0",
            name=op.f("ck_media_assets_height"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_media_assets"),
    )
    op.create_index("ix_media_assets_source", "media_assets", ["source_provider"])

    op.create_table(
        "map_feature_media",
        sa.Column("feature_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["feature_id"],
            ["map_features.id"],
            name="fk_map_feature_media_feature_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["media_assets.id"],
            name="fk_map_feature_media_media_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("feature_id", "media_id", "role", name="pk_map_feature_media"),
    )
    op.create_index(
        "ix_map_feature_media_feature",
        "map_feature_media",
        ["feature_id", "sort_order"],
    )
    op.create_index("ix_map_feature_media_media", "map_feature_media", ["media_id"])

    op.create_table(
        "content_media",
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["content_items.id"],
            name="fk_content_media_content_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["media_id"],
            ["media_assets.id"],
            name="fk_content_media_media_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("content_id", "media_id", "role", name="pk_content_media"),
    )
    op.create_index("ix_content_media_content", "content_media", ["content_id", "sort_order"])
    op.create_index("ix_content_media_media", "content_media", ["media_id"])


def _retarget_existing_feature_references() -> None:
    op.drop_constraint("fk_tpi_place_id", "trip_plan_items", type_="foreignkey")
    op.drop_constraint(
        op.f("ck_trip_plan_items_ck_tpi_place_type_match"),
        "trip_plan_items",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_trip_plan_items_ck_tpi_single_fk_resource"),
        "trip_plan_items",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_trip_plan_items_ck_tpi_resource_type"),
        "trip_plan_items",
        type_="check",
    )
    op.drop_index("ix_tpi_place_id", table_name="trip_plan_items")
    op.alter_column(
        "trip_plan_items",
        "place_id",
        new_column_name="map_feature_id",
        existing_type=postgresql.UUID(as_uuid=True),
    )
    op.create_check_constraint(
        op.f("ck_tpi_resource_type"),
        "trip_plan_items",
        "resource_type IN ("
        "'place', 'event', 'route', 'area', 'notice', "
        "'festival', 'trail', 'scenic_road', 'custom'"
        ")",
    )
    op.create_check_constraint(
        op.f("ck_tpi_map_feature_type_match"),
        "trip_plan_items",
        "map_feature_id IS NULL OR resource_type IN ('place', 'event', 'route', 'area', 'notice')",
    )
    op.create_check_constraint(
        op.f("ck_tpi_single_fk_resource"),
        "trip_plan_items",
        "NOT (map_feature_id IS NOT NULL AND festival_id IS NOT NULL)",
    )
    op.create_foreign_key(
        "fk_tpi_map_feature_id",
        "trip_plan_items",
        "map_features",
        ["map_feature_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_tpi_map_feature_id", "trip_plan_items", ["map_feature_id"])

    op.drop_constraint("fk_wbl_place_id", "weather_beach_location", type_="foreignkey")
    op.drop_index("ix_wbl_place_id", table_name="weather_beach_location")
    op.alter_column(
        "weather_beach_location",
        "place_id",
        new_column_name="map_feature_id",
        existing_type=postgresql.UUID(as_uuid=True),
    )
    op.create_foreign_key(
        "fk_wbl_map_feature_id",
        "weather_beach_location",
        "map_features",
        ["map_feature_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_wbl_map_feature_id",
        "weather_beach_location",
        ["map_feature_id"],
    )

    op.drop_constraint("fk_wsb_place_id", "weather_serving_beach", type_="foreignkey")
    op.drop_index("ix_wsb_place_id", table_name="weather_serving_beach")
    op.alter_column(
        "weather_serving_beach",
        "place_id",
        new_column_name="map_feature_id",
        existing_type=postgresql.UUID(as_uuid=True),
    )
    op.create_foreign_key(
        "fk_wsb_map_feature_id",
        "weather_serving_beach",
        "map_features",
        ["map_feature_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_wsb_map_feature_id",
        "weather_serving_beach",
        ["map_feature_id"],
    )

    op.drop_constraint("fk_beach_profiles_place_id", "beach_profiles", type_="foreignkey")
    op.drop_index("ix_beach_profiles_place_id", table_name="beach_profiles")
    op.alter_column(
        "beach_profiles",
        "place_id",
        new_column_name="map_feature_id",
        existing_type=postgresql.UUID(as_uuid=True),
    )
    op.create_foreign_key(
        "fk_beach_profiles_map_feature_id",
        "beach_profiles",
        "map_features",
        ["map_feature_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_beach_profiles_map_feature_id",
        "beach_profiles",
        ["map_feature_id"],
    )
