"""curated trip plan schema names

Revision ID: 20260607_0011
Revises: 20260606_0010
Create Date: 2026-06-07 12:00:00

T-137 / ADR-029: 사용자 대면 추천 여행은 system notice와 분리된
`curated_trip_plans` 계열 테이블명을 쓴다.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260607_0011"
down_revision: str | None = "20260606_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE app.notice_plans RENAME TO curated_trip_plans")
    op.execute("ALTER TABLE app.notice_pois RENAME TO curated_plan_pois")
    op.execute("ALTER TABLE app.plan_poi_attachments RENAME TO curated_plan_attachments")

    op.execute("ALTER TABLE app.curated_trip_plans RENAME COLUMN notice_plan_id TO curated_plan_id")
    op.execute("ALTER TABLE app.curated_plan_pois RENAME COLUMN notice_poi_id TO curated_poi_id")
    op.execute("ALTER TABLE app.curated_plan_pois RENAME COLUMN notice_plan_id TO curated_plan_id")
    op.execute(
        "ALTER TABLE app.curated_plan_attachments RENAME COLUMN notice_plan_id TO curated_plan_id"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments RENAME COLUMN notice_poi_id TO curated_poi_id"
    )

    op.execute(
        "ALTER TABLE app.curated_trip_plans "
        "RENAME CONSTRAINT pk_notice_plans TO pk_curated_trip_plans"
    )
    op.execute(
        "ALTER TABLE app.curated_trip_plans "
        "RENAME CONSTRAINT fk_notice_plans_created_by_admin_id "
        "TO fk_curated_trip_plans_created_by_admin_id"
    )
    op.execute(
        "ALTER TABLE app.curated_trip_plans "
        "RENAME CONSTRAINT fk_notice_plans_updated_by_admin_id "
        "TO fk_curated_trip_plans_updated_by_admin_id"
    )
    op.execute(
        "ALTER TABLE app.curated_trip_plans "
        "RENAME CONSTRAINT ck_notice_plans_ck_notice_plans_date_range "
        "TO ck_curated_trip_plans_date_range"
    )

    op.execute(
        "ALTER TABLE app.curated_plan_pois RENAME CONSTRAINT pk_notice_pois TO pk_curated_plan_pois"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_pois "
        "RENAME CONSTRAINT fk_notice_pois_notice_plan_id "
        "TO fk_curated_plan_pois_curated_plan_id"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_pois "
        "RENAME CONSTRAINT ck_notice_pois_ck_notice_pois_day_index "
        "TO ck_curated_plan_pois_day_index"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_pois "
        "RENAME CONSTRAINT ck_notice_pois_ck_notice_pois_custom_marker_color "
        "TO ck_curated_plan_pois_custom_marker_color"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_pois "
        "RENAME CONSTRAINT ck_notice_pois_ck_notice_pois_budget_nonnegative "
        "TO ck_curated_plan_pois_budget_nonnegative"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_pois "
        "RENAME CONSTRAINT ck_notice_pois_ck_notice_pois_currency "
        "TO ck_curated_plan_pois_currency"
    )

    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT pk_plan_poi_attachments TO pk_curated_plan_attachments"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT ck_plan_poi_attachments_ck_plan_poi_attachments_single_target "
        "TO ck_curated_plan_attachments_single_target"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT ck_plan_poi_attachments_ck_plan_poi_attachments_role "
        "TO ck_curated_plan_attachments_role"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT ck_plan_poi_attachments_ck_plan_poi_attachments_byte_size "
        "TO ck_curated_plan_attachments_byte_size"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT ck_plan_poi_attachments_ck_plan_poi_attachments_sort_order "
        "TO ck_curated_plan_attachments_sort_order"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT fk_plan_poi_attachments_trip_id "
        "TO fk_curated_plan_attachments_trip_id"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT fk_plan_poi_attachments_trip_poi_id "
        "TO fk_curated_plan_attachments_trip_poi_id"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT fk_plan_poi_attachments_notice_plan_id "
        "TO fk_curated_plan_attachments_curated_plan_id"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT fk_plan_poi_attachments_notice_poi_id "
        "TO fk_curated_plan_attachments_curated_poi_id"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT fk_plan_poi_attachments_source_attachment_id "
        "TO fk_curated_plan_attachments_source_attachment_id"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT fk_plan_poi_attachments_uploaded_by_user_id "
        "TO fk_curated_plan_attachments_uploaded_by_user_id"
    )

    op.execute(
        "ALTER INDEX app.uq_notice_plans_slug_active RENAME TO uq_curated_trip_plans_slug_active"
    )
    op.execute(
        "ALTER INDEX app.ix_notice_plans_published RENAME TO ix_curated_trip_plans_published"
    )
    op.execute("ALTER INDEX app.ix_notice_plans_category RENAME TO ix_curated_trip_plans_category")
    op.execute("ALTER INDEX app.ix_notice_pois_plan_day RENAME TO ix_curated_plan_pois_plan_day")
    op.execute(
        "ALTER INDEX app.uq_notice_pois_plan_day_sort RENAME TO uq_curated_plan_pois_plan_day_sort"
    )
    op.execute(
        "ALTER INDEX app.ix_plan_poi_attachments_trip RENAME TO ix_curated_plan_attachments_trip"
    )
    op.execute(
        "ALTER INDEX app.ix_plan_poi_attachments_trip_poi "
        "RENAME TO ix_curated_plan_attachments_trip_poi"
    )
    op.execute(
        "ALTER INDEX app.ix_plan_poi_attachments_notice_plan "
        "RENAME TO ix_curated_plan_attachments_curated_plan"
    )
    op.execute(
        "ALTER INDEX app.ix_plan_poi_attachments_notice_poi "
        "RENAME TO ix_curated_plan_attachments_curated_poi"
    )
    op.execute(
        "ALTER INDEX app.ix_plan_poi_attachments_storage_key "
        "RENAME TO ix_curated_plan_attachments_storage_key"
    )

    op.execute(
        "ALTER TRIGGER trg_notice_plans_touch_updated_at "
        "ON app.curated_trip_plans RENAME TO trg_curated_trip_plans_touch_updated_at"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TRIGGER trg_curated_trip_plans_touch_updated_at "
        "ON app.curated_trip_plans RENAME TO trg_notice_plans_touch_updated_at"
    )

    op.execute(
        "ALTER INDEX app.ix_curated_plan_attachments_storage_key "
        "RENAME TO ix_plan_poi_attachments_storage_key"
    )
    op.execute(
        "ALTER INDEX app.ix_curated_plan_attachments_curated_poi "
        "RENAME TO ix_plan_poi_attachments_notice_poi"
    )
    op.execute(
        "ALTER INDEX app.ix_curated_plan_attachments_curated_plan "
        "RENAME TO ix_plan_poi_attachments_notice_plan"
    )
    op.execute(
        "ALTER INDEX app.ix_curated_plan_attachments_trip_poi "
        "RENAME TO ix_plan_poi_attachments_trip_poi"
    )
    op.execute(
        "ALTER INDEX app.ix_curated_plan_attachments_trip RENAME TO ix_plan_poi_attachments_trip"
    )
    op.execute(
        "ALTER INDEX app.uq_curated_plan_pois_plan_day_sort RENAME TO uq_notice_pois_plan_day_sort"
    )
    op.execute("ALTER INDEX app.ix_curated_plan_pois_plan_day RENAME TO ix_notice_pois_plan_day")
    op.execute("ALTER INDEX app.ix_curated_trip_plans_category RENAME TO ix_notice_plans_category")
    op.execute(
        "ALTER INDEX app.ix_curated_trip_plans_published RENAME TO ix_notice_plans_published"
    )
    op.execute(
        "ALTER INDEX app.uq_curated_trip_plans_slug_active RENAME TO uq_notice_plans_slug_active"
    )

    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT fk_curated_plan_attachments_uploaded_by_user_id "
        "TO fk_plan_poi_attachments_uploaded_by_user_id"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT fk_curated_plan_attachments_source_attachment_id "
        "TO fk_plan_poi_attachments_source_attachment_id"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT fk_curated_plan_attachments_curated_poi_id "
        "TO fk_plan_poi_attachments_notice_poi_id"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT fk_curated_plan_attachments_curated_plan_id "
        "TO fk_plan_poi_attachments_notice_plan_id"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT fk_curated_plan_attachments_trip_poi_id "
        "TO fk_plan_poi_attachments_trip_poi_id"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT fk_curated_plan_attachments_trip_id "
        "TO fk_plan_poi_attachments_trip_id"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT ck_curated_plan_attachments_sort_order "
        "TO ck_plan_poi_attachments_ck_plan_poi_attachments_sort_order"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT ck_curated_plan_attachments_byte_size "
        "TO ck_plan_poi_attachments_ck_plan_poi_attachments_byte_size"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT ck_curated_plan_attachments_role "
        "TO ck_plan_poi_attachments_ck_plan_poi_attachments_role"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT ck_curated_plan_attachments_single_target "
        "TO ck_plan_poi_attachments_ck_plan_poi_attachments_single_target"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments "
        "RENAME CONSTRAINT pk_curated_plan_attachments TO pk_plan_poi_attachments"
    )

    op.execute(
        "ALTER TABLE app.curated_plan_pois "
        "RENAME CONSTRAINT ck_curated_plan_pois_currency "
        "TO ck_notice_pois_ck_notice_pois_currency"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_pois "
        "RENAME CONSTRAINT ck_curated_plan_pois_budget_nonnegative "
        "TO ck_notice_pois_ck_notice_pois_budget_nonnegative"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_pois "
        "RENAME CONSTRAINT ck_curated_plan_pois_custom_marker_color "
        "TO ck_notice_pois_ck_notice_pois_custom_marker_color"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_pois "
        "RENAME CONSTRAINT ck_curated_plan_pois_day_index "
        "TO ck_notice_pois_ck_notice_pois_day_index"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_pois "
        "RENAME CONSTRAINT fk_curated_plan_pois_curated_plan_id "
        "TO fk_notice_pois_notice_plan_id"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_pois RENAME CONSTRAINT pk_curated_plan_pois TO pk_notice_pois"
    )

    op.execute(
        "ALTER TABLE app.curated_trip_plans "
        "RENAME CONSTRAINT ck_curated_trip_plans_date_range "
        "TO ck_notice_plans_ck_notice_plans_date_range"
    )
    op.execute(
        "ALTER TABLE app.curated_trip_plans "
        "RENAME CONSTRAINT fk_curated_trip_plans_updated_by_admin_id "
        "TO fk_notice_plans_updated_by_admin_id"
    )
    op.execute(
        "ALTER TABLE app.curated_trip_plans "
        "RENAME CONSTRAINT fk_curated_trip_plans_created_by_admin_id "
        "TO fk_notice_plans_created_by_admin_id"
    )
    op.execute(
        "ALTER TABLE app.curated_trip_plans "
        "RENAME CONSTRAINT pk_curated_trip_plans TO pk_notice_plans"
    )

    op.execute(
        "ALTER TABLE app.curated_plan_attachments RENAME COLUMN curated_poi_id TO notice_poi_id"
    )
    op.execute(
        "ALTER TABLE app.curated_plan_attachments RENAME COLUMN curated_plan_id TO notice_plan_id"
    )
    op.execute("ALTER TABLE app.curated_plan_pois RENAME COLUMN curated_plan_id TO notice_plan_id")
    op.execute("ALTER TABLE app.curated_plan_pois RENAME COLUMN curated_poi_id TO notice_poi_id")
    op.execute("ALTER TABLE app.curated_trip_plans RENAME COLUMN curated_plan_id TO notice_plan_id")

    op.execute("ALTER TABLE app.curated_plan_attachments RENAME TO plan_poi_attachments")
    op.execute("ALTER TABLE app.curated_plan_pois RENAME TO notice_pois")
    op.execute("ALTER TABLE app.curated_trip_plans RENAME TO notice_plans")
