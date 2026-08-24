"""M05 schema-swap에 필요한 admin 감사 원장 계약을 fail-closed로 고정한다.

Revision ID: 20260824_0063
Revises: 20260824_0062
Create Date: 2026-08-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0063"
down_revision: str | None = "20260824_0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260824_0063'"
)


def upgrade() -> None:
    # 이 migration은 restore 후 API가 post-cutover reflection을 기존 audit chain에
    # append할 수 있다는 M05 전제를 강화한다. 기존 generic trigger는 location retention
    # 예외를 포함하므로 admin 원장에는 전용 SECURITY INVOKER guard를 사용한다.
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
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION app.guard_admin_audit_log_append_only()
            RETURNS trigger
            LANGUAGE plpgsql
            SECURITY INVOKER
            SET search_path = pg_catalog
            AS $function$BEGIN
                IF TG_OP = 'INSERT' THEN
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION '% is append-only', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
                    USING ERRCODE = '55000';
            END;$function$
            """
        )
    )
    op.execute("DROP TRIGGER IF EXISTS trg_admin_audit_log_append_only ON app.admin_audit_log")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_admin_audit_log_truncate_append_only ON app.admin_audit_log"
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_admin_audit_log_append_only
            BEFORE INSERT OR UPDATE OR DELETE ON app.admin_audit_log
            FOR EACH ROW EXECUTE FUNCTION app.guard_admin_audit_log_append_only()
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_admin_audit_log_truncate_append_only
            BEFORE TRUNCATE ON app.admin_audit_log
            FOR EACH STATEMENT EXECUTE FUNCTION app.guard_admin_audit_log_append_only()
            """
        )
    )
    for trigger_name in (
        "trg_admin_audit_log_append_only",
        "trg_admin_audit_log_truncate_append_only",
    ):
        op.execute(
            sa.text(f"ALTER TABLE app.admin_audit_log ENABLE ALWAYS TRIGGER {trigger_name}")
        )


def downgrade() -> None:
    raise RuntimeError("M05 admin audit guard migration is forward-only")
