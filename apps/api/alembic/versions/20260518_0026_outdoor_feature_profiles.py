"""add outdoor feature profile schema

Revision ID: 20260518_0026
Revises: 20260516_0025
Create Date: 2026-05-18 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260518_0026"
down_revision: str | None = "20260516_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _seed_outdoor_place_categories()
    op.execute(
        """
        ALTER TABLE map_features
        ALTER COLUMN geom TYPE geometry(Geometry, 4326)
        USING geom::geometry(Geometry, 4326)
        """
    )
    op.alter_column(
        "map_features",
        "address",
        existing_type=sa.String(length=700),
        nullable=True,
    )
    op.drop_constraint(op.f("ck_area_details_area_kind"), "area_details", type_="check")
    op.create_check_constraint(
        op.f("ck_area_details_area_kind"),
        "area_details",
        "area_kind IN ("
        "'national_park', 'beach', 'tourism_zone', 'market_area', 'restricted_area', "
        "'mountain', 'recreation_forest', 'arboretum', 'forest_area', 'trail_area'"
        ")",
    )

    op.create_table(
        "outdoor_feature_profiles",
        sa.Column("feature_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outdoor_kind", sa.String(length=40), nullable=False),
        sa.Column("feature_role", sa.String(length=32), nullable=False, server_default="primary"),
        sa.Column("source_provider", sa.String(length=40), nullable=False),
        sa.Column("source_dataset_key", sa.String(length=120), nullable=False),
        sa.Column("source_dataset_name", sa.String(length=255)),
        sa.Column("confidence", sa.SmallInteger()),
        sa.Column("difficulty", sa.String(length=32)),
        sa.Column("distance_m", sa.Integer()),
        sa.Column("duration_min", sa.Integer()),
        sa.Column("elevation_gain_m", sa.Integer()),
        sa.Column("recommended_season", sa.Text()),
        sa.Column("reservation_url", sa.Text()),
        sa.Column("safety_note", sa.Text()),
        sa.Column("data_quality_note", sa.Text()),
        sa.Column(
            "extra",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "outdoor_kind IN ("
            "'national_park', 'mountain', 'recreation_forest', 'arboretum', "
            "'forest_trail', 'hiking_trail', 'trekking_course', 'forest_education', "
            "'kid_forest', 'village_forest', 'campground', 'outdoor_support', 'unknown'"
            ")",
            name="ck_outdoor_feature_profiles_kind",
        ),
        sa.CheckConstraint(
            "feature_role IN ('primary', 'support', 'safety', 'enrichment')",
            name="ck_outdoor_feature_profiles_role",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 100",
            name="ck_outdoor_feature_profiles_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["feature_id"],
            ["map_features.id"],
            name="fk_outdoor_feature_profiles_feature_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("feature_id", name="pk_outdoor_feature_profiles"),
    )
    op.create_index(
        "ix_outdoor_feature_profiles_kind_role",
        "outdoor_feature_profiles",
        ["outdoor_kind", "feature_role"],
    )
    op.create_index(
        "ix_outdoor_feature_profiles_source",
        "outdoor_feature_profiles",
        ["source_provider", "source_dataset_key"],
    )
    op.create_index(
        "ix_outdoor_feature_profiles_updated_at",
        "outdoor_feature_profiles",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outdoor_feature_profiles_updated_at",
        table_name="outdoor_feature_profiles",
    )
    op.drop_index(
        "ix_outdoor_feature_profiles_source",
        table_name="outdoor_feature_profiles",
    )
    op.drop_index(
        "ix_outdoor_feature_profiles_kind_role",
        table_name="outdoor_feature_profiles",
    )
    op.drop_table("outdoor_feature_profiles")
    op.drop_constraint(op.f("ck_area_details_area_kind"), "area_details", type_="check")
    op.create_check_constraint(
        op.f("ck_area_details_area_kind"),
        "area_details",
        "area_kind IN ("
        "'national_park', 'beach', 'tourism_zone', 'market_area', 'restricted_area'"
        ")",
    )
    op.execute(
        """
        ALTER TABLE map_features
        ALTER COLUMN geom TYPE geometry(Point, 4326)
        USING ST_PointOnSurface(geom)::geometry(Point, 4326)
        """
    )
    op.alter_column(
        "map_features",
        "address",
        existing_type=sa.String(length=700),
        nullable=False,
    )


def _seed_outdoor_place_categories() -> None:
    rows = [
        ("01020000", "관광", "자연관광", None, None, 2, "01000000", 20),
        ("01020100", "관광", "자연관광", "국립공원", None, 3, "01020000", 201),
        ("01020101", "관광", "자연관광", "국립공원", "국립공원", 4, "01020100", 2011),
        ("01020200", "관광", "자연관광", "산·명산", None, 3, "01020000", 202),
        ("01020201", "관광", "자연관광", "산·명산", "100대명산", 4, "01020200", 2021),
        ("01020300", "관광", "자연관광", "산림휴양", None, 3, "01020000", 203),
        ("01020301", "관광", "자연관광", "산림휴양", "휴양림", 4, "01020300", 2031),
        ("01020302", "관광", "자연관광", "산림휴양", "수목원", 4, "01020300", 2032),
        ("01020303", "관광", "자연관광", "산림휴양", "산림교육·체험", 4, "01020300", 2033),
        ("02000000", "액티비티", None, None, None, 1, None, 200),
        ("02010000", "액티비티", "걷기·등산", None, None, 2, "02000000", 210),
        ("02010100", "액티비티", "걷기·등산", "등산로", None, 3, "02010000", 211),
        ("02010101", "액티비티", "걷기·등산", "등산로", "산림청 등산로", 4, "02010100", 2111),
        ("02010200", "액티비티", "걷기·등산", "트레킹·숲길", None, 3, "02010000", 212),
        ("02010201", "액티비티", "걷기·등산", "트레킹·숲길", "둘레길·숲길", 4, "02010200", 2121),
    ]
    for row in rows:
        op.execute(
            sa.text(
                """
                INSERT INTO place_categories (
                    category_code,
                    tier1_code,
                    tier2_code,
                    tier3_code,
                    tier4_code,
                    tier1_name,
                    tier2_name,
                    tier3_name,
                    tier4_name,
                    depth,
                    parent_category_code,
                    sort_order,
                    is_active,
                    created_at,
                    updated_at
                )
                VALUES (
                    :category_code,
                    substring(:category_code from 1 for 2),
                    substring(:category_code from 3 for 2),
                    substring(:category_code from 5 for 2),
                    substring(:category_code from 7 for 2),
                    :tier1_name,
                    :tier2_name,
                    :tier3_name,
                    :tier4_name,
                    :depth,
                    :parent_category_code,
                    :sort_order,
                    true,
                    now(),
                    now()
                )
                ON CONFLICT (category_code) DO NOTHING
                """
            ).bindparams(
                category_code=row[0],
                tier1_name=row[1],
                tier2_name=row[2],
                tier3_name=row[3],
                tier4_name=row[4],
                depth=row[5],
                parent_category_code=row[6],
                sort_order=row[7],
            )
        )
