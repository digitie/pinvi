"""M05 activation 계약을 새 Alembic 기준선 위에 한 번에 적용한다.

Revision ID: 20260824_0101
Revises: 20260824_0100
Create Date: 2026-08-24

`20260824_0062`~`0064`의 최종 DDL만 보존한다. 이 revision은 새 설치와
ADR-062의 명시적 0061 rebaseline 뒤에만 실행된다.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0101"
down_revision: str | None = "20260824_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_M05_SCHEMA_FILE = "20260824_0101_m05_activation.sql"
_M05_SCHEMA_SHA256 = "128e2b374842ca2e9755041815457625a8c2212c013c1bafd6adb93db42128cb"
_M05_SCHEMA_STATEMENT_COUNT = 21
_DOLLAR_QUOTE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")
_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260824_0101'"
)


def _split_postgres_statements(source: str) -> tuple[str, ...]:
    """dollar-quoted function body를 보존한 채 top-level SQL 문만 분리한다."""

    statements: list[str] = []
    buffer: list[str] = []
    index = 0
    quote: str | None = None
    dollar_quote: str | None = None

    while index < len(source):
        if dollar_quote is not None:
            if source.startswith(dollar_quote, index):
                buffer.append(dollar_quote)
                index += len(dollar_quote)
                dollar_quote = None
            else:
                buffer.append(source[index])
                index += 1
            continue

        if quote is not None:
            character = source[index]
            buffer.append(character)
            index += 1
            if character == quote:
                if index < len(source) and source[index] == quote:
                    buffer.append(source[index])
                    index += 1
                else:
                    quote = None
            continue

        if source.startswith("--", index):
            newline = source.find("\n", index)
            index = len(source) if newline == -1 else newline + 1
            continue
        if source.startswith("/*", index):
            comment_end = source.find("*/", index + 2)
            if comment_end == -1:
                raise RuntimeError("0101 M05 schema artifact has an unterminated block comment")
            index = comment_end + 2
            continue

        character = source[index]
        if character in "'\"":
            quote = character
            buffer.append(character)
            index += 1
            continue
        if character == "$":
            match = _DOLLAR_QUOTE.match(source, index)
            if match is not None:
                dollar_quote = match.group(0)
                buffer.append(dollar_quote)
                index += len(dollar_quote)
                continue
        if character == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer.clear()
            index += 1
            continue
        buffer.append(character)
        index += 1

    if quote is not None or dollar_quote is not None:
        raise RuntimeError("0101 M05 schema artifact has an unterminated SQL literal")
    trailing = "".join(buffer).strip()
    if trailing:
        raise RuntimeError("0101 M05 schema artifact has a trailing SQL statement")
    if len(statements) != _M05_SCHEMA_STATEMENT_COUNT:
        raise RuntimeError("0101 M05 schema artifact statement count is invalid")
    return tuple(statements)


def _m05_schema_statements() -> tuple[str, ...]:
    path = Path(__file__).resolve().parents[1] / "baselines" / _M05_SCHEMA_FILE
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise RuntimeError("0101 M05 schema artifact is unavailable") from exc
    if hashlib.sha256(payload).hexdigest() != _M05_SCHEMA_SHA256:
        raise RuntimeError("0101 M05 schema artifact digest is invalid")
    try:
        source = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("0101 M05 schema artifact is not UTF-8") from exc
    return _split_postgres_statements(source)


def _reject_unsafe_m05_default_privileges(bind: sa.Connection) -> None:
    """M05 object에 권한이 전파될 default ACL이 있으면 DDL 전에 중단한다."""

    unsafe_default_acl = bind.scalar(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_default_acl default_acl
                WHERE default_acl.defaclrole = current_user::regrole
                  AND (
                    default_acl.defaclnamespace = 0
                    OR default_acl.defaclnamespace = (
                        SELECT namespace.oid
                        FROM pg_namespace namespace
                        WHERE namespace.nspname = 'ops'
                    )
                  )
            )
            """
        )
    )
    if unsafe_default_acl is True:
        raise RuntimeError("0101 rejects migration-owner default privileges for M05 objects")


def _reject_existing_m05_objects(bind: sa.Connection) -> None:
    """부분 적용된 과거 M05 object 위로 덮어쓰지 않는다."""

    existing = bind.scalar(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_class relation
                JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = 'ops'
                  AND relation.relname IN (
                    'm05_activation_database_anchor',
                    'm05_hotswap_release_receipts'
                  )
                UNION ALL
                SELECT 1
                FROM pg_proc procedure
                JOIN pg_namespace namespace ON namespace.oid = procedure.pronamespace
                WHERE namespace.nspname = 'ops'
                  AND procedure.proname IN (
                    'guard_m05_activation_database_anchor_append_only',
                    'guard_m05_hotswap_release_receipts_append_only',
                    'm05_hotswap_release_topology_sha256',
                    'record_m05_hotswap_release_receipt',
                    'verify_m05_hotswap_release_receipt'
                  )
            )
            """
        )
    )
    if existing is True:
        raise RuntimeError("0101 refuses to replace pre-existing M05 objects")


def _advance_boundary_contract() -> None:
    """finalize가 기준선 이후 M05 계약만 수용하도록 revision pin을 전진시킨다."""

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


def _replace_admin_audit_guard() -> None:
    """restore 뒤 admin reflection도 기존 원장에 append만 하도록 고정한다."""

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
        "DROP TRIGGER IF EXISTS trg_admin_audit_log_truncate_append_only "
        "ON app.admin_audit_log"
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


def _grant_receipt_fence_access(bind: sa.Connection) -> None:
    """database owner fence에 receipt read와 세 security-definer execute만 허용한다."""

    bind.execute(
        sa.text(
            """
            DO $m05$
            DECLARE
                fence_role name;
            BEGIN
                SELECT database_row.datdba::regrole::text::name
                  INTO fence_role
                  FROM pg_database database_row
                 WHERE database_row.datname = current_database();
                EXECUTE format(
                    'GRANT SELECT ON TABLE ops.m05_hotswap_release_receipts TO %I',
                    fence_role
                );
                EXECUTE format(
                    'GRANT EXECUTE ON FUNCTION '
                    || 'ops.m05_hotswap_release_topology_sha256(name, name, name, name, name, name) '
                    || 'TO %I',
                    fence_role
                );
                EXECUTE format(
                    'GRANT EXECUTE ON FUNCTION '
                    || 'ops.record_m05_hotswap_release_receipt('
                    || 'uuid, text, text, text, text, text, text, text, name, name, name, '
                    || 'name, name, name, oid, oid, oid, oid, jsonb, jsonb, boolean, text) '
                    || 'TO %I',
                    fence_role
                );
                EXECUTE format(
                    'GRANT EXECUTE ON FUNCTION '
                    || 'ops.verify_m05_hotswap_release_receipt(uuid, text) '
                    || 'TO %I',
                    fence_role
                );
            END
            $m05$
            """
        )
    )


def _harden_m05_acl(bind: sa.Connection) -> None:
    """public verification 범위와 fence capability를 최소 권한으로 확정한다."""

    op.execute("REVOKE ALL ON SCHEMA ops FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA ops TO PUBLIC")
    op.execute("REVOKE ALL PRIVILEGES ON TABLE ops.m05_activation_database_anchor FROM PUBLIC")
    op.execute("GRANT SELECT ON TABLE ops.m05_activation_database_anchor TO PUBLIC")
    op.execute("REVOKE ALL PRIVILEGES ON TABLE ops.m05_hotswap_release_receipts FROM PUBLIC")
    for signature in (
        "ops.guard_m05_activation_database_anchor_append_only()",
        "ops.guard_m05_hotswap_release_receipts_append_only()",
        "ops.m05_hotswap_release_topology_sha256(name, name, name, name, name, name)",
        "ops.record_m05_hotswap_release_receipt("
        "uuid, text, text, text, text, text, text, text, name, name, name, name, name, "
        "name, oid, oid, oid, oid, jsonb, jsonb, boolean, text)",
        "ops.verify_m05_hotswap_release_receipt(uuid, text)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    _grant_receipt_fence_access(bind)


def _assert_m05_acl(bind: sa.Connection) -> None:
    """M05 object owner와 공개/fence ACL이 정확히 기대한 surface인지 검사한다."""

    acl_is_exact = bind.scalar(
        sa.text(
            """
            WITH fence_role AS (
                SELECT database_row.datdba AS oid
                FROM pg_database database_row
                WHERE database_row.datname = current_database()
            ),
            m05_schema AS (
                SELECT namespace.oid, namespace.nspowner, namespace.nspacl
                FROM pg_namespace namespace
                WHERE namespace.nspname = 'ops'
            ),
            anchor_table AS (
                SELECT relation.oid, relation.relowner, relation.relacl
                FROM pg_class relation
                JOIN m05_schema schema ON schema.oid = relation.relnamespace
                WHERE relation.relname = 'm05_activation_database_anchor'
                  AND relation.relkind = 'r'
            ),
            receipt_table AS (
                SELECT relation.oid, relation.relowner, relation.relacl
                FROM pg_class relation
                JOIN m05_schema schema ON schema.oid = relation.relnamespace
                WHERE relation.relname = 'm05_hotswap_release_receipts'
                  AND relation.relkind = 'r'
            ),
            guard_functions AS (
                SELECT procedure.oid, procedure.proowner, procedure.proacl, procedure.prosecdef
                FROM pg_proc procedure
                JOIN m05_schema schema ON schema.oid = procedure.pronamespace
                WHERE procedure.oid IN (
                    'ops.guard_m05_activation_database_anchor_append_only()'::regprocedure,
                    'ops.guard_m05_hotswap_release_receipts_append_only()'::regprocedure
                )
            ),
            receipt_functions AS (
                SELECT procedure.oid, procedure.proowner, procedure.proacl, procedure.prosecdef
                FROM pg_proc procedure
                JOIN m05_schema schema ON schema.oid = procedure.pronamespace
                WHERE procedure.oid IN (
                    'ops.m05_hotswap_release_topology_sha256(name, name, name, name, name, name)'::regprocedure,
                    'ops.record_m05_hotswap_release_receipt(uuid, text, text, text, text, text, text, text, name, name, name, name, name, name, oid, oid, oid, oid, jsonb, jsonb, boolean, text)'::regprocedure,
                    'ops.verify_m05_hotswap_release_receipt(uuid, text)'::regprocedure
                )
            )
            SELECT
                (SELECT count(*) FROM fence_role) = 1
                AND (SELECT count(*) FROM m05_schema) = 1
                AND (SELECT count(*) FROM anchor_table) = 1
                AND (SELECT count(*) FROM receipt_table) = 1
                AND (SELECT count(*) FROM guard_functions) = 2
                AND (SELECT count(*) FROM receipt_functions) = 3
                AND NOT EXISTS (
                    SELECT 1 FROM m05_schema schema
                    WHERE schema.nspowner <> current_user::regrole
                )
                AND NOT EXISTS (
                    SELECT 1 FROM anchor_table relation
                    WHERE relation.relowner <> current_user::regrole
                )
                AND NOT EXISTS (
                    SELECT 1 FROM receipt_table relation
                    WHERE relation.relowner <> current_user::regrole
                )
                AND NOT EXISTS (
                    SELECT 1 FROM guard_functions procedure
                    WHERE procedure.proowner <> current_user::regrole OR procedure.prosecdef
                )
                AND NOT EXISTS (
                    SELECT 1 FROM receipt_functions procedure
                    WHERE procedure.proowner <> current_user::regrole OR NOT procedure.prosecdef
                )
                AND EXISTS (
                    SELECT 1
                    FROM m05_schema schema
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(schema.nspacl, acldefault('n', schema.nspowner))
                    ) acl
                    WHERE acl.grantee = 0 AND acl.privilege_type = 'USAGE'
                      AND NOT acl.is_grantable
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM m05_schema schema
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(schema.nspacl, acldefault('n', schema.nspowner))
                    ) acl
                    WHERE NOT (
                        acl.grantee = schema.nspowner
                        OR (acl.grantee = 0 AND acl.privilege_type = 'USAGE'
                            AND NOT acl.is_grantable)
                    )
                )
                AND EXISTS (
                    SELECT 1
                    FROM anchor_table relation
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(relation.relacl, acldefault('r', relation.relowner))
                    ) acl
                    WHERE acl.grantee = 0 AND acl.privilege_type = 'SELECT'
                      AND NOT acl.is_grantable
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM anchor_table relation
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(relation.relacl, acldefault('r', relation.relowner))
                    ) acl
                    WHERE NOT (
                        acl.grantee = relation.relowner
                        OR (acl.grantee = 0 AND acl.privilege_type = 'SELECT'
                            AND NOT acl.is_grantable)
                    )
                )
                AND EXISTS (
                    SELECT 1
                    FROM receipt_table relation
                    CROSS JOIN fence_role fence
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(relation.relacl, acldefault('r', relation.relowner))
                    ) acl
                    WHERE acl.grantee = fence.oid AND acl.privilege_type = 'SELECT'
                      AND NOT acl.is_grantable
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM receipt_table relation
                    CROSS JOIN fence_role fence
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(relation.relacl, acldefault('r', relation.relowner))
                    ) acl
                    WHERE NOT (
                        acl.grantee = relation.relowner
                        OR (acl.grantee = fence.oid AND acl.privilege_type = 'SELECT'
                            AND NOT acl.is_grantable)
                    )
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM guard_functions procedure
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(procedure.proacl, acldefault('f', procedure.proowner))
                    ) acl
                    WHERE acl.grantee <> procedure.proowner
                )
                AND (
                    SELECT count(*)
                    FROM receipt_functions procedure
                    CROSS JOIN fence_role fence
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(procedure.proacl, acldefault('f', procedure.proowner))
                    ) acl
                    WHERE acl.grantee = fence.oid AND acl.privilege_type = 'EXECUTE'
                      AND NOT acl.is_grantable
                ) = 3
                AND NOT EXISTS (
                    SELECT 1
                    FROM receipt_functions procedure
                    CROSS JOIN fence_role fence
                    CROSS JOIN LATERAL aclexplode(
                        COALESCE(procedure.proacl, acldefault('f', procedure.proowner))
                    ) acl
                    WHERE NOT (
                        acl.grantee = procedure.proowner
                        OR (acl.grantee = fence.oid AND acl.privilege_type = 'EXECUTE'
                            AND NOT acl.is_grantable)
                    )
                )
            """
        )
    )
    if acl_is_exact is not True:
        raise RuntimeError("0101 M05 ACL is not canonical")


def upgrade() -> None:
    # named ops default ACL까지 검사하려면 schema를 먼저 확보해야 한다. 이 revision은
    # partial legacy M05 object를 덮어쓰지 않고 transaction 전체를 fail-close한다.
    op.execute("CREATE SCHEMA IF NOT EXISTS ops")
    bind = op.get_bind()
    _reject_unsafe_m05_default_privileges(bind)
    _reject_existing_m05_objects(bind)
    _advance_boundary_contract()
    _replace_admin_audit_guard()
    op.execute("SET LOCAL check_function_bodies = false")
    for statement in _m05_schema_statements():
        op.execute(sa.text(statement))
    _harden_m05_acl(bind)
    _assert_m05_acl(bind)


def downgrade() -> None:
    raise RuntimeError("0101 M05 activation contract migration is forward-only")
