"""여행 장소(POI)별 영업 정보(영업시간·휴무일·전화·웹사이트) 사본.

새 테이블 하나라 forward-safe다. 이전 코드는 이 테이블을 읽지 않는다. POI가 영구 삭제되면 FK CASCADE로
함께 지워지고, soft delete는 서비스가 지운다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "20261116_0108"
down_revision: str | None = "20261107_0107"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRIOR = "contract_version = 'pinvi-cache-target-final-boundary/v1' AND status = 'succeeded' AND (schema_revision = '20260824_0101' OR schema_revision = '20260917_0102' OR schema_revision = '20261105_0103' OR schema_revision = '20261105_0104' OR schema_revision = '20261105_0105' OR schema_revision = '20261106_0106' OR schema_revision = '20261107_0107')"
_CHECK = _PRIOR[:-1] + " OR schema_revision = '20261116_0108')"


def _boundary(check: str) -> None:
    op.drop_constraint(
        op.f("ck_ktm_ct_boundary_contract"),
        "ktm_cache_target_boundary_audits",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_ktm_ct_boundary_contract"), "ktm_cache_target_boundary_audits", check, schema="app"
    )


def upgrade() -> None:
    op.create_table(
        "trip_poi_place_details",
        sa.Column(
            "poi_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey(
                "app.trip_day_pois.attachment_id",
                ondelete="CASCADE",
                name=op.f("fk_trip_poi_place_details_poi_id"),
            ),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "opening_hours", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("closed_days", sa.Text()),
        sa.Column("phone", sa.Text()),
        sa.Column("website", sa.Text()),
        sa.Column("sources", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("poi_id", name=op.f("pk_trip_poi_place_details")),
        sa.CheckConstraint(
            "status IN ('ready', 'empty')", name=op.f("ck_trip_poi_place_details_status")
        ),
        schema="app",
    )
    _boundary(_CHECK)


def downgrade() -> None:
    op.execute(
        "DELETE FROM app.ktm_cache_target_boundary_audits WHERE schema_revision = '20261116_0108'"
    )
    _boundary(_PRIOR)
    op.drop_table("trip_poi_place_details", schema="app")
