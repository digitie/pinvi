"""cache target initial cutover 동안 POI source write를 DB에서 fence한다.

Revision ID: 20260731_0045
Revises: 20260731_0044
Create Date: 2026-07-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260731_0045"
down_revision: str | None = "20260731_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FENCE_FUNCTION = """
CREATE FUNCTION app.lock_ktm_cache_target_source_cutover()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
    PERFORM pg_advisory_xact_lock_shared(1263816009, 41);
    RETURN NULL;
END;
$$
"""


def upgrade() -> None:
    op.add_column(
        "ktm_cache_target_consumers",
        sa.Column("initial_cutover_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="app",
    )
    op.add_column(
        "ktm_cache_target_consumers",
        sa.Column(
            "initial_reconciliation_request_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        schema="app",
    )
    op.add_column(
        "ktm_cache_target_consumers",
        sa.Column("initial_begin_stream_etag", sa.Text(), nullable=True),
        schema="app",
    )
    op.add_column(
        "ktm_cache_target_consumers",
        sa.Column("initial_reconciliation_etag", sa.Text(), nullable=True),
        schema="app",
    )
    op.add_column(
        "ktm_cache_target_consumers",
        sa.Column("initial_source_count", sa.BigInteger(), nullable=True),
        schema="app",
    )
    op.add_column(
        "ktm_cache_target_consumers",
        sa.Column("initial_source_merkle_root", sa.LargeBinary(), nullable=True),
        schema="app",
    )
    op.add_column(
        "ktm_cache_target_consumers",
        sa.Column("initial_cutover_completed_at", sa.DateTime(timezone=True), nullable=True),
        schema="app",
    )
    op.create_check_constraint(
        "ck_ktm_ct_consumers_initial_cutover",
        "ktm_cache_target_consumers",
        "(initial_cutover_id IS NULL AND initial_reconciliation_request_id IS NULL "
        "AND initial_begin_stream_etag IS NULL AND initial_reconciliation_etag IS NULL "
        "AND initial_source_count IS NULL AND initial_source_merkle_root IS NULL "
        "AND initial_cutover_completed_at IS NULL) OR "
        "(initial_cutover_id IS NOT NULL AND initial_source_count >= 0 "
        "AND octet_length(initial_source_merkle_root) = 32)",
        schema="app",
    )
    op.execute(sa.text(_FENCE_FUNCTION))
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_trip_day_pois_cache_target_cutover_fence "
            "BEFORE INSERT OR UPDATE OR DELETE ON app.trip_day_pois "
            "FOR EACH STATEMENT EXECUTE FUNCTION app.lock_ktm_cache_target_source_cutover()"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_trip_day_pois_cache_target_cutover_fence "
            "ON app.trip_day_pois"
        )
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS app.lock_ktm_cache_target_source_cutover()"))
    op.drop_constraint(
        "ck_ktm_ct_consumers_initial_cutover",
        "ktm_cache_target_consumers",
        schema="app",
        type_="check",
    )
    for column in (
        "initial_cutover_completed_at",
        "initial_source_merkle_root",
        "initial_source_count",
        "initial_reconciliation_etag",
        "initial_begin_stream_etag",
        "initial_reconciliation_request_id",
        "initial_cutover_id",
    ):
        op.drop_column("ktm_cache_target_consumers", column, schema="app")
