"""M05 activation generation을 app schema 복원과 분리된 DB append-only anchor에 봉인한다."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0062"
down_revision: str | None = "20260821_0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260824_0062'"
)


def upgrade() -> None:
    # 이 migration 자체가 Alembic head를 전진시키므로, final boundary의 schema pin도
    # 같은 트랜잭션에서 함께 전진시킨다. pin을 빠뜨리면 boundary는 의도대로 fail-close한다.
    op.drop_constraint(
        op.f("ck_ktm_ct_boundary_contract"),
        "ktm_cache_target_boundary_audits",
        schema="app",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_ktm_ct_boundary_contract"),
        "ktm_cache_target_boundary_audits",
        _BOUNDARY_CONTRACT_CHECK,
        schema="app",
    )
    op.execute("CREATE SCHEMA IF NOT EXISTS ops")
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT to_regclass('ops.m05_activation_database_anchor')")) is None:
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
            sa.CheckConstraint("record_sha256 ~ '^[0-9a-f]{64}$'", name="ck_m05_anchor_record_sha"),
            sa.PrimaryKeyConstraint("generation", name="pk_m05_activation_database_anchor"),
            schema="ops",
        )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ops.guard_m05_activation_database_anchor_append_only()
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
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                  FROM pg_trigger
                 WHERE tgname = 'trg_m05_activation_database_anchor_append_only'
                   AND tgrelid = 'ops.m05_activation_database_anchor'::regclass
            ) THEN
                CREATE TRIGGER trg_m05_activation_database_anchor_append_only
                BEFORE UPDATE OR DELETE ON ops.m05_activation_database_anchor
                FOR EACH ROW EXECUTE FUNCTION ops.guard_m05_activation_database_anchor_append_only();
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                  FROM pg_trigger
                 WHERE tgname = 'trg_m05_activation_database_anchor_truncate_append_only'
                   AND tgrelid = 'ops.m05_activation_database_anchor'::regclass
            ) THEN
                CREATE TRIGGER trg_m05_activation_database_anchor_truncate_append_only
                BEFORE TRUNCATE ON ops.m05_activation_database_anchor
                FOR EACH STATEMENT EXECUTE FUNCTION ops.guard_m05_activation_database_anchor_append_only();
            END IF;
        END
        $$;
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
