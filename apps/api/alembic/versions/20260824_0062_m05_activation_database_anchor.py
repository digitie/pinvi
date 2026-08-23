"""M05 activation generation을 app schema 복원과 분리된 DB append-only anchor에 봉인한다."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0062"
down_revision: str | None = "20260821_0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ops")
    op.create_table(
        "m05_activation_database_anchor",
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("receipt_sha256", sa.String(length=64), nullable=False),
        sa.Column("record_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("generation > 0", name="ck_m05_anchor_generation"),
        sa.CheckConstraint(
            "receipt_sha256 ~ '^[0-9a-f]{64}$'", name="ck_m05_anchor_receipt_sha"
        ),
        sa.CheckConstraint(
            "record_sha256 ~ '^[0-9a-f]{64}$'", name="ck_m05_anchor_record_sha"
        ),
        sa.PrimaryKeyConstraint("generation", name="pk_m05_activation_database_anchor"),
        schema="ops",
    )
    op.execute(
        """
        CREATE FUNCTION ops.guard_m05_activation_database_anchor_append_only()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY INVOKER
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION '% is append-only', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
                USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_m05_activation_database_anchor_append_only
        BEFORE UPDATE OR DELETE ON ops.m05_activation_database_anchor
        FOR EACH ROW EXECUTE FUNCTION ops.guard_m05_activation_database_anchor_append_only()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_m05_activation_database_anchor_truncate_append_only
        BEFORE TRUNCATE ON ops.m05_activation_database_anchor
        FOR EACH STATEMENT EXECUTE FUNCTION ops.guard_m05_activation_database_anchor_append_only()
        """
    )
    op.execute(
        "ALTER TABLE ops.m05_activation_database_anchor "
        "ENABLE ALWAYS TRIGGER trg_m05_activation_database_anchor_append_only"
    )
    op.execute(
        "ALTER TABLE ops.m05_activation_database_anchor "
        "ENABLE ALWAYS TRIGGER trg_m05_activation_database_anchor_truncate_append_only"
    )
    # generation/해시만 담긴 공개 검증 anchor이며 비밀 credential은 저장하지 않는다.
    op.execute("GRANT USAGE ON SCHEMA ops TO PUBLIC")
    op.execute("GRANT SELECT ON ops.m05_activation_database_anchor TO PUBLIC")


def downgrade() -> None:
    raise RuntimeError("M05 activation database anchor migration is forward-only")
