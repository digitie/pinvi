"""#637: 특보 동의 시점과 취소/충돌 관측의 영속 fence."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "20261105_0105"
down_revision: str | None = "20261105_0104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRIOR = "contract_version = 'pinvi-cache-target-final-boundary/v1' AND status = 'succeeded' AND (schema_revision = '20260824_0101' OR schema_revision = '20260917_0102' OR schema_revision = '20261105_0103' OR schema_revision = '20261105_0104')"


def boundary(check: str) -> None:
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
    op.add_column(
        "telegram_notification_preferences",
        sa.Column("weather_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        schema="app",
    )
    op.add_column(
        "telegram_notification_preferences",
        sa.Column("weather_enabled_at", sa.DateTime(timezone=True)),
        schema="app",
    )
    op.create_table(
        "telegram_weather_observations",
        sa.Column(
            "trip_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("app.trips.trip_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("announcement_id", sa.String(128), primary_key=True),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("cancelled", sa.Boolean(), nullable=False),
        sa.Column("ambiguous", sa.Boolean(), nullable=False),
        sa.Column(
            "generation",
            pg.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        schema="app",
    )
    boundary(_PRIOR[:-1] + " OR schema_revision = '20261105_0105')")


def downgrade() -> None:
    op.execute(
        "DELETE FROM app.ktm_cache_target_boundary_audits WHERE schema_revision = '20261105_0105'"
    )
    boundary(_PRIOR)
    op.drop_table("telegram_weather_observations", schema="app")
    op.drop_column("telegram_notification_preferences", "weather_enabled_at", schema="app")
    op.drop_column("telegram_notification_preferences", "weather_enabled", schema="app")
