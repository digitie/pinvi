"""현재 main과 M05 계약을 새 Alembic 기준선 위에 한 번에 적용한다.

Revision ID: 20260824_0101
Revises: 20260824_0100
Create Date: 2026-08-24

N150의 `0061` 기준선 뒤에 합류한 location-audit·동의 이력·좌표 출처 변경과 M05의
옛 `0062`~`0065` DDL을 모두 이 revision에 통합한다. 이 revision은 새 설치와
ADR-065의 명시적 `0061` rebaseline 뒤에만 실행된다.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import stat
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
_ROLE_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*")
_OPERATOR_NAME = re.compile(r"[-+*/<>=~!@#%^&|`?]+")
_BOUNDARY_CONTRACT_CHECK = (
    "contract_version = 'pinvi-cache-target-final-boundary/v1' "
    "AND status = 'succeeded' AND schema_revision = '20260824_0101'"
)
_LOCATION_ACCESS_LOG_PURPOSE_CONSTRAINT = "ck_location_access_log_ck_location_access_log_purpose"
_LOCATION_ACCESS_LOG_PURPOSES = (
    "'viewport_query', 'nearby_attractions', 'weather_at_coord', "
    "'feature_request', 'region_covering', 'region_radius', 'third_party_place_search', "
    "'reverse_geocode'"
)
_LOCATION_AUDIT_COORD_SOURCE_CHECK = (
    "coord_source IS NULL OR coord_source IN ('device', 'map_pick')"
)
_LEGACY_REBASELINE_RECEIPT_PATH_ENV = "PINVI_M05_LEGACY_REBASELINE_RECEIPT_PATH"
_LEGACY_REBASELINE_RECEIPT_FIELDS = frozenset(
    {
        "action",
        "backup_manifest_sha256",
        "backup_sha256",
        "completed_at",
        "preflight",
        "state",
        "target_manifest_sha256",
        "version",
    }
)
_LEGACY_REBASELINE_PREFLIGHT_FIELDS = frozenset(
    {
        "app_data_content_sha256",
        "app_data_rows",
        "app_data_table_lines",
        "catalog_lines",
        "catalog_sha256",
        "current_user",
        "database_name",
        "database_oid",
        "expected_catalog_lines",
        "expected_catalog_sha256",
        "server_addr",
        "server_port",
        "server_version_num",
        "session_user",
        "system_identifier",
        "version_rows",
    }
)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_LEGACY_REBASELINE_FINGERPRINT_SESSION_STATEMENTS = (
    "SET LOCAL TIME ZONE 'UTC'",
    "SET LOCAL DateStyle TO 'ISO, YMD'",
    "SET LOCAL IntervalStyle TO 'iso_8601'",
    "SET LOCAL bytea_output TO 'hex'",
    "SET LOCAL extra_float_digits TO 3",
)
# `scripts/alembic_rebaseline.py`의 0061 preflight와 같은 catalog serialization이다.
# 0101은 receipt를 만든 뒤의 data/catalog drift를 DDL 전에 다시 검증해야 하므로, 이
# forward-only migration 안에도 독립적으로 남긴다.
_LEGACY_REBASELINE_CATALOG_FINGERPRINT_SQL = """
WITH object_lines(line) AS (
  SELECT jsonb_build_array('schema', n.nspname, pg_get_userbyid(n.nspowner),
                           COALESCE(n.nspacl::text, ''))::text
  FROM pg_namespace AS n
  WHERE n.nspname = 'app'
  UNION ALL
  SELECT jsonb_build_array('relation', c.relname, c.relkind, c.relpersistence,
                           pg_get_userbyid(c.relowner), COALESCE(c.reloptions::text, ''),
                           COALESCE(c.relacl::text, ''), c.relrowsecurity,
                           c.relforcerowsecurity, c.relispartition,
                           COALESCE(pg_get_expr(c.relpartbound, c.oid, true), ''),
                           COALESCE(pg_get_partkeydef(c.oid), ''))::text
  FROM pg_class AS c
  JOIN pg_namespace AS n ON n.oid = c.relnamespace
  WHERE n.nspname = 'app' AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f', 'c')
  UNION ALL
  SELECT jsonb_build_array('column', c.relname, a.attname, a.attnum,
                           pg_catalog.format_type(a.atttypid, a.atttypmod), a.attnotnull,
                           a.attidentity, a.attgenerated,
                           COALESCE(pg_get_expr(d.adbin, d.adrelid), ''),
                           COALESCE(a.attcollation::regcollation::text, ''))::text
  FROM pg_attribute AS a
  JOIN pg_class AS c ON c.oid = a.attrelid
  JOIN pg_namespace AS n ON n.oid = c.relnamespace
  LEFT JOIN pg_attrdef AS d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
  WHERE n.nspname = 'app' AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'c')
    AND a.attnum > 0 AND NOT a.attisdropped
  UNION ALL
  SELECT jsonb_build_array(
      'type', type_row.typname, type_row.typtype,
      pg_get_userbyid(type_row.typowner), COALESCE(type_row.typacl::text, ''),
      CASE WHEN type_row.typbasetype = 0 THEN ''
           ELSE pg_catalog.format_type(type_row.typbasetype, type_row.typtypmod) END,
      type_row.typnotnull, COALESCE(type_row.typdefault, ''),
      CASE WHEN type_row.typcollation = 0 THEN ''
           ELSE type_row.typcollation::regcollation::text END
    )::text
  FROM pg_type AS type_row
  JOIN pg_namespace AS n ON n.oid = type_row.typnamespace
  WHERE n.nspname = 'app'
    AND type_row.typrelid = 0
    AND type_row.typelem = 0
    AND type_row.typtype <> 'p'
  UNION ALL
  SELECT jsonb_build_array(
      'enum', type_row.typname, enum_row.enumsortorder, enum_row.enumlabel
    )::text
  FROM pg_enum AS enum_row
  JOIN pg_type AS type_row ON type_row.oid = enum_row.enumtypid
  JOIN pg_namespace AS n ON n.oid = type_row.typnamespace
  WHERE n.nspname = 'app'
  UNION ALL
  SELECT jsonb_build_array(
      'domain_constraint', type_row.typname, constraint_row.conname,
      constraint_row.condeferrable, constraint_row.condeferred,
      constraint_row.convalidated, pg_get_constraintdef(constraint_row.oid, true)
    )::text
  FROM pg_constraint AS constraint_row
  JOIN pg_type AS type_row ON type_row.oid = constraint_row.contypid
  JOIN pg_namespace AS n ON n.oid = type_row.typnamespace
  WHERE n.nspname = 'app' AND constraint_row.contypid <> 0
  UNION ALL
  SELECT jsonb_build_array(
      'composite_type', type_row.typname, pg_get_userbyid(type_row.typowner),
      COALESCE(type_row.typacl::text, '')
    )::text
  FROM pg_type AS type_row
  JOIN pg_class AS relation ON relation.oid = type_row.typrelid
  JOIN pg_namespace AS n ON n.oid = type_row.typnamespace
  WHERE n.nspname = 'app' AND relation.relkind = 'c'
  UNION ALL
  SELECT jsonb_build_array(
      'operator', operator_row.oprname, operator_row.oprkind,
      pg_get_userbyid(operator_row.oprowner), operator_row.oprcanmerge,
      operator_row.oprcanhash,
      CASE WHEN operator_row.oprleft = 0 THEN ''
           ELSE pg_catalog.format_type(operator_row.oprleft, NULL::integer) END,
      CASE WHEN operator_row.oprright = 0 THEN ''
           ELSE pg_catalog.format_type(operator_row.oprright, NULL::integer) END,
      pg_catalog.format_type(operator_row.oprresult, NULL::integer),
      CASE WHEN operator_row.oprcom = 0 THEN ''
           ELSE operator_row.oprcom::regoperator::text END,
      CASE WHEN operator_row.oprnegate = 0 THEN ''
           ELSE operator_row.oprnegate::regoperator::text END,
      operator_row.oprcode::regprocedure::text,
      CASE WHEN operator_row.oprrest = 0 THEN ''
           ELSE operator_row.oprrest::regprocedure::text END,
      CASE WHEN operator_row.oprjoin = 0 THEN ''
           ELSE operator_row.oprjoin::regprocedure::text END
    )::text
  FROM pg_operator AS operator_row
  JOIN pg_namespace AS n ON n.oid = operator_row.oprnamespace
  WHERE n.nspname = 'app'
  UNION ALL
  SELECT jsonb_build_array('constraint', c.relname, con.conname, con.contype,
                           con.condeferrable, con.condeferred, con.convalidated,
                           con.conkey::text,
                           CASE WHEN con.confrelid = 0 THEN ''
                                ELSE con.confrelid::regclass::text END,
                           con.confkey::text, con.confupdtype, con.confdeltype,
                           con.confmatchtype,
                           pg_get_constraintdef(con.oid, true))::text
  FROM pg_constraint AS con
  JOIN pg_class AS c ON c.oid = con.conrelid
  JOIN pg_namespace AS n ON n.oid = c.relnamespace
  WHERE n.nspname = 'app'
  UNION ALL
  SELECT jsonb_build_array('index', table_rel.relname, index_rel.relname,
                           i.indisunique, i.indisprimary, i.indisvalid, i.indisready,
                           i.indkey::text, i.indclass::text, i.indcollation::text,
                           i.indoption::text, pg_get_indexdef(i.indexrelid),
                           COALESCE(pg_get_expr(i.indexprs, i.indrelid, true), ''),
                           COALESCE(pg_get_expr(i.indpred, i.indrelid, true), ''))::text
  FROM pg_index AS i
  JOIN pg_class AS table_rel ON table_rel.oid = i.indrelid
  JOIN pg_class AS index_rel ON index_rel.oid = i.indexrelid
  JOIN pg_namespace AS n ON n.oid = table_rel.relnamespace
  WHERE n.nspname = 'app'
  UNION ALL
  SELECT jsonb_build_array('function', p.oid::regprocedure::text, l.lanname,
                           p.prosecdef, p.proleakproof, p.proisstrict, p.provolatile,
                           p.proparallel, COALESCE(p.proconfig::text, ''),
                           COALESCE(p.prosrc, ''), COALESCE(p.proacl::text, ''))::text
  FROM pg_proc AS p
  JOIN pg_namespace AS n ON n.oid = p.pronamespace
  JOIN pg_language AS l ON l.oid = p.prolang
  WHERE n.nspname = 'app'
  UNION ALL
  SELECT jsonb_build_array('trigger', c.relname, t.tgname, t.tgenabled, t.tgtype,
                           t.tgfoid::regprocedure::text, encode(t.tgargs, 'hex'),
                           t.tgattr::text)::text
  FROM pg_trigger AS t
  JOIN pg_class AS c ON c.oid = t.tgrelid
  JOIN pg_namespace AS n ON n.oid = c.relnamespace
  WHERE n.nspname = 'app' AND NOT t.tgisinternal
  UNION ALL
  SELECT jsonb_build_array(
      'policy', relation.relname, policy.polname, policy.polpermissive,
      policy.polcmd,
      COALESCE(array_to_string(ARRAY(
        SELECT pg_get_userbyid(role_oid)
        FROM unnest(policy.polroles) AS role_oid
        ORDER BY pg_get_userbyid(role_oid)
      ), ','), ''),
      COALESCE(pg_get_expr(policy.polqual, policy.polrelid, true), ''),
      COALESCE(pg_get_expr(policy.polwithcheck, policy.polrelid, true), '')
    )::text
  FROM pg_policy AS policy
  JOIN pg_class AS relation ON relation.oid = policy.polrelid
  JOIN pg_namespace AS n ON n.oid = relation.relnamespace
  WHERE n.nspname = 'app'
  UNION ALL
  SELECT jsonb_build_array(
      'rule', relation.relname, rewrite.rulename, rewrite.ev_type,
      rewrite.ev_enabled, rewrite.is_instead, pg_get_ruledef(rewrite.oid, true)
    )::text
  FROM pg_rewrite AS rewrite
  JOIN pg_class AS relation ON relation.oid = rewrite.ev_class
  JOIN pg_namespace AS n ON n.oid = relation.relnamespace
  WHERE n.nspname = 'app'
  UNION ALL
  SELECT jsonb_build_array('extension', e.extname, e.extversion, n.nspname)::text
  FROM pg_extension AS e
  JOIN pg_namespace AS n ON n.oid = e.extnamespace
  WHERE e.extname IN ('pgcrypto', 'pg_trgm', 'citext')
  UNION ALL
  SELECT jsonb_build_array('default_acl', COALESCE(n.nspname, ''),
                           d.defaclrole::regrole::text, d.defaclobjtype,
                           COALESCE(d.defaclacl::text, ''))::text
  FROM pg_default_acl AS d
  LEFT JOIN pg_namespace AS n ON n.oid = d.defaclnamespace
  WHERE n.nspname = 'app' OR n.nspname IS NULL
)
SELECT line FROM object_lines ORDER BY line COLLATE "C"
"""
_LEGACY_REBASELINE_APP_TABLES_SQL = """
SELECT relation.relname
FROM pg_class AS relation
JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
WHERE namespace.nspname = 'app'
  AND relation.relkind IN ('r', 'p')
ORDER BY relation.relname COLLATE "C"
"""
_LEGACY_REBASELINE_SERIALIZATION_LOCK_SQL = "SELECT pg_advisory_xact_lock(1863432274, 20260824)"
# legacy handoff도 새 backend를 막는 database catalog fence 뒤 기존 DDL-capable
# backend를 종료한다. database owner만으로는 다른 role backend를 종료할 수 없으므로
# root-only superuser caller만 허용해 handoff 중간의 permission failure를 막는다.
_LEGACY_REBASELINE_DATABASE_FENCE_AUTHORITY_SQL = """
SELECT current_role_row.rolsuper
FROM pg_roles AS current_role_row
WHERE current_role_row.rolname = current_user
  AND session_user = current_user
"""
_LEGACY_REBASELINE_DATABASE_FENCE_LOCK_TIMEOUT_SQL = "SET LOCAL lock_timeout = '5s'"
_LEGACY_REBASELINE_DATABASE_FENCE_LOCK_TIMEOUT_RESET_SQL = "SET LOCAL lock_timeout = 0"
_LEGACY_REBASELINE_DDL_CAPABLE_SESSIONS_CTE = """
WITH app_schema AS (
  SELECT namespace.oid, namespace.nspowner
  FROM pg_namespace AS namespace
  WHERE namespace.nspname = 'app'
),
app_catalog_owners(owner_oid) AS (
  SELECT schema.nspowner FROM app_schema AS schema
  UNION
  SELECT relation.relowner
  FROM pg_class AS relation
  JOIN app_schema AS schema ON schema.oid = relation.relnamespace
  UNION
  SELECT procedure.proowner
  FROM pg_proc AS procedure
  JOIN app_schema AS schema ON schema.oid = procedure.pronamespace
  UNION
  SELECT type_row.typowner
  FROM pg_type AS type_row
  JOIN app_schema AS schema ON schema.oid = type_row.typnamespace
  UNION
  SELECT operator_row.oprowner
  FROM pg_operator AS operator_row
  JOIN app_schema AS schema ON schema.oid = operator_row.oprnamespace
  UNION
  SELECT collation_row.collowner
  FROM pg_collation AS collation_row
  JOIN app_schema AS schema ON schema.oid = collation_row.collnamespace
  UNION
  SELECT conversion_row.conowner
  FROM pg_conversion AS conversion_row
  JOIN app_schema AS schema ON schema.oid = conversion_row.connamespace
  UNION
  SELECT opclass_row.opcowner
  FROM pg_opclass AS opclass_row
  JOIN app_schema AS schema ON schema.oid = opclass_row.opcnamespace
  UNION
  SELECT opfamily_row.opfowner
  FROM pg_opfamily AS opfamily_row
  JOIN app_schema AS schema ON schema.oid = opfamily_row.opfnamespace
  UNION
  SELECT config_row.cfgowner
  FROM pg_ts_config AS config_row
  JOIN app_schema AS schema ON schema.oid = config_row.cfgnamespace
  UNION
  SELECT dictionary_row.dictowner
  FROM pg_ts_dict AS dictionary_row
  JOIN app_schema AS schema ON schema.oid = dictionary_row.dictnamespace
  UNION
  SELECT statistic_row.stxowner
  FROM pg_statistic_ext AS statistic_row
  JOIN app_schema AS schema ON schema.oid = statistic_row.stxnamespace
  UNION
  SELECT extension_row.extowner
  FROM pg_extension AS extension_row
  JOIN app_schema AS schema ON schema.oid = extension_row.extnamespace
),
ddl_capable_sessions(pid) AS (
  SELECT activity.pid
  FROM pg_stat_activity AS activity
  LEFT JOIN pg_roles AS role_row ON role_row.oid = activity.usesysid
  WHERE activity.datname = current_database()
    AND activity.backend_type = 'client backend'
    AND activity.pid <> pg_backend_pid()
    AND (
      COALESCE(role_row.rolsuper, false)
      OR COALESCE(has_schema_privilege(activity.usesysid, 'app', 'CREATE'), false)
      OR EXISTS (
        SELECT 1
        FROM app_catalog_owners AS owner_row
        WHERE activity.usesysid = owner_row.owner_oid
          OR COALESCE(
            pg_has_role(activity.usesysid, owner_row.owner_oid, 'USAGE'),
            false
          )
          OR COALESCE(
            pg_has_role(activity.usesysid, owner_row.owner_oid, 'SET'),
            false
          )
      )
    )
)
"""
_LEGACY_REBASELINE_DDL_QUIESCENCE_SQL = "".join(
    (
        _LEGACY_REBASELINE_DDL_CAPABLE_SESSIONS_CTE,
        "SELECT NOT EXISTS (SELECT 1 FROM ddl_capable_sessions)",
    )
)
_LEGACY_REBASELINE_DDL_CAPABLE_SESSION_IDS_SQL = "".join(
    (
        _LEGACY_REBASELINE_DDL_CAPABLE_SESSIONS_CTE,
        "SELECT pid FROM ddl_capable_sessions ORDER BY pid",
    )
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


def _configured_migration_owner() -> str | None:
    """Return the explicitly configured M05 receipt owner, if this is a managed run."""

    configured = os.environ.get("PINVI_MIGRATION_OWNER")
    if configured is None or not configured.strip():
        return None
    if configured != configured.strip() or _ROLE_IDENTIFIER.fullmatch(configured) is None:
        raise RuntimeError("0101 migration owner configuration is invalid")
    return configured


def _configured_migrator_login() -> str | None:
    """Return the explicitly configured one-shot login that may activate owner roles."""

    configured = os.environ.get("PINVI_MIGRATOR_DB_USER")
    if configured is None or not configured.strip():
        return None
    if configured != configured.strip() or _ROLE_IDENTIFIER.fullmatch(configured) is None:
        raise RuntimeError("0101 migrator login configuration is invalid")
    return configured


def _configured_app_schema_owner() -> str | None:
    """Return the canonical non-login app owner used after legacy convergence."""

    configured = os.environ.get("PINVI_APP_SCHEMA_OWNER")
    if configured is None or not configured.strip():
        return None
    if configured != configured.strip() or _ROLE_IDENTIFIER.fullmatch(configured) is None:
        raise RuntimeError("0101 app schema owner configuration is invalid")
    return configured


def _configured_app_runtime_role() -> str | None:
    """Return the non-owner runtime login granted only after legacy handoff."""

    configured = os.environ.get("PINVI_APP_DB_USER")
    if configured is None or not configured.strip():
        return None
    if configured != configured.strip() or _ROLE_IDENTIFIER.fullmatch(configured) is None:
        raise RuntimeError("0101 app runtime role configuration is invalid")
    return configured


def _managed_deployment_requires_migration_owner() -> bool:
    """Keep staging/production M05 receipt ownership fail-closed."""

    environment = os.environ.get("PINVI_ENVIRONMENT", "").strip().lower()
    return environment in {"staging", "production"}


def _legacy_rebaseline_profile() -> bool:
    """Allow the one approved 0061 owner path without broadening normal migrator authority."""

    configured = os.environ.get("PINVI_M05_LEGACY_REBASELINE", "0")
    if configured == "0":
        return False
    if configured == "1":
        return True
    raise RuntimeError("0101 legacy rebaseline profile configuration is invalid")


def _read_legacy_rebaseline_receipt() -> dict[str, object]:
    """Read the root-only applied 0061→0100 receipt without a pathname race."""

    configured = os.environ.get(_LEGACY_REBASELINE_RECEIPT_PATH_ENV, "")
    if not configured:
        raise RuntimeError("0101 legacy rebaseline requires an applied root-owned receipt")
    path = Path(configured)
    if not path.is_absolute():
        raise RuntimeError("0101 legacy rebaseline receipt path must be absolute")
    if os.geteuid() != 0:
        raise RuntimeError("0101 legacy rebaseline requires a root OS account")
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise RuntimeError("0101 legacy rebaseline receipt must be root-owned mode 0600")
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            payload = stream.read(64 * 1024 + 1)
    except OSError as exc:
        raise RuntimeError("0101 legacy rebaseline receipt is unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(payload) > 64 * 1024:
        raise RuntimeError("0101 legacy rebaseline receipt is too large")

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise RuntimeError("0101 legacy rebaseline receipt has duplicate JSON keys")
            value[key] = item
        return value

    try:
        receipt = json.loads(payload.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("0101 legacy rebaseline receipt is not valid JSON") from exc
    if not isinstance(receipt, dict) or frozenset(receipt) != _LEGACY_REBASELINE_RECEIPT_FIELDS:
        raise RuntimeError("0101 legacy rebaseline receipt fields are invalid")
    if (
        receipt["action"] != "0061_to_0100_rebaseline"
        or receipt["version"] != 1
        or receipt["state"] != "applied"
        or not isinstance(receipt["completed_at"], str)
        or not receipt["completed_at"]
        or not isinstance(receipt["preflight"], dict)
        or any(
            not isinstance(receipt[field], str) or _SHA256.fullmatch(receipt[field]) is None
            for field in (
                "backup_manifest_sha256",
                "backup_sha256",
                "target_manifest_sha256",
            )
        )
    ):
        raise RuntimeError("0101 legacy rebaseline receipt values are invalid")
    preflight = receipt["preflight"]
    if frozenset(preflight) != _LEGACY_REBASELINE_PREFLIGHT_FIELDS:
        raise RuntimeError("0101 legacy rebaseline receipt preflight is invalid")
    if (
        preflight["version_rows"] != ["20260821_0061"]
        or any(
            not isinstance(preflight[field], str) or not preflight[field]
            for field in (
                "current_user",
                "database_name",
                "session_user",
                "system_identifier",
                "server_addr",
            )
        )
        or any(
            not isinstance(preflight[field], int) or isinstance(preflight[field], bool)
            for field in (
                "app_data_rows",
                "app_data_table_lines",
                "catalog_lines",
                "database_oid",
                "expected_catalog_lines",
                "server_port",
                "server_version_num",
            )
        )
        or any(
            not isinstance(preflight[field], str) or _SHA256.fullmatch(preflight[field]) is None
            for field in (
                "app_data_content_sha256",
                "catalog_sha256",
                "expected_catalog_sha256",
            )
        )
        or preflight["app_data_rows"] <= 0
        or preflight["app_data_table_lines"] <= 0
        or preflight["catalog_lines"] <= 0
        or preflight["database_oid"] <= 0
        or preflight["expected_catalog_lines"] != preflight["catalog_lines"]
        or preflight["expected_catalog_sha256"] != preflight["catalog_sha256"]
        or not 1 <= preflight["server_port"] <= 65535
        or preflight["server_version_num"] // 10000 != 16
        or not str(preflight["system_identifier"]).isdigit()
    ):
        raise RuntimeError("0101 legacy rebaseline receipt preflight is invalid")
    try:
        ipaddress.ip_address(preflight["server_addr"])
    except (TypeError, ValueError) as exc:
        raise RuntimeError("0101 legacy rebaseline receipt preflight endpoint is invalid") from exc
    return receipt


def _quote_identifier(identifier: str) -> str:
    """Quote a PostgreSQL identifier selected from trusted catalog rows."""

    return '"' + identifier.replace('"', '""') + '"'


def _normalize_legacy_rebaseline_fingerprint_session(bind: sa.Connection) -> None:
    """Keep the post-stamp fingerprint serialization identical to the helper."""

    for statement in _LEGACY_REBASELINE_FINGERPRINT_SESSION_STATEMENTS:
        bind.execute(sa.text(statement))


def _legacy_rebaseline_app_tables(bind: sa.Connection) -> tuple[str, ...]:
    return tuple(
        str(table_name)
        for table_name in bind.execute(sa.text(_LEGACY_REBASELINE_APP_TABLES_SQL)).scalars()
    )


def _lock_legacy_rebaseline_app_tables(bind: sa.Connection, tables: tuple[str, ...]) -> None:
    """Freeze the receipt-bound app rows before calculating their rebaseline digest."""

    for table_name in tables:
        bind.execute(
            sa.text(f"LOCK TABLE app.{_quote_identifier(table_name)} IN SHARE ROW EXCLUSIVE MODE")
        )


def _assert_legacy_rebaseline_ddl_quiescence(bind: sa.Connection) -> None:
    """Receipt 검증 중 app DDL을 할 수 있는 다른 세션을 fail-close한다."""

    bind.execute(sa.text("SELECT pg_stat_clear_snapshot()"))
    ddl_quiescent = bind.scalar(sa.text(_LEGACY_REBASELINE_DDL_QUIESCENCE_SQL))
    if ddl_quiescent is not True:
        raise RuntimeError("0101 legacy rebaseline requires app DDL quiescence")


def _acquire_legacy_rebaseline_database_connection_fence(bind: sa.Connection) -> None:
    """새 backend를 막고 기존 DDL 가능 client를 종료한 뒤 quiescence를 증명한다."""

    bind.execute(sa.text(_LEGACY_REBASELINE_DATABASE_FENCE_LOCK_TIMEOUT_SQL))
    try:
        has_authority = bind.scalar(sa.text(_LEGACY_REBASELINE_DATABASE_FENCE_AUTHORITY_SQL))
        if has_authority is not True:
            raise RuntimeError(
                "0101 legacy rebaseline requires superuser connection fence authority"
            )
        bind.execute(sa.text("LOCK TABLE pg_catalog.pg_database IN ACCESS EXCLUSIVE MODE"))
    except sa.exc.DBAPIError as exc:
        # pg_database AccessShare lock을 잡은 기존 backend는 DDL-capable PID 열거 전에
        # 이 fence를 막을 수 있다. 이 경우 transaction 전체를 fail-close하여 무기한
        # 대기나 부분 handoff를 남기지 않는다.
        raise RuntimeError(
            "0101 legacy rebaseline could not acquire database connection fence within 5s"
        ) from exc
    bind.execute(sa.text(_LEGACY_REBASELINE_DATABASE_FENCE_LOCK_TIMEOUT_RESET_SQL))
    for _ in range(20):
        bind.execute(sa.text("SELECT pg_stat_clear_snapshot()"))
        pids = tuple(
            int(pid)
            for pid in bind.execute(
                sa.text(_LEGACY_REBASELINE_DDL_CAPABLE_SESSION_IDS_SQL)
            ).scalars()
        )
        if not pids:
            _assert_legacy_rebaseline_ddl_quiescence(bind)
            return
        for pid in pids:
            bind.scalar(sa.text("SELECT pg_terminate_backend(:pid, 5000)"), {"pid": pid})
        bind.execute(sa.text("SELECT pg_sleep(0.05)"))
    raise RuntimeError("0101 legacy rebaseline could not prove app DDL quiescence")


def _legacy_rebaseline_catalog_fingerprint(bind: sa.Connection) -> tuple[int, str]:
    rows = tuple(
        str(line)
        for line in bind.execute(sa.text(_LEGACY_REBASELINE_CATALOG_FINGERPRINT_SQL)).scalars()
    )
    payload = ("\n".join(rows) + "\n").encode("utf-8")
    return len(rows), hashlib.sha256(payload).hexdigest()


def _legacy_rebaseline_app_data_fingerprint(
    bind: sa.Connection, tables: tuple[str, ...]
) -> tuple[int, int, str]:
    """Recreate the helper's PII-free app-data digest after the 0100 stamp."""

    digest = hashlib.sha256()
    total_rows = 0
    data_tables = tuple(table_name for table_name in tables if table_name != "alembic_version")
    for table_name in data_tables:
        digest.update(
            json.dumps(["table", table_name], ensure_ascii=True, separators=(",", ":")).encode(
                "utf-8"
            )
            + b"\n"
        )
        table_query = (
            f"SELECT to_jsonb(data_row)::text "  # noqa: S608 - pg_catalog table name is quoted
            f"FROM app.{_quote_identifier(table_name)} AS data_row "
            'ORDER BY to_jsonb(data_row)::text COLLATE "C"'
        )
        result = bind.execute(sa.text(table_query))
        try:
            for row_json in result.scalars():
                total_rows += 1
                digest.update(
                    json.dumps(
                        ["row", table_name, str(row_json)],
                        ensure_ascii=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    + b"\n"
                )
        finally:
            result.close()
    return total_rows, len(data_tables), digest.hexdigest()


def _assert_legacy_rebaseline_fingerprint(
    bind: sa.Connection, preflight: dict[str, object]
) -> None:
    """Reject receipt replay when the post-stamp legacy database has drifted."""

    bind.execute(sa.text(_LEGACY_REBASELINE_SERIALIZATION_LOCK_SQL))
    _normalize_legacy_rebaseline_fingerprint_session(bind)
    _assert_legacy_rebaseline_ddl_quiescence(bind)
    tables = _legacy_rebaseline_app_tables(bind)
    _lock_legacy_rebaseline_app_tables(bind, tables)
    catalog_lines, catalog_sha256 = _legacy_rebaseline_catalog_fingerprint(bind)
    app_data_rows, app_data_table_lines, app_data_content_sha256 = (
        _legacy_rebaseline_app_data_fingerprint(bind, tables)
    )
    actual = {
        "app_data_content_sha256": app_data_content_sha256,
        "app_data_rows": app_data_rows,
        "app_data_table_lines": app_data_table_lines,
        "catalog_lines": catalog_lines,
        "catalog_sha256": catalog_sha256,
    }
    expected = {field: preflight[field] for field in actual}
    if actual != expected:
        raise RuntimeError(
            "0101 legacy rebaseline receipt data or catalog fingerprint does not match this database"
        )


def _assert_legacy_rebaseline_handoff(bind: sa.Connection) -> None:
    """Bind the privileged 0101 legacy path to its completed 0061→0100 receipt."""

    if not _legacy_rebaseline_profile():
        return
    receipt = _read_legacy_rebaseline_receipt()
    preflight = receipt["preflight"]
    assert isinstance(preflight, dict)
    expected_identity = {
        key: preflight[key]
        for key in (
            "database_name",
            "database_oid",
            "system_identifier",
            "server_addr",
            "server_port",
        )
    }
    # 0100 helper와 같은 순서(advisory → pg_database fence)로 잡는다. advisory를
    # 먼저 잡아 catalog lock 대기와 반대 순서의 deadlock을 막고, 이후 identity
    # proof가 pg_database를 읽기 전부터 timeout을 적용한다.
    bind.execute(sa.text(_LEGACY_REBASELINE_SERIALIZATION_LOCK_SQL))
    bind.execute(sa.text(_LEGACY_REBASELINE_DATABASE_FENCE_LOCK_TIMEOUT_SQL))
    try:
        identity_payload = bind.scalar(
            sa.text(
                """
                SELECT json_build_object(
                    'database_name', current_database(),
                    'database_oid', (
                        SELECT database_row.oid
                        FROM pg_database database_row
                        WHERE database_row.datname = current_database()
                    )::bigint,
                    'system_identifier', (pg_control_system()).system_identifier::text,
                    'server_addr', COALESCE(host(inet_server_addr()), ''),
                    'server_port', COALESCE(inet_server_port(), 0)::integer
                )::text
                """
            )
        )
    except sa.exc.DBAPIError as exc:
        raise RuntimeError(
            "0101 legacy rebaseline could not read database proof within 5s"
        ) from exc
    try:
        identity = json.loads(identity_payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("0101 legacy rebaseline database proof is invalid") from exc
    if identity != expected_identity:
        raise RuntimeError("0101 legacy rebaseline receipt does not match this database")
    _acquire_legacy_rebaseline_database_connection_fence(bind)
    _assert_legacy_rebaseline_fingerprint(bind, preflight)
    version_rows_payload = bind.scalar(
        sa.text(
            """
            SELECT COALESCE(
                json_agg(version_num ORDER BY version_num)::text,
                '[]'
            )
            FROM app.alembic_version
            """
        )
    )
    try:
        version_rows = json.loads(version_rows_payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("0101 legacy rebaseline database proof is invalid") from exc
    if version_rows != ["20260824_0100"]:
        raise RuntimeError("0101 legacy rebaseline requires the 0100 handoff row")


def _activate_m05_migration_owner(bind: sa.Connection) -> str | None:
    """Switch only the M05 portion to its non-login receipt owner.

    The pre-existing app tables are still changed by their owner.  The root-only 0100
    handoff deliberately does not rewrite old object ownership; the verified legacy
    0101 tail converges only the approved `app` catalog after its M05 DDL is complete.
    Fresh installs instead arrive here through the non-inheriting one-shot migrator
    login whose database default role is the app owner.
    """

    migration_owner = _configured_migration_owner()
    migrator_login = _configured_migrator_login()
    legacy_rebaseline = _legacy_rebaseline_profile()
    if migration_owner is None or migrator_login is None:
        if (
            legacy_rebaseline
            or _managed_deployment_requires_migration_owner()
            or migration_owner is not None
            or migrator_login is not None
        ):
            raise RuntimeError("0101 managed migration requires migration and migrator roles")
        return None
    legacy_app_schema_owner = (
        _require_legacy_canonical_app_owner(bind) if legacy_rebaseline else None
    )

    role_contract_valid = bind.scalar(
        sa.text(
            """
            WITH migration_role AS (
                SELECT role_row.oid, role_row.rolcanlogin, role_row.rolsuper,
                       role_row.rolcreaterole, role_row.rolcreatedb,
                       role_row.rolreplication, role_row.rolbypassrls,
                       role_row.rolinherit
                FROM pg_roles role_row
                WHERE role_row.rolname = :migration_owner
            ),
            migrator_role AS (
                SELECT role_row.oid, role_row.rolcanlogin, role_row.rolsuper,
                       role_row.rolcreaterole, role_row.rolcreatedb,
                       role_row.rolreplication, role_row.rolbypassrls,
                       role_row.rolinherit
                FROM pg_roles role_row
                WHERE role_row.rolname = :migrator_login
            ),
            app_owner AS (
                SELECT namespace.nspowner AS oid
                FROM pg_namespace namespace
                WHERE namespace.nspname = 'app'
            ),
            legacy_app_owner AS (
                SELECT role_row.oid
                FROM pg_roles role_row
                WHERE role_row.rolname = :legacy_app_schema_owner
            ),
            database_owner AS (
                SELECT database_row.datdba AS oid
                FROM pg_database database_row
                WHERE database_row.datname = current_database()
            ),
            session_role AS (
                SELECT role_row.oid, role_row.rolcanlogin, role_row.rolsuper,
                       role_row.rolcreaterole, role_row.rolcreatedb,
                       role_row.rolreplication, role_row.rolbypassrls,
                       role_row.rolinherit
                FROM pg_roles role_row
                WHERE role_row.rolname = session_user
            )
            SELECT
                (SELECT count(*) FROM migration_role) = 1
                AND (SELECT count(*) FROM migrator_role) = 1
                AND (SELECT count(*) FROM app_owner) = 1
                AND (SELECT count(*) FROM database_owner) = 1
                AND (SELECT count(*) FROM session_role) = 1
                AND (
                    NOT :legacy_rebaseline
                    OR (SELECT count(*) FROM legacy_app_owner) = 1
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_auth_members membership
                    WHERE membership.member = (SELECT oid FROM app_owner)
                )
                AND EXISTS (
                    SELECT 1
                    FROM migration_role migration
                    WHERE NOT migration.rolcanlogin
                      AND NOT migration.rolsuper
                      AND NOT migration.rolcreaterole
                      AND NOT migration.rolcreatedb
                      AND NOT migration.rolreplication
                      AND NOT migration.rolbypassrls
                      AND NOT migration.rolinherit
                      AND migration.oid <> (SELECT oid FROM app_owner)
                      AND migration.oid <> (SELECT oid FROM database_owner)
                )
                AND EXISTS (
                    SELECT 1
                    FROM migrator_role migrator
                    WHERE NOT migrator.rolsuper
                      AND NOT migrator.rolcreaterole
                      AND NOT migrator.rolcreatedb
                      AND NOT migrator.rolreplication
                      AND NOT migrator.rolbypassrls
                      AND NOT migrator.rolinherit
                      AND migrator.oid <> (SELECT oid FROM migration_role)
                      AND migrator.oid <> (SELECT oid FROM app_owner)
                      AND migrator.oid <> (SELECT oid FROM database_owner)
                      AND CASE WHEN :legacy_rebaseline THEN NOT migrator.rolcanlogin
                               ELSE migrator.rolcanlogin
                          END
                      AND NOT EXISTS (
                          SELECT 1
                          FROM pg_auth_members membership
                          WHERE membership.roleid = migrator.oid
                      )
                )
                AND has_schema_privilege(
                    (SELECT oid FROM migration_role), 'x_extension', 'USAGE'
                )
                AND NOT has_schema_privilege(
                    (SELECT oid FROM migration_role), 'x_extension', 'CREATE'
                )
                AND has_function_privilege(
                    (SELECT oid FROM migration_role),
                    'x_extension.digest(bytea,text)'::regprocedure,
                    'EXECUTE'
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_default_acl default_acl
                    WHERE default_acl.defaclrole = (SELECT oid FROM migration_role)
                      AND default_acl.defaclnamespace = 0
                )
                AND (
                    SELECT count(*)
                    FROM pg_auth_members membership
                    WHERE membership.member = (SELECT oid FROM migration_role)
                      AND membership.roleid = CASE
                          WHEN :legacy_rebaseline THEN (SELECT oid FROM legacy_app_owner)
                          ELSE (SELECT oid FROM app_owner)
                      END
                      AND NOT membership.admin_option
                      AND NOT membership.inherit_option
                      AND membership.set_option
                ) = 1
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_auth_members membership
                    WHERE membership.member = (SELECT oid FROM migration_role)
                      AND (
                          membership.roleid <> CASE
                              WHEN :legacy_rebaseline THEN (SELECT oid FROM legacy_app_owner)
                              ELSE (SELECT oid FROM app_owner)
                          END
                          OR membership.admin_option
                          OR membership.inherit_option
                          OR NOT membership.set_option
                      )
                )
                AND (
                    SELECT count(*)
                    FROM pg_auth_members membership
                    WHERE membership.member = (SELECT oid FROM migrator_role)
                      AND membership.roleid IN (
                          (SELECT oid FROM migration_role),
                          CASE
                              WHEN :legacy_rebaseline THEN (SELECT oid FROM legacy_app_owner)
                              ELSE (SELECT oid FROM app_owner)
                          END
                      )
                      AND NOT membership.admin_option
                      AND NOT membership.inherit_option
                      AND membership.set_option
                ) = 2
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_auth_members membership
                    WHERE membership.member = (SELECT oid FROM migrator_role)
                      AND (
                          membership.roleid NOT IN (
                              (SELECT oid FROM migration_role),
                              CASE
                                  WHEN :legacy_rebaseline THEN (SELECT oid FROM legacy_app_owner)
                                  ELSE (SELECT oid FROM app_owner)
                              END
                          )
                          OR membership.admin_option
                          OR membership.inherit_option
                          OR NOT membership.set_option
                      )
                )
                AND (
                    CASE WHEN :legacy_rebaseline THEN
                        session_user = current_user
                        AND current_user::regrole = (SELECT oid FROM app_owner)
                        AND current_user::regrole = (SELECT oid FROM database_owner)
                        AND (SELECT count(*) FROM app.alembic_version) = 1
                        AND (SELECT version_num FROM app.alembic_version) = '20260824_0100'
                        AND pg_has_role(
                            session_user::regrole,
                            (SELECT oid FROM migration_role),
                            'SET'
                        )
                        AND NOT EXISTS (
                            SELECT 1
                            FROM pg_auth_members membership
                            WHERE membership.roleid = (SELECT oid FROM app_owner)
                        )
                        AND (
                            SELECT count(*)
                            FROM pg_auth_members membership
                            WHERE membership.member = (SELECT oid FROM migrator_role)
                              AND membership.roleid = (SELECT oid FROM migration_role)
                              AND NOT membership.admin_option
                              AND NOT membership.inherit_option
                              AND membership.set_option
                        ) = 1
                        AND NOT EXISTS (
                            SELECT 1
                            FROM pg_auth_members membership
                            WHERE membership.roleid = (SELECT oid FROM migration_role)
                              AND (
                                  membership.member <> (SELECT oid FROM migrator_role)
                                  OR membership.admin_option
                                  OR membership.inherit_option
                                  OR NOT membership.set_option
                              )
                        )
                    ELSE
                        session_user <> current_user
                        AND current_user::regrole = (SELECT oid FROM app_owner)
                        AND EXISTS (
                            SELECT 1
                            FROM session_role session_login
                            WHERE session_login.rolcanlogin
                              AND NOT session_login.rolsuper
                              AND NOT session_login.rolcreaterole
                              AND NOT session_login.rolcreatedb
                              AND NOT session_login.rolreplication
                              AND NOT session_login.rolbypassrls
                              AND NOT session_login.rolinherit
                              AND session_login.oid <> (SELECT oid FROM database_owner)
                              AND session_login.oid = (SELECT oid FROM migrator_role)
                        )
                        AND (
                            SELECT count(*)
                            FROM pg_auth_members membership
                            WHERE membership.roleid = (SELECT oid FROM app_owner)
                              AND membership.member IN (
                                  (SELECT oid FROM migration_role),
                                  (SELECT oid FROM migrator_role)
                              )
                              AND NOT membership.admin_option
                              AND NOT membership.inherit_option
                              AND membership.set_option
                        ) = 2
                        AND NOT EXISTS (
                            SELECT 1
                            FROM pg_auth_members membership
                            WHERE membership.roleid = (SELECT oid FROM app_owner)
                              AND (
                                  membership.member NOT IN (
                                      (SELECT oid FROM migration_role),
                                      (SELECT oid FROM migrator_role)
                                  )
                                  OR membership.admin_option
                                  OR membership.inherit_option
                                  OR NOT membership.set_option
                              )
                        )
                        AND (
                            SELECT count(*)
                            FROM pg_auth_members membership
                            WHERE membership.member = (SELECT oid FROM migrator_role)
                              AND membership.roleid = (SELECT oid FROM migration_role)
                              AND NOT membership.admin_option
                              AND NOT membership.inherit_option
                              AND membership.set_option
                        ) = 1
                        AND NOT EXISTS (
                            SELECT 1
                            FROM pg_auth_members membership
                            WHERE membership.roleid = (SELECT oid FROM migration_role)
                              AND (
                                  membership.member <> (SELECT oid FROM migrator_role)
                                  OR membership.admin_option
                                  OR membership.inherit_option
                                  OR NOT membership.set_option
                              )
                        )
                        AND NOT pg_has_role(
                            (SELECT oid FROM session_role),
                            (SELECT oid FROM database_owner),
                            'MEMBER'
                        )
                    END
                )
            """
        ),
        {
            "migration_owner": migration_owner,
            "migrator_login": migrator_login,
            "legacy_app_schema_owner": legacy_app_schema_owner,
            "legacy_rebaseline": legacy_rebaseline,
        },
    )
    if role_contract_valid is not True:
        raise RuntimeError("0101 migration owner role contract is not satisfied")

    # The identifier has already been constrained to a portable PostgreSQL role name.
    op.execute(f'SET LOCAL ROLE "{migration_owner}"')
    if (
        bind.scalar(
            sa.text("SELECT current_user = :migration_owner"), {"migration_owner": migration_owner}
        )
        is not True
    ):
        raise RuntimeError("0101 could not activate the migration owner")
    return bind.scalar(
        sa.text(
            """
            SELECT namespace.nspowner::regrole::text
            FROM pg_namespace namespace
            WHERE namespace.nspname = 'app'
            """
        )
    )


def _restore_app_owner(app_owner: str | None) -> None:
    """Let Alembic write its version row with the effective app schema owner again."""

    if app_owner is None:
        return
    if _ROLE_IDENTIFIER.fullmatch(app_owner) is None:
        raise RuntimeError("0101 app schema owner is invalid")
    op.execute(sa.text(f'SET LOCAL ROLE "{app_owner}"'))
    if (
        op.get_bind().scalar(sa.text("SELECT current_user = :app_owner"), {"app_owner": app_owner})
        is not True
    ):
        raise RuntimeError("0101 could not restore the app schema owner")


def _require_legacy_canonical_app_owner(bind: sa.Connection) -> str:
    """Require the configured post-legacy app owner before changing any owner metadata."""

    app_schema_owner = _configured_app_schema_owner()
    migration_owner = _configured_migration_owner()
    migrator_login = _configured_migrator_login()
    if app_schema_owner is None:
        raise RuntimeError("0101 legacy rebaseline requires PINVI_APP_SCHEMA_OWNER")
    if migration_owner is None or migrator_login is None:
        raise RuntimeError("0101 legacy rebaseline requires migration and migrator roles")
    canonical_owner_is_safe = bind.scalar(
        sa.text(
            """
            WITH canonical_owner AS (
                SELECT role_row.oid, role_row.rolcanlogin, role_row.rolsuper,
                       role_row.rolcreaterole, role_row.rolcreatedb,
                       role_row.rolreplication, role_row.rolbypassrls,
                       role_row.rolinherit
                FROM pg_roles role_row
                WHERE role_row.rolname = :app_schema_owner
            ),
            migration_role AS (
                SELECT role_row.oid
                FROM pg_roles role_row
                WHERE role_row.rolname = :migration_owner
            ),
            migrator_role AS (
                SELECT role_row.oid
                FROM pg_roles role_row
                WHERE role_row.rolname = :migrator_login
            ),
            database_owner AS (
                SELECT database_row.datdba AS oid
                FROM pg_database database_row
                WHERE database_row.datname = current_database()
            )
            SELECT
                (SELECT count(*) FROM canonical_owner) = 1
                AND (SELECT count(*) FROM migration_role) = 1
                AND (SELECT count(*) FROM migrator_role) = 1
                AND (SELECT count(*) FROM database_owner) = 1
                AND EXISTS (
                    SELECT 1
                    FROM canonical_owner owner
                    WHERE NOT owner.rolcanlogin
                      AND NOT owner.rolsuper
                      AND NOT owner.rolcreaterole
                      AND NOT owner.rolcreatedb
                      AND NOT owner.rolreplication
                      AND NOT owner.rolbypassrls
                      AND NOT owner.rolinherit
                      AND owner.oid <> (SELECT oid FROM database_owner)
                      AND owner.oid <> (SELECT oid FROM migration_role)
                      AND owner.oid <> (SELECT oid FROM migrator_role)
                      AND NOT EXISTS (
                          SELECT 1
                          FROM pg_auth_members membership
                          WHERE membership.member = owner.oid
                      )
                )
                AND session_user = current_user
                AND current_user::regrole = (SELECT oid FROM database_owner)
                AND pg_has_role(
                    session_user::regrole,
                    (SELECT oid FROM canonical_owner),
                    'SET'
                )
                AND (
                    SELECT count(*)
                    FROM pg_auth_members membership
                    WHERE membership.roleid = (SELECT oid FROM canonical_owner)
                      AND membership.member IN (
                          (SELECT oid FROM migration_role),
                          (SELECT oid FROM migrator_role)
                      )
                      AND NOT membership.admin_option
                      AND NOT membership.inherit_option
                      AND membership.set_option
                ) = 2
                AND NOT EXISTS (
                    SELECT 1
                    FROM pg_auth_members membership
                    WHERE membership.roleid = (SELECT oid FROM canonical_owner)
                      AND (
                          membership.member NOT IN (
                              (SELECT oid FROM migration_role),
                              (SELECT oid FROM migrator_role)
                          )
                          OR membership.admin_option
                          OR membership.inherit_option
                          OR NOT membership.set_option
                      )
                )
            """
        ),
        {
            "app_schema_owner": app_schema_owner,
            "migration_owner": migration_owner,
            "migrator_login": migrator_login,
        },
    )
    if canonical_owner_is_safe is not True:
        raise RuntimeError("0101 legacy rebaseline canonical app owner is not safe")
    return app_schema_owner


def _legacy_app_ownership_is_canonical(bind: sa.Connection, app_schema_owner: str) -> bool:
    return (
        bind.scalar(
            sa.text(
                """
                WITH app_schema AS (
                    SELECT namespace.oid, namespace.nspowner
                    FROM pg_namespace namespace
                    WHERE namespace.nspname = 'app'
                ),
                app_objects AS (
                    SELECT relation.relowner AS owner_oid
                    FROM pg_class relation
                    JOIN app_schema schema ON schema.oid = relation.relnamespace
                    UNION ALL
                    SELECT procedure.proowner
                    FROM pg_proc procedure
                    JOIN app_schema schema ON schema.oid = procedure.pronamespace
                    UNION ALL
                    SELECT type_row.typowner
                    FROM pg_type type_row
                    JOIN app_schema schema ON schema.oid = type_row.typnamespace
                    UNION ALL
                    SELECT operator_row.oprowner
                    FROM pg_operator operator_row
                    JOIN app_schema schema ON schema.oid = operator_row.oprnamespace
                    UNION ALL
                    SELECT collation_row.collowner
                    FROM pg_collation collation_row
                    JOIN app_schema schema ON schema.oid = collation_row.collnamespace
                    UNION ALL
                    SELECT conversion_row.conowner
                    FROM pg_conversion conversion_row
                    JOIN app_schema schema ON schema.oid = conversion_row.connamespace
                    UNION ALL
                    SELECT opclass_row.opcowner
                    FROM pg_opclass opclass_row
                    JOIN app_schema schema ON schema.oid = opclass_row.opcnamespace
                    UNION ALL
                    SELECT opfamily_row.opfowner
                    FROM pg_opfamily opfamily_row
                    JOIN app_schema schema ON schema.oid = opfamily_row.opfnamespace
                    UNION ALL
                    SELECT config_row.cfgowner
                    FROM pg_ts_config config_row
                    JOIN app_schema schema ON schema.oid = config_row.cfgnamespace
                    UNION ALL
                    SELECT dictionary_row.dictowner
                    FROM pg_ts_dict dictionary_row
                    JOIN app_schema schema ON schema.oid = dictionary_row.dictnamespace
                    UNION ALL
                    SELECT statistic_row.stxowner
                    FROM pg_statistic_ext statistic_row
                    JOIN app_schema schema ON schema.oid = statistic_row.stxnamespace
                    UNION ALL
                    SELECT extension_row.extowner
                    FROM pg_extension extension_row
                    JOIN app_schema schema ON schema.oid = extension_row.extnamespace
                )
                SELECT
                    (SELECT count(*) FROM app_schema) = 1
                    AND (SELECT nspowner FROM app_schema) = CAST(:app_schema_owner AS regrole)
                    AND NOT EXISTS (
                        SELECT 1 FROM app_objects
                        WHERE owner_oid <> CAST(:app_schema_owner AS regrole)
                    )
                """
            ),
            {"app_schema_owner": app_schema_owner},
        )
        is True
    )


def _assert_legacy_supported_catalog_owners_are_canonical(
    bind: sa.Connection, app_schema_owner: str
) -> None:
    """ALTER OWNER를 지원하지 않는 app catalog owner drift는 transaction 전체를 중단한다."""

    unsupported_owner_drift = bind.scalar(
        sa.text(
            """
            WITH app_schema AS (
                SELECT namespace.oid
                FROM pg_namespace namespace
                WHERE namespace.nspname = 'app'
            ),
            unsupported_objects(owner_oid) AS (
                SELECT collation_row.collowner
                FROM pg_collation collation_row
                JOIN app_schema schema ON schema.oid = collation_row.collnamespace
                UNION ALL
                SELECT conversion_row.conowner
                FROM pg_conversion conversion_row
                JOIN app_schema schema ON schema.oid = conversion_row.connamespace
                UNION ALL
                SELECT opclass_row.opcowner
                FROM pg_opclass opclass_row
                JOIN app_schema schema ON schema.oid = opclass_row.opcnamespace
                UNION ALL
                SELECT opfamily_row.opfowner
                FROM pg_opfamily opfamily_row
                JOIN app_schema schema ON schema.oid = opfamily_row.opfnamespace
                UNION ALL
                SELECT config_row.cfgowner
                FROM pg_ts_config config_row
                JOIN app_schema schema ON schema.oid = config_row.cfgnamespace
                UNION ALL
                SELECT dictionary_row.dictowner
                FROM pg_ts_dict dictionary_row
                JOIN app_schema schema ON schema.oid = dictionary_row.dictnamespace
                UNION ALL
                SELECT statistic_row.stxowner
                FROM pg_statistic_ext statistic_row
                JOIN app_schema schema ON schema.oid = statistic_row.stxnamespace
                UNION ALL
                SELECT extension_row.extowner
                FROM pg_extension extension_row
                JOIN app_schema schema ON schema.oid = extension_row.extnamespace
            )
            SELECT EXISTS (
                SELECT 1
                FROM unsupported_objects object_row
                JOIN pg_roles owner ON owner.rolname = :app_schema_owner
                WHERE object_row.owner_oid <> owner.oid
            )
            """
        ),
        {"app_schema_owner": app_schema_owner},
    )
    if unsupported_owner_drift is True:
        raise RuntimeError("0101 legacy rebaseline has noncanonical unsupported app catalog owners")


def _converge_legacy_app_ownership(bind: sa.Connection, app_owner: str | None) -> str | None:
    """Move only the approved legacy `app` catalog onto the canonical schema owner."""

    if not _legacy_rebaseline_profile():
        return app_owner
    if app_owner is None:
        raise RuntimeError("0101 legacy rebaseline app schema owner is unavailable")
    app_schema_owner = _require_legacy_canonical_app_owner(bind)
    current_owner = bind.scalar(
        sa.text(
            """
            SELECT namespace.nspowner::regrole::text
            FROM pg_namespace namespace
            WHERE namespace.nspname = 'app'
            """
        )
    )
    if current_owner != app_owner:
        raise RuntimeError("0101 legacy rebaseline app schema owner changed before convergence")

    _assert_legacy_supported_catalog_owners_are_canonical(bind, app_schema_owner)
    quoted_owner = _quote_identifier(app_schema_owner)
    bind.execute(sa.text(f"ALTER SCHEMA app OWNER TO {quoted_owner}"))

    relation_rows = tuple(
        (str(row[0]), str(row[1]))
        for row in bind.execute(
            sa.text(
                """
                SELECT relation.relname, relation.relkind::text
                FROM pg_class relation
                JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
                JOIN pg_roles owner ON owner.rolname = :app_schema_owner
                WHERE namespace.nspname = 'app'
                  AND relation.relowner <> owner.oid
                  AND relation.relkind IN ('r', 'p', 'v', 'm', 'S', 'f', 'c')
                ORDER BY relation.relkind, relation.relname COLLATE "C"
                """
            ),
            {"app_schema_owner": app_schema_owner},
        )
    )
    relation_commands = {
        "r": "ALTER TABLE",
        "p": "ALTER TABLE",
        "v": "ALTER VIEW",
        "m": "ALTER MATERIALIZED VIEW",
        "S": "ALTER SEQUENCE",
        "f": "ALTER FOREIGN TABLE",
        "c": "ALTER TYPE",
    }
    for relation_name, relation_kind in relation_rows:
        bind.execute(
            sa.text(
                f"{relation_commands[relation_kind]} app.{_quote_identifier(relation_name)} "
                f"OWNER TO {quoted_owner}"
            )
        )

    type_names = tuple(
        str(row[0])
        for row in bind.execute(
            sa.text(
                """
                SELECT type_row.typname
                FROM pg_type type_row
                JOIN pg_namespace namespace ON namespace.oid = type_row.typnamespace
                JOIN pg_roles owner ON owner.rolname = :app_schema_owner
                WHERE namespace.nspname = 'app'
                  AND type_row.typowner <> owner.oid
                  AND type_row.typrelid = 0
                  AND type_row.typelem = 0
                  AND type_row.typtype <> 'p'
                ORDER BY type_row.typname COLLATE "C"
                """
            ),
            {"app_schema_owner": app_schema_owner},
        )
    )
    for type_name in type_names:
        bind.execute(
            sa.text(f"ALTER TYPE app.{_quote_identifier(type_name)} OWNER TO {quoted_owner}")
        )

    routines = tuple(
        (str(row[0]), str(row[1]))
        for row in bind.execute(
            sa.text(
                """
                SELECT procedure.proname, pg_get_function_identity_arguments(procedure.oid)
                FROM pg_proc procedure
                JOIN pg_namespace namespace ON namespace.oid = procedure.pronamespace
                JOIN pg_roles owner ON owner.rolname = :app_schema_owner
                WHERE namespace.nspname = 'app'
                  AND procedure.proowner <> owner.oid
                ORDER BY procedure.proname COLLATE "C", procedure.oid
                """
            ),
            {"app_schema_owner": app_schema_owner},
        )
    )
    for routine_name, identity_arguments in routines:
        bind.execute(
            sa.text(
                f"ALTER ROUTINE app.{_quote_identifier(routine_name)}({identity_arguments}) "
                f"OWNER TO {quoted_owner}"
            )
        )

    operators = tuple(
        (str(row[0]), str(row[1]), str(row[2]))
        for row in bind.execute(
            sa.text(
                """
                SELECT
                    operator_row.oprname,
                    CASE WHEN operator_row.oprleft = 0 THEN 'NONE'
                         ELSE pg_catalog.format_type(operator_row.oprleft, NULL::integer) END,
                    CASE WHEN operator_row.oprright = 0 THEN 'NONE'
                         ELSE pg_catalog.format_type(operator_row.oprright, NULL::integer) END
                FROM pg_operator operator_row
                JOIN pg_namespace namespace ON namespace.oid = operator_row.oprnamespace
                JOIN pg_roles owner ON owner.rolname = :app_schema_owner
                WHERE namespace.nspname = 'app'
                  AND operator_row.oprowner <> owner.oid
                ORDER BY operator_row.oprname COLLATE "C", operator_row.oid
                """
            ),
            {"app_schema_owner": app_schema_owner},
        )
    )
    for operator_name, left_type, right_type in operators:
        if _OPERATOR_NAME.fullmatch(operator_name) is None:
            raise RuntimeError("0101 legacy rebaseline encountered an invalid app operator name")
        bind.execute(
            sa.text(
                f"ALTER OPERATOR app.{operator_name} "
                f"({left_type}, {right_type}) OWNER TO {quoted_owner}"
            )
        )

    if not _legacy_app_ownership_is_canonical(bind, app_schema_owner):
        raise RuntimeError("0101 legacy rebaseline app ownership did not converge")
    return app_schema_owner


def _grant_legacy_runtime_app_privileges(bind: sa.Connection, app_schema_owner: str | None) -> None:
    """Receipt fingerprint를 재검증한 뒤에만 legacy app runtime ACL을 복원한다."""

    if not _legacy_rebaseline_profile():
        return
    if app_schema_owner is None:
        raise RuntimeError("0101 legacy rebaseline app schema owner is unavailable")
    app_role = _configured_app_runtime_role()
    if app_role is None:
        raise RuntimeError("0101 legacy rebaseline requires PINVI_APP_DB_USER")
    if (
        bind.scalar(
            sa.text("SELECT current_user = :app_schema_owner"),
            {"app_schema_owner": app_schema_owner},
        )
        is not True
    ):
        raise RuntimeError("0101 legacy rebaseline could not restore app owner for runtime grants")

    quoted_owner = _quote_identifier(app_schema_owner)
    quoted_app_role = _quote_identifier(app_role)
    bind.execute(sa.text("REVOKE ALL ON SCHEMA app FROM PUBLIC"))
    bind.execute(sa.text(f"GRANT USAGE ON SCHEMA app TO {quoted_app_role}"))
    bind.execute(
        sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO {quoted_app_role}"
        )
    )
    bind.execute(
        sa.text(f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA app TO {quoted_app_role}")
    )
    bind.execute(
        sa.text(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {quoted_owner} IN SCHEMA app "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {quoted_app_role}"
        )
    )
    bind.execute(
        sa.text(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {quoted_owner} IN SCHEMA app "
            f"GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {quoted_app_role}"
        )
    )


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


def _install_location_audit_purpose_contract() -> None:
    """현재 main의 `/search` 감사 purpose를 0061 기준선 위에 반영한다."""

    op.execute(
        f"ALTER TABLE app.location_access_log DROP CONSTRAINT "
        f"{_LOCATION_ACCESS_LOG_PURPOSE_CONSTRAINT}"
    )
    op.execute(
        f"ALTER TABLE app.location_access_log ADD CONSTRAINT "
        f"{_LOCATION_ACCESS_LOG_PURPOSE_CONSTRAINT} "
        f"CHECK (purpose IN ({_LOCATION_ACCESS_LOG_PURPOSES}))"
    )


def _install_location_audit_coord_source_contract() -> None:
    """좌표 출처를 기록해 device 동의 게이트와 audit ledger를 같은 계약으로 묶는다."""

    for table in ("location_access_log", "location_audit_outbox"):
        op.add_column(
            table,
            sa.Column("coord_source", sa.Text(), nullable=True),
            schema="app",
        )
        op.create_check_constraint(
            f"ck_{table}_coord_source",
            table,
            _LOCATION_AUDIT_COORD_SOURCE_CHECK,
            schema="app",
        )


def _install_user_consent_event_history() -> None:
    """T-326의 현재 상태 이력 테이블과 정직한 0061 data backfill을 적용한다."""

    # 구 runtime은 user_consents만 in-place로 갱신한다. source table의 DML을 이
    # migration transaction 끝까지 막아야 backfill snapshot 뒤에 commit된 동의/철회가
    # event ledger에서 누락되지 않는다. deploy runner도 API/Dagster writer를 먼저 stop한다.
    op.execute("LOCK TABLE app.user_consents IN SHARE ROW EXCLUSIVE MODE")
    op.create_table(
        "user_consent_events",
        sa.Column(
            "event_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consent_type", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("event", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_user_consent_events")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.user_id"],
            name=op.f("fk_user_consent_events_user_id"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "consent_type IN ('tos', 'privacy', 'lbs_tos', 'location_collection', "
            "'demographic_use', 'marketing')",
            name=op.f("ck_user_consent_events_consent_type"),
        ),
        sa.CheckConstraint(
            "event IN ('agreed', 'withdrawn')",
            name=op.f("ck_user_consent_events_event"),
        ),
        sa.CheckConstraint(
            "source IN ('register', 'profile_complete', 'settings', 'backfill')",
            name=op.f("ck_user_consent_events_source"),
        ),
        schema="app",
    )
    op.create_index(
        "ix_user_consent_events_user_type_time",
        "user_consent_events",
        ["user_id", "consent_type", "occurred_at"],
        schema="app",
    )
    # `0101`은 M05 object용 별도 migration owner로도 실행한다. app schema의 새 table은
    # 그 owner가 아니라 app schema owner가 소유해야 runtime privilege 경계가 기존 table과 같다.
    op.execute(
        sa.text(
            """
            DO $app_owner$
            DECLARE
                app_owner name;
            BEGIN
                SELECT namespace.nspowner::regrole::text::name
                  INTO app_owner
                  FROM pg_namespace namespace
                 WHERE namespace.nspname = 'app';
                IF app_owner IS NULL THEN
                    RAISE EXCEPTION 'app schema owner is unavailable';
                END IF;
                EXECUTE format('ALTER TABLE app.user_consent_events OWNER TO %I', app_owner);
            END
            $app_owner$
            """
        )
    )
    # 현재 상태만 남은 0061 행에서 정확히 복원할 수 있는 agreement/withdrawal만 기록한다.
    # 재동의로 사라진 과거 cycle은 추정해 만들지 않는다.
    op.execute(
        sa.text(
            """
            INSERT INTO app.user_consent_events
                (user_id, consent_type, version, event, source, occurred_at)
            SELECT user_id, consent_type, version, event, 'backfill', occurred_at
            FROM (
                SELECT c.user_id, c.consent_type, c.version, 'agreed' AS event, c.agreed_at AS occurred_at
                FROM app.user_consents c
                UNION ALL
                SELECT c.user_id, c.consent_type, c.version, 'withdrawn', c.withdrawn_at
                FROM app.user_consents c
                WHERE c.withdrawn_at IS NOT NULL
            ) AS restored
            WHERE NOT EXISTS (
                SELECT 1 FROM app.user_consent_events e
                WHERE e.user_id = restored.user_id
                  AND e.consent_type = restored.consent_type
                  AND e.event = restored.event
                  AND e.source = 'backfill'
            )
            """
        )
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
        op.execute(sa.text(f"ALTER TABLE app.admin_audit_log ENABLE ALWAYS TRIGGER {trigger_name}"))


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
    bind = op.get_bind()
    _assert_legacy_rebaseline_handoff(bind)
    _install_location_audit_purpose_contract()
    _install_location_audit_coord_source_contract()
    _install_user_consent_event_history()
    _advance_boundary_contract()
    _replace_admin_audit_guard()
    app_owner = _activate_m05_migration_owner(bind)
    # named ops default ACL까지 검사하려면 schema를 먼저 확보해야 한다. 이 revision은
    # partial legacy M05 object를 덮어쓰지 않고 transaction 전체를 fail-close한다.
    op.execute("CREATE SCHEMA IF NOT EXISTS ops")
    _reject_unsafe_m05_default_privileges(bind)
    _reject_existing_m05_objects(bind)
    op.execute("SET LOCAL check_function_bodies = false")
    for statement in _m05_schema_statements():
        op.execute(sa.text(statement))
    _harden_m05_acl(bind)
    _assert_m05_acl(bind)
    _restore_app_owner(app_owner)
    canonical_app_owner = _converge_legacy_app_ownership(bind, app_owner)
    if canonical_app_owner != app_owner:
        _restore_app_owner(canonical_app_owner)
    _grant_legacy_runtime_app_privileges(bind, canonical_app_owner)


def downgrade() -> None:
    raise RuntimeError("0101 M05 activation contract migration is forward-only")
