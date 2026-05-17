"""add provider source roles, overrides, weather merge values, sync state

Revision ID: 20260516_0025
Revises: 20260513_0024
Create Date: 2026-05-16 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260516_0025"
down_revision: str | None = "20260513_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "map_feature_source_links",
        sa.Column(
            "source_role",
            sa.String(length=40),
            nullable=False,
            server_default="enrichment",
        ),
    )
    op.create_check_constraint(
        "ck_map_feature_source_links_role",
        "map_feature_source_links",
        "source_role IN ('base_address', 'base_coordinate', 'primary', 'enrichment', "
        "'correction', 'duplicate_candidate', 'media', 'weather_context')",
    )
    op.create_index(
        "ix_map_feature_source_links_role",
        "map_feature_source_links",
        ["source_role"],
    )

    op.create_table(
        "map_feature_overrides",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("feature_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_dataset_key", sa.String(length=120)),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True)),
        sa.Column("field_path", sa.Text(), nullable=False),
        sa.Column("source_value", postgresql.JSONB()),
        sa.Column("override_value", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
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
            "status IN ('pending_review', 'active', 'rejected', 'superseded')",
            name="ck_map_feature_overrides_status",
        ),
        sa.CheckConstraint("field_path <> ''", name="ck_map_feature_overrides_field_path"),
        sa.ForeignKeyConstraint(
            ["feature_id"],
            ["map_features.id"],
            name="fk_map_feature_overrides_feature_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_record_id"],
            ["source_records.id"],
            name="fk_map_feature_overrides_source_record_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            name="fk_map_feature_overrides_reviewed_by",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_map_feature_overrides"),
    )
    op.create_index("ix_map_feature_overrides_feature", "map_feature_overrides", ["feature_id"])
    op.create_index("ix_map_feature_overrides_provider", "map_feature_overrides", ["provider"])
    op.create_index(
        "ix_map_feature_overrides_source",
        "map_feature_overrides",
        ["source_record_id"],
    )
    op.create_index("ix_map_feature_overrides_status", "map_feature_overrides", ["status"])
    op.create_index(
        "ix_map_feature_overrides_reviewer",
        "map_feature_overrides",
        ["reviewed_by_user_id"],
    )

    op.create_table(
        "provider_sync_state",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("dataset_key", sa.String(length=120), nullable=False),
        sa.Column("sync_scope", sa.String(length=160), nullable=False, server_default="global"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("cursor", postgresql.JSONB()),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("next_run_after", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("last_error_at", sa.DateTime(timezone=True)),
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
            "status IN ('active', 'paused', 'failed')",
            name="ck_provider_sync_state_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_provider_sync_state"),
        sa.UniqueConstraint(
            "provider",
            "dataset_key",
            "sync_scope",
            name="uq_provider_sync_state_provider_dataset_scope",
        ),
    )
    op.create_index(
        "ix_provider_sync_state_provider_dataset",
        "provider_sync_state",
        ["provider", "dataset_key"],
    )
    op.create_index(
        "ix_provider_sync_state_status_next",
        "provider_sync_state",
        ["status", "next_run_after"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_sync_state_status_next", table_name="provider_sync_state")
    op.drop_index("ix_provider_sync_state_provider_dataset", table_name="provider_sync_state")
    op.drop_table("provider_sync_state")

    op.drop_index("ix_map_feature_overrides_reviewer", table_name="map_feature_overrides")
    op.drop_index("ix_map_feature_overrides_status", table_name="map_feature_overrides")
    op.drop_index("ix_map_feature_overrides_source", table_name="map_feature_overrides")
    op.drop_index("ix_map_feature_overrides_provider", table_name="map_feature_overrides")
    op.drop_index("ix_map_feature_overrides_feature", table_name="map_feature_overrides")
    op.drop_table("map_feature_overrides")

    op.drop_index("ix_map_feature_source_links_role", table_name="map_feature_source_links")
    op.drop_constraint(
        "ck_map_feature_source_links_role",
        "map_feature_source_links",
        type_="check",
    )
    op.drop_column("map_feature_source_links", "source_role")
