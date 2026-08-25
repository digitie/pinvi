#!/usr/bin/env python3
"""ADR-063의 단발 0061 → 0100 Alembic metadata rebaseline 도구.

이 도구는 기존 migration을 실행하거나 app data/DDL을 바꾸지 않는다. `check`는
읽기 전용 preflight이고, `apply`는 검증된 0061 catalog의 `app.alembic_version`
한 행만 0100으로 바꾼다. 운영 실행은 root OS 계정과 별도 maintainer DB URL을
요구한다.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import ipaddress
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

LEGACY_REVISION = "20260821_0061"
BASELINE_REVISION = "20260824_0100"
_EXPECTED_CATALOG_LINES = 1590
_EXPECTED_CATALOG_SHA256 = (
    "bcf526cfa62facfaf3fe4b64a62e90329552cd887865a8ed5a477fe1fcc09c73"
)
_N150_LEGACY_CATALOG_SHA256 = (
    # N150 운영 0061과 fresh 0061 migration probe가 공통으로 산출한 legacy 기준선.
    "91949a8f1b609ca99b4631ee2db75b03d8cfc933ae72c52edec8d99d3d91b501"
)
_ALLOWED_CATALOG_SHA256 = frozenset(
    {_EXPECTED_CATALOG_SHA256, _N150_LEGACY_CATALOG_SHA256}
)
_CHECKSUM = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_INTEGER = re.compile(r"^[0-9]+$")
_BACKUP_MANIFEST_FIELDS = frozenset(
    {
        "version",
        "dump_filename",
        "schema",
        "dump_sha256",
        "pg_restore_list_sha256",
        "source_database",
        "source_database_oid",
        "source_system_identifier",
        "source_hostaddr",
        "source_port",
        "created_at",
    }
)
_TARGET_MANIFEST_FIELDS = frozenset(
    {
        "action",
        "backup_manifest_sha256",
        "captured_at",
        "preflight",
        "version",
    }
)
_PREFLIGHT_FIELDS = frozenset(
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
_RECEIPT_FIELDS = frozenset(
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
_MANIFEST_VERSION = 1

# pg_dump 기반 기준선은 source location을 다시 정규화한다. catalog fingerprint는
# 제약식·index expression/predicate·RLS/policy/rule/partition까지 포함해 0061의
# 의미가 같은지 확인한다. 표현식 일부를 sentinel만으로 확인하면 같은 이름·열 구성을
# 유지한 변조가 통과할 수 있으므로 허용하지 않는다.
_CATALOG_FINGERPRINT_SQL = """
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

# `apply`와 0101 receipt 검증은 같은 transaction-scoped advisory lock을 잡는다.
# 0101도 receipt 뒤 변조를 재검증하므로, 이 lock은 두 단계의 DDL-capable 실행을
# 직렬화하는 보조 장치일 뿐 재검증을 대체하지 않는다.
_REBASELINE_SERIALIZATION_LOCK_SQL = (
    "SELECT pg_advisory_xact_lock(1863432274, 20260824)"
)

# `apply`는 root-only superuser 연결로만 수행한다. transaction 전체에 shared
# `pg_database`의 AccessExclusive lock을 유지해 새 backend가 startup 중에 멈추도록
# 하고 기존 DDL-capable backend를 `pg_terminate_backend`로 종료한다. 단순 database
# owner는 임의 role의 backend를 종료할 권한이 없으므로, 그보다 약한 권한을 허용하면
# fence 중간에 permission error가 나고 부분 절차를 남긴다.
_REBASELINE_DATABASE_FENCE_AUTHORITY_SQL = """
SELECT current_role_row.rolsuper
FROM pg_roles AS current_role_row
WHERE current_role_row.rolname = current_user
  AND session_user = current_user
"""
_REBASELINE_DATABASE_FENCE_LOCK_TIMEOUT_SQL = "SET LOCAL lock_timeout = '5s'"
_REBASELINE_DATABASE_FENCE_LOCK_TIMEOUT_RESET_SQL = "SET LOCAL lock_timeout = 0"

# table lock만으로 enum/domain/operator처럼 relation 밖에 저장되는 app DDL을 멈출 수는
# 없다. owner role은 direct login뿐 아니라 INHERIT membership나 SET ROLE로도 쓸 수
# 있으므로, receipt를 작성하거나 소비할 때 그런 별도 client backend가 하나라도 있으면
# fail-close한다.
_REBASELINE_DDL_CAPABLE_SESSIONS_CTE = """
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
_REBASELINE_DDL_QUIESCENCE_SQL = (
    _REBASELINE_DDL_CAPABLE_SESSIONS_CTE
    + "SELECT NOT EXISTS (SELECT 1 FROM ddl_capable_sessions)"
)
_REBASELINE_DDL_CAPABLE_SESSION_IDS_SQL = (
    _REBASELINE_DDL_CAPABLE_SESSIONS_CTE
    + "SELECT pid FROM ddl_capable_sessions ORDER BY pid"
)

_LEGACY_SENTINELS_SQL = """
SELECT
  current_database() AS database_name,
  (SELECT database_row.oid FROM pg_database AS database_row
   WHERE database_row.datname = current_database())::bigint AS database_oid,
  (pg_control_system()).system_identifier::text AS system_identifier,
  COALESCE(host(inet_server_addr()), '') AS server_addr,
  COALESCE(inet_server_port(), 0)::integer AS server_port,
  session_user AS session_user,
  current_user AS current_user,
  current_setting('server_version_num')::integer AS server_version_num,
  EXISTS (
    SELECT 1
    FROM pg_constraint AS constraint_row
    JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname = 'app'
      AND relation.relname = 'ktm_cache_target_boundary_audits'
      AND pg_get_constraintdef(constraint_row.oid) LIKE
        '%pinvi-cache-target-final-boundary/v1%'
      AND pg_get_constraintdef(constraint_row.oid) LIKE
        '%schema_revision = ''20260821_0061''%'
  ) AS boundary_is_0061,
  NOT EXISTS (
    SELECT 1
    FROM pg_class AS relation
    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname = 'ops'
      AND relation.relname IN (
        'm05_activation_database_anchor',
        'm05_hotswap_release_receipts'
      )
    UNION ALL
    SELECT 1
    FROM pg_proc AS procedure
    JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace
    WHERE namespace.nspname = 'ops'
      AND procedure.proname IN (
        'guard_m05_activation_database_anchor_append_only',
        'guard_m05_hotswap_release_receipts_append_only',
        'm05_hotswap_release_topology_sha256',
        'record_m05_hotswap_release_receipt',
        'verify_m05_hotswap_release_receipt'
      )
  ) AS m05_objects_absent
"""


class RebaselineError(RuntimeError):
    """실행자가 조치할 수 있는 rebaseline preflight 실패."""


@dataclass(frozen=True)
class CatalogPreflight:
    database_name: str
    database_oid: int
    system_identifier: str
    server_addr: str
    server_port: int
    session_user: str
    current_user: str
    server_version_num: int
    version_rows: tuple[str, ...]
    catalog_lines: int
    catalog_sha256: str
    app_data_rows: int
    app_data_table_lines: int
    app_data_content_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "app_data_rows": self.app_data_rows,
            "app_data_table_lines": self.app_data_table_lines,
            "app_data_content_sha256": self.app_data_content_sha256,
            "database_name": self.database_name,
            "database_oid": self.database_oid,
            "system_identifier": self.system_identifier,
            "server_addr": self.server_addr,
            "server_port": self.server_port,
            "session_user": self.session_user,
            "current_user": self.current_user,
            "server_version_num": self.server_version_num,
            "version_rows": list(self.version_rows),
            "catalog_lines": self.catalog_lines,
            "catalog_sha256": self.catalog_sha256,
            "expected_catalog_lines": _EXPECTED_CATALOG_LINES,
            "expected_catalog_sha256": (
                self.catalog_sha256
                if self.catalog_sha256 in _ALLOWED_CATALOG_SHA256
                else _EXPECTED_CATALOG_SHA256
            ),
        }

    def stable_identity_dict(self) -> dict[str, Any]:
        """version row만 달라질 수 있는 0061→0100 전환 전후 identity."""

        value = self.as_dict()
        value.pop("version_rows")
        return value


@dataclass(frozen=True)
class BackupManifest:
    path: Path
    sha256: str
    created_at: str
    dump_sha256: str
    restore_list_sha256: str
    source_database: str
    source_database_oid: int
    source_system_identifier: str
    source_hostaddr: str
    source_port: int


@dataclass(frozen=True)
class BackupArtifact:
    sha256: str
    manifest: BackupManifest


@dataclass(frozen=True)
class TargetManifest:
    path: Path
    sha256: str
    captured_at: str
    backup_manifest_sha256: str
    preflight: dict[str, Any]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_root() -> None:
    if os.geteuid() != 0:
        raise RebaselineError("apply requires a root OS account")


def _validate_private_parent(path: Path, *, label: str) -> Path:
    parent = path.parent
    if parent.is_symlink():
        raise RebaselineError(f"{label} directory must not be a symlink")
    try:
        metadata = parent.stat()
    except OSError as exc:
        raise RebaselineError(f"{label} directory is unavailable") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise RebaselineError(f"{label} directory must be a directory")
    if metadata.st_uid != 0 or metadata.st_mode & 0o077:
        raise RebaselineError(f"{label} directory must be root-owned and private")
    return parent


def _validate_private_root_file(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise RebaselineError(f"{label} must not be a symlink")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise RebaselineError(f"{label} is unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise RebaselineError(f"{label} must be a regular file")
    if metadata.st_uid != 0:
        raise RebaselineError(f"{label} must be owned by root")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise RebaselineError(f"{label} must use mode 0600")
    _validate_private_parent(path, label=label)
    return path


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise RebaselineError(f"{label} must not contain duplicate JSON keys")
            value[key] = item
        return value

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RebaselineError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise RebaselineError(f"{label} must be a JSON object")
    return value


def _parse_utc_timestamp(value: object, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise RebaselineError(f"{label} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RebaselineError(f"{label} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise RebaselineError(f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def _read_checksum(checksum_file: Path) -> str:
    _validate_private_root_file(checksum_file, label="backup checksum file")
    try:
        first_line = checksum_file.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError, UnicodeDecodeError) as exc:
        raise RebaselineError("backup checksum file is unreadable") from exc
    digest = first_line.split(maxsplit=1)[0].lower()
    if _CHECKSUM.fullmatch(digest) is None:
        raise RebaselineError(
            "backup checksum file does not start with a SHA-256 digest"
        )
    return digest


def _read_backup_manifest(path: Path) -> BackupManifest:
    _validate_private_root_file(path, label="backup manifest")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise RebaselineError("backup manifest is unreadable") from exc

    fields: dict[str, str] = {}
    for line in lines:
        if not line or "=" not in line:
            raise RebaselineError("backup manifest has an invalid line")
        key, value = line.split("=", 1)
        if key in fields or key not in _BACKUP_MANIFEST_FIELDS or not value:
            raise RebaselineError("backup manifest has an invalid field")
        fields[key] = value
    if frozenset(fields) != _BACKUP_MANIFEST_FIELDS:
        raise RebaselineError("backup manifest is incomplete")
    if fields["version"] != "1" or fields["schema"] != "app":
        raise RebaselineError("backup manifest is not an app schema v1 manifest")
    dump_filename = fields["dump_filename"]
    if (
        Path(dump_filename).name != dump_filename
        or not dump_filename.endswith(".dump")
        or dump_filename == ".dump"
    ):
        raise RebaselineError("backup manifest dump filename is invalid")
    if any(
        _CHECKSUM.fullmatch(fields[field]) is None
        for field in ("dump_sha256", "pg_restore_list_sha256")
    ):
        raise RebaselineError("backup manifest hashes are invalid")
    if (
        _IDENTIFIER.fullmatch(fields["source_database"]) is None
        or _INTEGER.fullmatch(fields["source_database_oid"]) is None
        or _INTEGER.fullmatch(fields["source_system_identifier"]) is None
        or _INTEGER.fullmatch(fields["source_port"]) is None
    ):
        raise RebaselineError("backup manifest source identity is invalid")
    try:
        ipaddress.ip_address(fields["source_hostaddr"])
    except ValueError as exc:
        raise RebaselineError("backup manifest source endpoint is invalid") from exc
    _parse_utc_timestamp(fields["created_at"], label="backup manifest created_at")
    return BackupManifest(
        path=path,
        sha256=_sha256_file(path),
        created_at=fields["created_at"],
        dump_sha256=fields["dump_sha256"],
        restore_list_sha256=fields["pg_restore_list_sha256"],
        source_database=fields["source_database"],
        source_database_oid=int(fields["source_database_oid"]),
        source_system_identifier=fields["source_system_identifier"],
        source_hostaddr=fields["source_hostaddr"],
        source_port=int(fields["source_port"]),
    )


def _trusted_pg_restore() -> Path:
    candidates = [Path("/usr/bin/pg_restore"), Path("/bin/pg_restore")]
    postgres_root = Path("/usr/lib/postgresql")
    if postgres_root.is_dir():
        candidates.extend(sorted(postgres_root.glob("*/bin/pg_restore")))
    for candidate in candidates:
        if candidate.is_symlink():
            continue
        try:
            metadata = candidate.stat()
        except OSError:
            continue
        if (
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_uid == 0
            and not metadata.st_mode & 0o022
            and metadata.st_mode & 0o111
        ):
            return candidate
    raise RebaselineError("trusted pg_restore executable is unavailable")


def _restore_list_sha256(backup: Path) -> str:
    try:
        completed = subprocess.run(
            [str(_trusted_pg_restore()), "--list", str(backup)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise RebaselineError("pg_restore inventory verification failed") from exc
    if completed.returncode != 0:
        raise RebaselineError("backup is not a valid pg_restore custom archive")
    return hashlib.sha256(completed.stdout).hexdigest()


def _validate_backup(
    backup: Path, checksum_file: Path, manifest_file: Path
) -> BackupArtifact:
    _validate_private_root_file(backup, label="backup file")
    expected = _read_checksum(checksum_file)
    actual = _sha256_file(backup)
    if actual != expected:
        raise RebaselineError("backup SHA-256 does not match its checksum file")
    manifest = _read_backup_manifest(manifest_file)
    if manifest.path.name != f"{backup.name}.m05-manifest":
        raise RebaselineError("backup manifest path does not bind the backup filename")
    if actual != manifest.dump_sha256:
        raise RebaselineError("backup manifest dump SHA-256 does not match backup")
    if _restore_list_sha256(backup) != manifest.restore_list_sha256:
        raise RebaselineError("backup pg_restore inventory does not match manifest")
    return BackupArtifact(sha256=actual, manifest=manifest)


def _assert_backup_source_matches_preflight(
    backup: BackupManifest, preflight: CatalogPreflight
) -> None:
    if (
        backup.source_database != preflight.database_name
        or backup.source_database_oid != preflight.database_oid
        or backup.source_system_identifier != preflight.system_identifier
        or backup.source_hostaddr != preflight.server_addr
        or backup.source_port != preflight.server_port
    ):
        raise RebaselineError("backup source identity does not match rebaseline target")


def _write_json_descriptor(descriptor: int, payload: dict[str, Any]) -> None:
    with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(descriptor)


def _write_private_json_temp(path: Path, payload: dict[str, Any]) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        _write_json_descriptor(descriptor, payload)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    finally:
        os.close(descriptor)
    return temporary


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _create_private_json(path: Path, payload: dict[str, Any], *, label: str) -> None:
    parent = _validate_private_parent(path, label=label)
    if path.exists() or path.is_symlink():
        raise RebaselineError(f"{label} path must not already exist")
    temporary = _write_private_json_temp(path, payload)
    try:
        try:
            os.link(temporary, path)
        except OSError as exc:
            raise RebaselineError(f"{label} file cannot be reserved") from exc
        _fsync_directory(parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _replace_private_json(path: Path, payload: dict[str, Any], *, label: str) -> None:
    parent = _validate_private_parent(path, label=label)
    _validate_private_root_file(path, label=label)
    temporary = _write_private_json_temp(path, payload)
    try:
        os.replace(temporary, path)
        _fsync_directory(parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _target_manifest_payload(
    preflight: CatalogPreflight, backup_manifest_sha256: str
) -> dict[str, Any]:
    return {
        "action": "0061_to_0100_rebaseline_target",
        "backup_manifest_sha256": backup_manifest_sha256,
        "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "preflight": preflight.as_dict(),
        "version": _MANIFEST_VERSION,
    }


def _read_target_manifest(path: Path) -> TargetManifest:
    _validate_private_root_file(path, label="rebaseline target manifest")
    value = _read_json_object(path, label="rebaseline target manifest")
    if frozenset(value) != _TARGET_MANIFEST_FIELDS:
        raise RebaselineError("rebaseline target manifest fields are invalid")
    if (
        value["version"] != _MANIFEST_VERSION
        or value["action"] != "0061_to_0100_rebaseline_target"
        or not isinstance(value["preflight"], dict)
        or not isinstance(value["backup_manifest_sha256"], str)
        or _CHECKSUM.fullmatch(value["backup_manifest_sha256"]) is None
    ):
        raise RebaselineError("rebaseline target manifest values are invalid")
    _parse_utc_timestamp(value["captured_at"], label="target manifest captured_at")
    preflight = value["preflight"]
    if frozenset(preflight) != _PREFLIGHT_FIELDS:
        raise RebaselineError("rebaseline target manifest preflight fields are invalid")
    if (
        preflight["version_rows"] != [LEGACY_REVISION]
        or preflight["expected_catalog_lines"] != _EXPECTED_CATALOG_LINES
        or preflight["expected_catalog_sha256"] not in _ALLOWED_CATALOG_SHA256
        or preflight["catalog_lines"] != _EXPECTED_CATALOG_LINES
        or preflight["catalog_sha256"] != preflight["expected_catalog_sha256"]
        or not isinstance(preflight["database_name"], str)
        or _IDENTIFIER.fullmatch(preflight["database_name"]) is None
        or any(
            not isinstance(preflight[field], int) or isinstance(preflight[field], bool)
            for field in (
                "app_data_rows",
                "app_data_table_lines",
                "database_oid",
                "server_port",
                "server_version_num",
            )
        )
        or preflight["app_data_rows"] <= 0
        or preflight["app_data_table_lines"] <= 0
        or preflight["database_oid"] <= 0
        or not 1 <= preflight["server_port"] <= 65535
        or preflight["server_version_num"] // 10000 != 16
        or any(
            not isinstance(preflight[field], str) or not preflight[field]
            for field in (
                "current_user",
                "session_user",
                "system_identifier",
            )
        )
        or _INTEGER.fullmatch(preflight["system_identifier"]) is None
        or any(
            not isinstance(preflight[field], str)
            or _CHECKSUM.fullmatch(preflight[field]) is None
            for field in ("app_data_content_sha256",)
        )
    ):
        raise RebaselineError("rebaseline target manifest preflight values are invalid")
    try:
        ipaddress.ip_address(preflight["server_addr"])
    except (TypeError, ValueError) as exc:
        raise RebaselineError(
            "rebaseline target manifest preflight endpoint is invalid"
        ) from exc
    return TargetManifest(
        path=path,
        sha256=_sha256_file(path),
        captured_at=str(value["captured_at"]),
        backup_manifest_sha256=value["backup_manifest_sha256"],
        preflight=value["preflight"],
    )


def _assert_target_manifest(
    target: TargetManifest,
    preflight: CatalogPreflight,
    backup_manifest_sha256: str,
    backup_created_at: str,
    *,
    allow_baseline_revision: bool,
) -> None:
    if target.backup_manifest_sha256 != backup_manifest_sha256:
        raise RebaselineError("target manifest is not bound to this backup manifest")
    if _parse_utc_timestamp(
        backup_created_at, label="backup manifest created_at"
    ) > _parse_utc_timestamp(target.captured_at, label="target manifest captured_at"):
        raise RebaselineError("target manifest predates the backup manifest")
    expected = target.preflight
    actual = preflight.as_dict()
    if allow_baseline_revision:
        expected = dict(expected)
        expected.pop("version_rows", None)
        actual = preflight.stable_identity_dict()
    if expected != actual:
        raise RebaselineError("target database identity or data fingerprint changed")


def _receipt_payload(
    preflight: dict[str, Any],
    artifact: BackupArtifact,
    target: TargetManifest,
    *,
    state: str,
    completed_at: str | None,
) -> dict[str, Any]:
    return {
        "action": "0061_to_0100_rebaseline",
        "backup_manifest_sha256": artifact.manifest.sha256,
        "backup_sha256": artifact.sha256,
        "completed_at": completed_at,
        "preflight": preflight,
        "state": state,
        "target_manifest_sha256": target.sha256,
        "version": _MANIFEST_VERSION,
    }


def _read_receipt(path: Path) -> dict[str, Any]:
    _validate_private_root_file(path, label="rebaseline receipt")
    value = _read_json_object(path, label="rebaseline receipt")
    if frozenset(value) != _RECEIPT_FIELDS:
        raise RebaselineError("rebaseline receipt fields are invalid")
    if (
        value["version"] != _MANIFEST_VERSION
        or value["action"] != "0061_to_0100_rebaseline"
        or value["state"] not in {"prepared", "applied"}
        or not isinstance(value["preflight"], dict)
        or any(
            not isinstance(value[field], str)
            or _CHECKSUM.fullmatch(value[field]) is None
            for field in (
                "backup_manifest_sha256",
                "backup_sha256",
                "target_manifest_sha256",
            )
        )
    ):
        raise RebaselineError("rebaseline receipt values are invalid")
    if value["state"] == "prepared" and value["completed_at"] is not None:
        raise RebaselineError("prepared receipt must not have completed_at")
    if value["state"] == "applied":
        _parse_utc_timestamp(value["completed_at"], label="receipt completed_at")
    return value


def _assert_receipt_intent(receipt: dict[str, Any], expected: dict[str, Any]) -> None:
    for field in (
        "action",
        "backup_manifest_sha256",
        "backup_sha256",
        "preflight",
        "target_manifest_sha256",
        "version",
    ):
        if receipt[field] != expected[field]:
            raise RebaselineError("existing receipt is not this rebaseline intent")


def _prepare_receipt(path: Path, payload: dict[str, Any]) -> None:
    _create_private_json(path, payload, label="rebaseline receipt")


def _finalize_receipt(path: Path, payload: dict[str, Any]) -> None:
    _replace_private_json(path, payload, label="rebaseline receipt")


async def _catalog_fingerprint(connection: AsyncConnection) -> tuple[int, str]:
    rows = tuple((await connection.execute(text(_CATALOG_FINGERPRINT_SQL))).scalars())
    payload = ("\n".join(rows) + "\n").encode("utf-8")
    return len(rows), hashlib.sha256(payload).hexdigest()


async def _normalize_fingerprint_session(connection: AsyncConnection) -> None:
    """logical row serialization이 접속별 GUC에 흔들리지 않게 고정한다."""

    for statement in (
        "SET LOCAL TIME ZONE 'UTC'",
        "SET LOCAL DateStyle TO 'ISO, YMD'",
        "SET LOCAL IntervalStyle TO 'iso_8601'",
        "SET LOCAL bytea_output TO 'hex'",
        "SET LOCAL extra_float_digits TO 3",
    ):
        await connection.execute(text(statement))


async def _assert_rebaseline_ddl_quiescence(connection: AsyncConnection) -> None:
    """Fail-close unless no other client can mutate the protected app catalog."""

    await connection.execute(text("SELECT pg_stat_clear_snapshot()"))
    ddl_quiescent = await connection.scalar(text(_REBASELINE_DDL_QUIESCENCE_SQL))
    if ddl_quiescent is not True:
        raise RebaselineError("rebaseline requires app DDL quiescence")


async def _acquire_rebaseline_database_connection_fence(
    connection: AsyncConnection,
) -> None:
    """Block new backends, evict existing DDL-capable clients, then prove quiescence."""

    await connection.execute(text(_REBASELINE_DATABASE_FENCE_LOCK_TIMEOUT_SQL))
    try:
        has_authority = await connection.scalar(text(_REBASELINE_DATABASE_FENCE_AUTHORITY_SQL))
        if has_authority is not True:
            raise RebaselineError("rebaseline requires superuser connection fence authority")
        await connection.execute(text("LOCK TABLE pg_catalog.pg_database IN ACCESS EXCLUSIVE MODE"))
    except DBAPIError as exc:
        # 기존 backend가 pg_database AccessShare lock을 길게 보유하면 client를
        # 식별·종료하기도 전에 여기서 막힌다. 무기한 대기하지 않고 transaction을
        # rollback하게 하여 다음 승인된 재시도에 맡긴다.
        raise RebaselineError(
            "rebaseline could not acquire database connection fence within 5s"
        ) from exc
    await connection.execute(text(_REBASELINE_DATABASE_FENCE_LOCK_TIMEOUT_RESET_SQL))
    for _ in range(20):
        await connection.execute(text("SELECT pg_stat_clear_snapshot()"))
        pids = tuple(
            int(pid)
            for pid in (
                await connection.execute(text(_REBASELINE_DDL_CAPABLE_SESSION_IDS_SQL))
            ).scalars()
        )
        if not pids:
            await _assert_rebaseline_ddl_quiescence(connection)
            return
        for pid in pids:
            await connection.scalar(
                text("SELECT pg_terminate_backend(:pid, 5000)"), {"pid": pid}
            )
        await connection.execute(text("SELECT pg_sleep(0.05)"))
    raise RebaselineError("rebaseline could not prove app DDL quiescence")


async def _app_data_fingerprint(connection: AsyncConnection) -> tuple[int, int, str]:
    """0061 대상의 실제 app data 내용까지 PII를 남기지 않고 고정한다."""

    table_rows = await connection.execute(
        text(
            "SELECT relation.relname "
            "FROM pg_class AS relation "
            "JOIN pg_namespace AS namespace "
            "ON namespace.oid = relation.relnamespace "
            "WHERE namespace.nspname = 'app' "
            "AND relation.relkind IN ('r', 'p') "
            "AND relation.relname <> 'alembic_version' "
            'ORDER BY relation.relname COLLATE "C"'
        )
    )
    tables = tuple(table_rows.scalars())
    digest = hashlib.sha256()
    total_rows = 0
    for table_name in tables:
        quoted_table = str(table_name).replace('"', '""')
        digest.update(
            json.dumps(
                ["table", table_name], ensure_ascii=True, separators=(",", ":")
            ).encode("utf-8")
            + b"\n"
        )
        result = await connection.stream(
            text(
                f"SELECT to_jsonb(data_row)::text "
                f'FROM app."{quoted_table}" AS data_row '
                'ORDER BY to_jsonb(data_row)::text COLLATE "C"'
            )
        )
        async for row_json in result.scalars():
            total_rows += 1
            digest.update(
                json.dumps(
                    ["row", table_name, str(row_json)],
                    ensure_ascii=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
        await result.close()
    return total_rows, len(tables), digest.hexdigest()


async def _read_version_rows(
    connection: AsyncConnection, *, lock: bool
) -> tuple[str, ...]:
    suffix = " FOR UPDATE" if lock else ""
    rows = await connection.execute(
        text(
            f"SELECT version_num FROM app.alembic_version ORDER BY version_num{suffix}"
        )
    )
    return tuple(rows.scalars())


async def _preflight(
    connection: AsyncConnection,
    *,
    lock_version: bool,
    expected_revision: str = LEGACY_REVISION,
) -> CatalogPreflight:
    await _normalize_fingerprint_session(connection)
    version_rows = await _read_version_rows(connection, lock=lock_version)
    sentinel = (await connection.execute(text(_LEGACY_SENTINELS_SQL))).mappings().one()
    catalog_lines, catalog_sha256 = await _catalog_fingerprint(connection)
    (
        app_data_rows,
        app_data_table_lines,
        app_data_content_sha256,
    ) = await _app_data_fingerprint(connection)
    preflight = CatalogPreflight(
        database_name=str(sentinel["database_name"]),
        database_oid=int(sentinel["database_oid"]),
        system_identifier=str(sentinel["system_identifier"]),
        server_addr=str(sentinel["server_addr"]),
        server_port=int(sentinel["server_port"]),
        session_user=str(sentinel["session_user"]),
        current_user=str(sentinel["current_user"]),
        server_version_num=int(sentinel["server_version_num"]),
        version_rows=version_rows,
        catalog_lines=catalog_lines,
        catalog_sha256=catalog_sha256,
        app_data_rows=app_data_rows,
        app_data_table_lines=app_data_table_lines,
        app_data_content_sha256=app_data_content_sha256,
    )
    if preflight.server_version_num // 10000 != 16:
        raise RebaselineError("rebaseline requires PostgreSQL 16")
    if preflight.version_rows != (expected_revision,):
        raise RebaselineError(
            f"database must have exactly one {expected_revision} alembic version row"
        )
    if not bool(sentinel["boundary_is_0061"]):
        raise RebaselineError("0061 final-boundary contract sentinel is missing")
    if not bool(sentinel["m05_objects_absent"]):
        raise RebaselineError("pre-existing M05 objects reject a 0061 rebaseline")
    if preflight.catalog_lines != _EXPECTED_CATALOG_LINES:
        raise RebaselineError("legacy catalog fingerprint line count is not canonical")
    if preflight.catalog_sha256 not in _ALLOWED_CATALOG_SHA256:
        raise RebaselineError("legacy catalog fingerprint is not canonical")
    if preflight.app_data_rows <= 0:
        raise RebaselineError("rebaseline target must contain app data rows")
    return preflight


def _database_url() -> str:
    value = os.environ.get("PINVI_ALEMBIC_REBASELINE_DATABASE_URL", "")
    if not value:
        raise RebaselineError("PINVI_ALEMBIC_REBASELINE_DATABASE_URL is required")
    if not value.startswith(("postgresql://", "postgresql+asyncpg://")):
        raise RebaselineError("rebaseline database URL must be PostgreSQL")
    return value.replace("postgresql://", "postgresql+asyncpg://", 1)


async def _check(
    database_url: str, artifact: BackupArtifact, target: TargetManifest
) -> CatalogPreflight:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            preflight = await _preflight(connection, lock_version=False)
            _assert_backup_source_matches_preflight(artifact.manifest, preflight)
            _assert_target_manifest(
                target,
                preflight,
                artifact.manifest.sha256,
                artifact.manifest.created_at,
                allow_baseline_revision=False,
            )
            return preflight
    finally:
        await engine.dispose()


async def _capture_target(
    database_url: str, artifact: BackupArtifact, target_path: Path
) -> tuple[CatalogPreflight, TargetManifest]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            preflight = await _preflight(connection, lock_version=False)
            _assert_backup_source_matches_preflight(artifact.manifest, preflight)
    finally:
        await engine.dispose()
    _create_private_json(
        target_path,
        _target_manifest_payload(preflight, artifact.manifest.sha256),
        label="rebaseline target manifest",
    )
    return preflight, _read_target_manifest(target_path)


async def _apply(
    database_url: str,
    artifact: BackupArtifact,
    target: TargetManifest,
    receipt: Path,
) -> tuple[CatalogPreflight, str]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    preflight: CatalogPreflight | None = None
    receipt_payload: dict[str, Any] | None = None
    completed_state = "applied"
    try:
        async with engine.begin() as connection:
            await connection.execute(text(_REBASELINE_SERIALIZATION_LOCK_SQL))
            await _acquire_rebaseline_database_connection_fence(connection)
            locked_versions = await _read_version_rows(connection, lock=True)
            if locked_versions not in {(LEGACY_REVISION,), (BASELINE_REVISION,)}:
                raise RebaselineError(
                    "database must have exactly one 0061 or recoverable 0100 version row"
                )
            recovering = locked_versions == (BASELINE_REVISION,)
            preflight = await _preflight(
                connection,
                lock_version=False,
                expected_revision=BASELINE_REVISION if recovering else LEGACY_REVISION,
            )
            _assert_backup_source_matches_preflight(artifact.manifest, preflight)
            _assert_target_manifest(
                target,
                preflight,
                artifact.manifest.sha256,
                artifact.manifest.created_at,
                allow_baseline_revision=recovering,
            )
            receipt_payload = _receipt_payload(
                target.preflight if recovering else preflight.as_dict(),
                artifact,
                target,
                state="prepared",
                completed_at=None,
            )
            existing_receipt = _read_receipt(receipt) if receipt.exists() else None
            if existing_receipt is not None:
                _assert_receipt_intent(existing_receipt, receipt_payload)
            if recovering:
                if existing_receipt is None:
                    raise RebaselineError(
                        "0100 rebaseline row has no recoverable prepared receipt"
                    )
                if existing_receipt["state"] == "applied":
                    completed_state = "already_applied"
                else:
                    completed_state = "recovered"
            else:
                if (
                    existing_receipt is not None
                    and existing_receipt["state"] == "applied"
                ):
                    raise RebaselineError(
                        "applied receipt conflicts with 0061 version row"
                    )
                if existing_receipt is None:
                    _prepare_receipt(receipt, receipt_payload)
                result = await connection.execute(
                    text(
                        "UPDATE app.alembic_version "
                        "SET version_num = :baseline "
                        "WHERE version_num = :legacy"
                    ),
                    {"baseline": BASELINE_REVISION, "legacy": LEGACY_REVISION},
                )
                if result.rowcount != 1:
                    raise RebaselineError(
                        "alembic version row changed during the locked transition"
                    )
                version_rows = await _read_version_rows(connection, lock=False)
                if version_rows != (BASELINE_REVISION,):
                    raise RebaselineError(
                        "post-update alembic version row is not 20260824_0100"
                    )
    finally:
        await engine.dispose()

    if preflight is None or receipt_payload is None:
        raise RebaselineError("rebaseline transition did not produce a preflight")
    if completed_state != "already_applied":
        completed_payload = dict(receipt_payload)
        completed_payload["completed_at"] = (
            datetime.now(UTC).isoformat().replace("+00:00", "Z")
        )
        completed_payload["state"] = "applied"
        try:
            _finalize_receipt(receipt, completed_payload)
        except OSError as exc:
            raise RebaselineError(
                "version transition committed; rerun apply to recover the prepared receipt"
            ) from exc
    return preflight, completed_state


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    def add_backup_evidence_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument("--backup", required=True, type=Path)
        command.add_argument("--backup-checksum", required=True, type=Path)
        command.add_argument("--backup-manifest", required=True, type=Path)

    capture = subcommands.add_parser(
        "capture-target",
        help="root-only backup과 같은 0061 target identity/data manifest를 단발 봉인",
    )
    add_backup_evidence_arguments(capture)
    capture.add_argument("--target-manifest", required=True, type=Path)

    check = subcommands.add_parser(
        "check", help="읽기 전용 0061 rebaseline preflight와 target binding 검증"
    )
    add_backup_evidence_arguments(check)
    check.add_argument("--target-manifest", required=True, type=Path)

    apply = subcommands.add_parser("apply", help="검증된 0061 row를 0100으로 단발 전환")
    add_backup_evidence_arguments(apply)
    apply.add_argument("--target-manifest", required=True, type=Path)
    apply.add_argument("--receipt", required=True, type=Path)
    apply.add_argument(
        "--confirm-0061-to-0100",
        action="store_true",
        help="app.alembic_version 한 행의 단발 전환을 명시적으로 승인한다.",
    )
    return parser


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    database_url = _database_url()
    if args.command == "capture-target":
        _require_root()
        artifact = _validate_backup(
            args.backup, args.backup_checksum, args.backup_manifest
        )
        preflight, target = await _capture_target(
            database_url, artifact, args.target_manifest
        )
        return {
            "backup_manifest_sha256": artifact.manifest.sha256,
            "preflight": preflight.as_dict(),
            "state": "target_captured",
            "target_manifest_sha256": target.sha256,
        }

    artifact = _validate_backup(args.backup, args.backup_checksum, args.backup_manifest)
    target = _read_target_manifest(args.target_manifest)
    if args.command == "check":
        preflight = await _check(database_url, artifact, target)
        return {
            "backup_manifest_sha256": artifact.manifest.sha256,
            "preflight": preflight.as_dict(),
            "state": "checked",
            "target_manifest_sha256": target.sha256,
        }

    _require_root()
    if not args.confirm_0061_to_0100:
        raise RebaselineError("apply requires --confirm-0061-to-0100")
    preflight, state = await _apply(database_url, artifact, target, args.receipt)
    return {
        "backup_manifest_sha256": artifact.manifest.sha256,
        "backup_sha256": artifact.sha256,
        "preflight": preflight.as_dict(),
        "state": state,
        "target_manifest_sha256": target.sha256,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = asyncio.run(_run(args))
    except RebaselineError as exc:
        print(f"rebaseline rejected: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
