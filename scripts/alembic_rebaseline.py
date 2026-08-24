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
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

LEGACY_REVISION = "20260821_0061"
BASELINE_REVISION = "20260824_0100"
_EXPECTED_CATALOG_LINES = 1590
_EXPECTED_CATALOG_SHA256 = (
    "30257369c7141b19d77071ce6414c4cdc8195a66bac7dc0a49aa72cd66e03cf7"
)
_CHECKSUM = re.compile(r"^[0-9a-f]{64}$")

# pg_dump 기반 기준선은 constraint/source location을 다시 정규화한다. 그래서 이
# 지문은 양쪽에 공통인 catalog 구조와 권한 경계만 고정하고, expression 세부는 아래
# sentinel query가 명시적으로 검증한다.
_CATALOG_FINGERPRINT_SQL = """
WITH object_lines(line) AS (
  SELECT jsonb_build_array('schema', n.nspname, pg_get_userbyid(n.nspowner),
                           COALESCE(n.nspacl::text, ''))::text
  FROM pg_namespace AS n
  WHERE n.nspname = 'app'
  UNION ALL
  SELECT jsonb_build_array('relation', c.relname, c.relkind, c.relpersistence,
                           pg_get_userbyid(c.relowner), COALESCE(c.reloptions::text, ''),
                           COALESCE(c.relacl::text, ''))::text
  FROM pg_class AS c
  JOIN pg_namespace AS n ON n.oid = c.relnamespace
  WHERE n.nspname = 'app' AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
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
  WHERE n.nspname = 'app' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
    AND a.attnum > 0 AND NOT a.attisdropped
  UNION ALL
  SELECT jsonb_build_array('constraint', c.relname, con.conname, con.contype,
                           con.condeferrable, con.condeferred, con.convalidated,
                           con.conkey::text,
                           CASE WHEN con.confrelid = 0 THEN ''
                                ELSE con.confrelid::regclass::text END,
                           con.confkey::text, con.confupdtype, con.confdeltype,
                           con.confmatchtype)::text
  FROM pg_constraint AS con
  JOIN pg_class AS c ON c.oid = con.conrelid
  JOIN pg_namespace AS n ON n.oid = c.relnamespace
  WHERE n.nspname = 'app'
  UNION ALL
  SELECT jsonb_build_array('index', table_rel.relname, index_rel.relname,
                           i.indisunique, i.indisprimary, i.indisvalid, i.indisready,
                           i.indkey::text, i.indclass::text, i.indcollation::text,
                           i.indoption::text)::text
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

_LEGACY_SENTINELS_SQL = """
SELECT
  current_database() AS database_name,
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
    server_version_num: int
    version_rows: tuple[str, ...]
    catalog_lines: int
    catalog_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "database_name": self.database_name,
            "server_version_num": self.server_version_num,
            "version_rows": list(self.version_rows),
            "catalog_lines": self.catalog_lines,
            "catalog_sha256": self.catalog_sha256,
            "expected_catalog_lines": _EXPECTED_CATALOG_LINES,
            "expected_catalog_sha256": _EXPECTED_CATALOG_SHA256,
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_root() -> None:
    if os.geteuid() != 0:
        raise RebaselineError("apply requires a root OS account")


def _validate_protected_file(path: Path, *, label: str) -> Path:
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
    if metadata.st_mode & 0o022:
        raise RebaselineError(f"{label} must not be group- or world-writable")
    return path


def _read_checksum(checksum_file: Path) -> str:
    _validate_protected_file(checksum_file, label="backup checksum file")
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


def _validate_backup(backup: Path, checksum_file: Path) -> str:
    _validate_protected_file(backup, label="backup file")
    expected = _read_checksum(checksum_file)
    actual = _sha256_file(backup)
    if actual != expected:
        raise RebaselineError("backup SHA-256 does not match its checksum file")
    return actual


def _prepare_receipt(path: Path, payload: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise RebaselineError("receipt path must not already exist")
    parent = path.parent
    try:
        parent_metadata = parent.stat()
    except OSError as exc:
        raise RebaselineError("receipt directory is unavailable") from exc
    if parent_metadata.st_uid != 0 or parent_metadata.st_mode & 0o022:
        raise RebaselineError(
            "receipt directory must be root-owned and not writable by group/other"
        )
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as exc:
        raise RebaselineError("receipt file cannot be reserved") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
        stream.write("\n")


def _finalize_receipt(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
        stream.write("\n")
    os.chmod(path, 0o600)


async def _catalog_fingerprint(connection: AsyncConnection) -> tuple[int, str]:
    rows = tuple((await connection.execute(text(_CATALOG_FINGERPRINT_SQL))).scalars())
    payload = ("\n".join(rows) + "\n").encode("utf-8")
    return len(rows), hashlib.sha256(payload).hexdigest()


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
    connection: AsyncConnection, *, lock_version: bool
) -> CatalogPreflight:
    version_rows = await _read_version_rows(connection, lock=lock_version)
    sentinel = (await connection.execute(text(_LEGACY_SENTINELS_SQL))).mappings().one()
    catalog_lines, catalog_sha256 = await _catalog_fingerprint(connection)
    preflight = CatalogPreflight(
        database_name=str(sentinel["database_name"]),
        server_version_num=int(sentinel["server_version_num"]),
        version_rows=version_rows,
        catalog_lines=catalog_lines,
        catalog_sha256=catalog_sha256,
    )
    if preflight.server_version_num // 10000 != 16:
        raise RebaselineError("rebaseline requires PostgreSQL 16")
    if preflight.version_rows != (LEGACY_REVISION,):
        raise RebaselineError(
            "database must have exactly one 20260821_0061 alembic version row"
        )
    if not bool(sentinel["boundary_is_0061"]):
        raise RebaselineError("0061 final-boundary contract sentinel is missing")
    if not bool(sentinel["m05_objects_absent"]):
        raise RebaselineError("pre-existing M05 objects reject a 0061 rebaseline")
    if preflight.catalog_lines != _EXPECTED_CATALOG_LINES:
        raise RebaselineError("legacy catalog fingerprint line count is not canonical")
    if preflight.catalog_sha256 != _EXPECTED_CATALOG_SHA256:
        raise RebaselineError("legacy catalog fingerprint is not canonical")
    return preflight


def _database_url() -> str:
    value = os.environ.get("PINVI_ALEMBIC_REBASELINE_DATABASE_URL", "")
    if not value:
        raise RebaselineError("PINVI_ALEMBIC_REBASELINE_DATABASE_URL is required")
    if not value.startswith(("postgresql://", "postgresql+asyncpg://")):
        raise RebaselineError("rebaseline database URL must be PostgreSQL")
    return value.replace("postgresql://", "postgresql+asyncpg://", 1)


async def _check(database_url: str) -> CatalogPreflight:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            return await _preflight(connection, lock_version=False)
    finally:
        await engine.dispose()


async def _apply(
    database_url: str, backup_sha256: str, receipt: Path
) -> CatalogPreflight:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            preflight = await _preflight(connection, lock_version=True)
            prepared_payload = {
                "action": "0061_to_0100_rebaseline",
                "backup_sha256": backup_sha256,
                "completed_at": None,
                "preflight": preflight.as_dict(),
                "state": "prepared",
            }
            _prepare_receipt(receipt, prepared_payload)
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

    completed_payload = {
        "action": "0061_to_0100_rebaseline",
        "backup_sha256": backup_sha256,
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "preflight": preflight.as_dict(),
        "state": "applied",
    }
    _finalize_receipt(receipt, completed_payload)
    return preflight


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("check", help="읽기 전용 0061 rebaseline preflight")
    apply = subcommands.add_parser("apply", help="검증된 0061 row를 0100으로 단발 전환")
    apply.add_argument("--backup", required=True, type=Path)
    apply.add_argument("--backup-checksum", required=True, type=Path)
    apply.add_argument("--receipt", required=True, type=Path)
    apply.add_argument(
        "--confirm-0061-to-0100",
        action="store_true",
        help="app.alembic_version 한 행의 단발 전환을 명시적으로 승인한다.",
    )
    return parser


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    database_url = _database_url()
    if args.command == "check":
        preflight = await _check(database_url)
        return {"state": "checked", "preflight": preflight.as_dict()}

    _require_root()
    if not args.confirm_0061_to_0100:
        raise RebaselineError("apply requires --confirm-0061-to-0100")
    backup_sha256 = _validate_backup(args.backup, args.backup_checksum)
    preflight = await _apply(database_url, backup_sha256, args.receipt)
    return {
        "state": "applied",
        "backup_sha256": backup_sha256,
        "preflight": preflight.as_dict(),
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
