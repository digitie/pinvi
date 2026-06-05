"""KASI 특일 + POI 출몰시각 테이블

Revision ID: 20260605_0006
Revises: 20260602_0005
Create Date: 2026-06-05 18:00:00

`docs/integrations/kasi.md` / `docs/runbooks/etl.md`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260605_0006"
down_revision: str | None = "20260602_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "kasi_special_days",
        sa.Column(
            "special_day_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("dataset", sa.String(length=40), nullable=False),
        sa.Column("sol_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("sequence", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("is_holiday", sa.Boolean()),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
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
        sa.PrimaryKeyConstraint("special_day_id", name="pk_kasi_special_days"),
        sa.UniqueConstraint(
            "dataset",
            "sol_date",
            "sequence",
            "name",
            name="uq_kasi_special_days_identity",
        ),
        sa.CheckConstraint(
            "dataset IN ("
            "'holidays', 'national_holidays', 'anniversaries', "
            "'solar_terms_24', 'sundry_days'"
            ")",
            name="ck_kasi_special_days_dataset",
        ),
        schema="app",
    )
    op.create_index(
        "ix_kasi_special_days_sol_date",
        "kasi_special_days",
        ["sol_date"],
        schema="app",
    )
    op.create_index(
        "ix_kasi_special_days_dataset_date",
        "kasi_special_days",
        ["dataset", "sol_date"],
        schema="app",
    )
    op.execute(
        "CREATE TRIGGER trg_kasi_special_days_touch_updated_at "
        "BEFORE UPDATE ON app.kasi_special_days "
        "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )

    op.create_table(
        "trip_poi_rise_sets",
        sa.Column("poi_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("locdate", sa.Date()),
        sa.Column("longitude", sa.Float(precision=53)),
        sa.Column("latitude", sa.Float(precision=53)),
        sa.Column("sunrise_at", sa.DateTime(timezone=True)),
        sa.Column("sunset_at", sa.DateTime(timezone=True)),
        sa.Column("moonrise_at", sa.DateTime(timezone=True)),
        sa.Column("moonset_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending_date"),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
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
        sa.PrimaryKeyConstraint("poi_id", name="pk_trip_poi_rise_sets"),
        sa.ForeignKeyConstraint(
            ["poi_id"],
            ["app.trip_day_pois.attachment_id"],
            name="fk_trip_poi_rise_sets_poi_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('pending_date', 'pending_coord', 'pending_fetch', 'success', 'failed')",
            name="ck_trip_poi_rise_sets_status",
        ),
        schema="app",
    )
    op.create_index(
        "ix_trip_poi_rise_sets_locdate",
        "trip_poi_rise_sets",
        ["locdate"],
        schema="app",
    )
    op.create_index(
        "ix_trip_poi_rise_sets_pending_fetch",
        "trip_poi_rise_sets",
        ["locdate"],
        schema="app",
        postgresql_where=sa.text("status = 'pending_fetch'"),
    )
    op.execute(
        "CREATE TRIGGER trg_trip_poi_rise_sets_touch_updated_at "
        "BEFORE UPDATE ON app.trip_poi_rise_sets "
        "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_trip_poi_rise_sets_touch_updated_at ON app.trip_poi_rise_sets"
    )
    op.drop_index(
        "ix_trip_poi_rise_sets_pending_fetch",
        table_name="trip_poi_rise_sets",
        schema="app",
    )
    op.drop_index("ix_trip_poi_rise_sets_locdate", table_name="trip_poi_rise_sets", schema="app")
    op.drop_table("trip_poi_rise_sets", schema="app")

    op.execute(
        "DROP TRIGGER IF EXISTS trg_kasi_special_days_touch_updated_at ON app.kasi_special_days"
    )
    op.drop_index("ix_kasi_special_days_dataset_date", table_name="kasi_special_days", schema="app")
    op.drop_index("ix_kasi_special_days_sol_date", table_name="kasi_special_days", schema="app")
    op.drop_table("kasi_special_days", schema="app")
