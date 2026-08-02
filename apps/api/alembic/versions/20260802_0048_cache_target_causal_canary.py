"""cache target production causal canary의 durable 실행 정본을 추가한다.

Revision ID: 20260802_0048
Revises: 20260801_0047
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260802_0048"
down_revision: str | None = "20260801_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ktm_cache_target_canary_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_poi_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("phase", sa.Text(), nullable=False, server_default="put_enqueued"),
        sa.Column("put_command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delete_command_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("put_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("delete_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("put_generation", sa.BigInteger(), nullable=False),
        sa.Column("delete_generation", sa.BigInteger(), nullable=False),
        sa.Column("put_relay_order", sa.BigInteger(), nullable=True),
        sa.Column("delete_relay_order", sa.BigInteger(), nullable=True),
        sa.Column("baseline_cache_generation", sa.BigInteger(), nullable=False),
        sa.Column("put_cache_generation", sa.BigInteger(), nullable=True),
        sa.Column("final_cache_generation", sa.BigInteger(), nullable=True),
        sa.Column("baseline_cursor", sa.Text(), nullable=False),
        sa.Column("put_cursor", sa.Text(), nullable=True),
        sa.Column("final_cursor", sa.Text(), nullable=True),
        sa.Column("baseline_count", sa.BigInteger(), nullable=False),
        sa.Column("baseline_merkle_root", sa.LargeBinary(), nullable=False),
        sa.Column("final_count", sa.BigInteger(), nullable=True),
        sa.Column("final_merkle_root", sa.LargeBinary(), nullable=True),
        sa.Column("terminal_error_code", sa.Text(), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("run_id", name="pk_ktm_cache_target_canary_runs"),
        sa.UniqueConstraint("put_command_id", name="uq_ktm_ct_canary_put_command"),
        sa.UniqueConstraint("delete_command_id", name="uq_ktm_ct_canary_delete_command"),
        sa.UniqueConstraint("put_event_id", name="uq_ktm_ct_canary_put_event"),
        sa.UniqueConstraint("delete_event_id", name="uq_ktm_ct_canary_delete_event"),
        sa.ForeignKeyConstraint(
            ["target_poi_id"],
            ["app.ktm_cache_target_heads.poi_id"],
            name="fk_ktm_ct_canary_target",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["put_command_id"],
            ["app.ktm_cache_target_commands.command_id"],
            name="fk_ktm_ct_canary_put_command",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["delete_command_id"],
            ["app.ktm_cache_target_commands.command_id"],
            name="fk_ktm_ct_canary_delete_command",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["put_event_id"],
            ["app.ktm_cache_target_events.event_id"],
            name="fk_ktm_ct_canary_put_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["delete_event_id"],
            ["app.ktm_cache_target_events.event_id"],
            name="fk_ktm_ct_canary_delete_event",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "target_poi_id = '15f98050-27d7-5f85-be21-dc53eded5d7d'::uuid",
            name="ck_ktm_ct_canary_stable_target",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_ktm_ct_canary_status",
        ),
        sa.CheckConstraint(
            "phase IN ('put_enqueued', 'put_applied', 'delete_enqueued', "
            "'delete_applied', 'completed')",
            name="ck_ktm_ct_canary_phase",
        ),
        sa.CheckConstraint(
            "put_generation > 0 AND delete_generation = put_generation + 1",
            name="ck_ktm_ct_canary_generations",
        ),
        sa.CheckConstraint(
            "baseline_cache_generation >= 0 AND baseline_count >= 0 "
            "AND octet_length(baseline_merkle_root) = 32 AND length(baseline_cursor) > 0",
            name="ck_ktm_ct_canary_baseline",
        ),
        sa.CheckConstraint(
            "(put_event_id IS NULL AND put_relay_order IS NULL "
            "AND put_cache_generation IS NULL AND put_cursor IS NULL) OR "
            "(put_event_id IS NOT NULL AND put_relay_order > 0 "
            "AND put_cache_generation > baseline_cache_generation AND length(put_cursor) > 0)",
            name="ck_ktm_ct_canary_put_material",
        ),
        sa.CheckConstraint(
            "(delete_event_id IS NULL AND delete_relay_order IS NULL) OR "
            "(delete_event_id IS NOT NULL AND delete_relay_order > put_relay_order)",
            name="ck_ktm_ct_canary_delete_material",
        ),
        sa.CheckConstraint(
            "(final_cache_generation IS NULL AND final_cursor IS NULL "
            "AND final_count IS NULL AND final_merkle_root IS NULL) OR "
            "(final_cache_generation > put_cache_generation AND length(final_cursor) > 0 "
            "AND final_count >= 0 AND octet_length(final_merkle_root) = 32)",
            name="ck_ktm_ct_canary_final_material",
        ),
        sa.CheckConstraint(
            "(phase = 'put_enqueued' AND put_event_id IS NULL AND delete_command_id IS NULL "
            "AND delete_event_id IS NULL AND final_cache_generation IS NULL) OR "
            "(phase = 'put_applied' AND put_event_id IS NOT NULL AND delete_command_id IS NULL "
            "AND delete_event_id IS NULL AND final_cache_generation IS NULL) OR "
            "(phase = 'delete_enqueued' AND put_event_id IS NOT NULL "
            "AND delete_command_id IS NOT NULL AND delete_event_id IS NULL "
            "AND final_cache_generation IS NULL) OR "
            "(phase = 'delete_applied' AND put_event_id IS NOT NULL "
            "AND delete_command_id IS NOT NULL AND delete_event_id IS NOT NULL "
            "AND final_cache_generation IS NULL) OR "
            "(phase = 'completed' AND put_event_id IS NOT NULL "
            "AND delete_command_id IS NOT NULL AND delete_event_id IS NOT NULL "
            "AND final_cache_generation IS NOT NULL)",
            name="ck_ktm_ct_canary_phase_material",
        ),
        sa.CheckConstraint(
            "(status = 'running' AND terminal_error_code IS NULL AND failed_at IS NULL "
            "AND completed_at IS NULL AND phase <> 'completed') OR "
            "(status = 'succeeded' AND terminal_error_code IS NULL AND failed_at IS NULL "
            "AND completed_at IS NOT NULL AND phase = 'completed') OR "
            "(status = 'failed' AND length(terminal_error_code) > 0 "
            "AND failed_at IS NOT NULL AND completed_at IS NULL AND phase <> 'completed')",
            name="ck_ktm_ct_canary_terminal",
        ),
        schema="app",
    )
    op.create_index(
        "uq_ktm_ct_canary_running_target",
        "ktm_cache_target_canary_runs",
        ["target_poi_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_ktm_ct_canary_running_target",
        table_name="ktm_cache_target_canary_runs",
        schema="app",
    )
    op.drop_table("ktm_cache_target_canary_runs", schema="app")
