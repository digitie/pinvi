#!/usr/bin/env python3
"""M05 복원 증거를 실제 source dump와 fresh target 검증으로 생성한다.

DB URL과 runtime role은 명령행에 넣지 않고 다음 환경변수로만 받는다.

* ``PINVI_RESTORE_SOURCE_DATABASE_URL`` — dump source
* ``PINVI_RESTORE_STAGING_DATABASE_URL`` — owner/migrator target
* ``PINVI_RESTORE_RUNTIME_DATABASE_URL`` — non-owner runtime target login
* ``PINVI_RESTORE_RUNTIME_ROLE`` — runtime login name

이 도구는 repository의 backup/restore runner를 고정 호출하고, 성공한 실행의
결과만 root-owned evidence JSON으로 봉인한다. stdout/stderr에는 URL을 출력하지 않는다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

_BASH = "/usr/bin/bash"
_ROLE_RE = re.compile(r"[a-z_][a-z0-9_]{0,62}\Z")
_SCHEMA_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_TARGET_DATABASE_RE = re.compile(r"pinvi_m05_restore_[a-z0-9_]+\Z")
_SAFE_PATH = "/usr/local/bin:/usr/bin:/bin"


class RestoreDrillError(ValueError):
    """실제 복원 드릴이 M05 evidence 계약을 충족하지 못했다."""


def _command_env() -> dict[str, str]:
    environment = os.environ.copy()
    if environment.get("PINVI_M05_RESTORE_TEST_MODE") != "1":
        environment["PATH"] = _SAFE_PATH
        environment["PINVI_BACKUP_PG_DUMP_BIN"] = "/usr/local/bin/pg_dump"
        environment["PINVI_BACKUP_DOCKER_BIN"] = "/usr/bin/docker"
    return environment


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _write_json(path: Path, value: object) -> None:
    raw = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode(
        "utf-8"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RestoreDrillError(
            "restore evidence output already exists or is unsafe"
        ) from exc
    try:
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if fd != -1:
            os.close(fd)


def _run(
    command: list[str],
    *,
    env: dict[str, str],
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except OSError as exc:
        raise RestoreDrillError("restore drill command could not be started") from exc
    if check and completed.returncode != 0:
        raise RestoreDrillError("restore drill command failed")
    return completed


def _database_url(name: str) -> str:
    value = os.environ.get(name, "")
    if not value or any(character.isspace() for character in value):
        raise RestoreDrillError(f"{name} must be supplied via environment")
    if value.startswith("postgresql+asyncpg://"):
        value = "postgresql://" + value.removeprefix("postgresql+asyncpg://")
    if not value.startswith(("postgres://", "postgresql://")):
        raise RestoreDrillError(f"{name} must be a PostgreSQL URL")
    return value


def _scalar(
    database_url: str, sql: str, *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            "psql",
            "--no-psqlrc",
            "--tuples-only",
            "--no-align",
            "--set=ON_ERROR_STOP=1",
            f"--dbname={database_url}",
            f"--command={sql}",
        ],
        env=_command_env(),
        check=check,
    )


def _require_true(result: subprocess.CompletedProcess[str], *, name: str) -> None:
    if result.returncode != 0 or result.stdout.strip() != "t":
        raise RestoreDrillError(f"restore verification failed: {name}")


def _runtime_role_check(database_url: str, *, schema: str, expected_role: str) -> None:
    if not _ROLE_RE.fullmatch(expected_role):
        raise RestoreDrillError("restore runtime role is invalid")
    sql = f"""
SELECT r.rolcanlogin
  AND current_user = '{expected_role}'
  AND NOT r.rolsuper
  AND NOT r.rolcreaterole
  AND NOT r.rolcreatedb
  AND NOT r.rolreplication
  AND has_schema_privilege(current_user, '{schema}', 'USAGE')
  AND NOT has_schema_privilege(current_user, '{schema}', 'CREATE')
  AND NOT has_database_privilege(current_user, current_database(), 'CREATE')
  AND NOT EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = '{schema}'
        AND c.relkind IN ('r', 'p')
        AND NOT (
            has_table_privilege(current_user, c.oid, 'SELECT')
            AND has_table_privilege(current_user, c.oid, 'INSERT')
            AND has_table_privilege(current_user, c.oid, 'UPDATE')
            AND has_table_privilege(current_user, c.oid, 'DELETE')
        )
  )
  AND NOT EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = '{schema}'
        AND c.relkind = 'S'
        AND NOT (
            has_sequence_privilege(current_user, c.oid, 'USAGE')
            AND has_sequence_privilege(current_user, c.oid, 'SELECT')
            AND has_sequence_privilege(current_user, c.oid, 'UPDATE')
        )
  )
  AND NOT EXISTS (
      SELECT 1 FROM pg_namespace n
      WHERE n.nspname = '{schema}'
        AND (n.nspowner = r.oid OR pg_has_role(r.oid, n.nspowner, 'member'))
  )
FROM pg_roles r
WHERE r.rolname = current_user
""".strip()
    _require_true(_scalar(database_url, sql), name="runtime role")


def _staging_role_check(
    database_url: str, *, expected_role: str, runtime_role: str
) -> None:
    if not _ROLE_RE.fullmatch(expected_role):
        raise RestoreDrillError("restore staging role is invalid")
    if expected_role == runtime_role:
        raise RestoreDrillError("restore staging and runtime roles must differ")
    sql = f"""
SELECT current_user = '{expected_role}'
  AND r.rolcanlogin
  AND NOT r.rolreplication
FROM pg_roles r
WHERE r.rolname = current_user
""".strip()
    _require_true(_scalar(database_url, sql), name="staging role")


def _trigger_check(database_url: str, *, schema: str) -> None:
    sql = f"""
SELECT count(*) = 6
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = '{schema}'
  AND c.relname IN (
      'ktm_feature_reference_reconciliation_delivery_attempts',
      'ktm_feature_reference_reconciliation_applied_receipts',
      'ktm_feature_reference_reconciliation_impacts'
  )
  AND t.tgenabled = 'A'
""".strip()
    _require_true(_scalar(database_url, sql), name="always-enabled M05 triggers")


def _trigger_bypass_is_blocked(database_url: str, *, schema: str) -> None:
    sql = f"""
BEGIN;
SET LOCAL session_replication_role = replica;
UPDATE {schema}.ktm_feature_reference_reconciliation_delivery_attempts
SET event_sha256 = event_sha256
WHERE event_id = (
    SELECT event_id
    FROM {schema}.ktm_feature_reference_reconciliation_delivery_attempts
    ORDER BY observed_at
    LIMIT 1
);
ROLLBACK;
""".strip()
    result = _scalar(database_url, sql, check=False)
    if result.returncode == 0 or "append-only" not in result.stderr:
        raise RestoreDrillError(
            "M05 append-only trigger did not block replication bypass"
        )


def _identity(database_url: str, *, schema: str) -> dict[str, object]:
    sql = (
        "SELECT json_build_object("
        "'database', current_database(), "
        "'user', current_user, "
        "'database_oid', d.oid::text, "
        "'system_identifier', (pg_control_system()).system_identifier::text, "
        "'schema_exists', to_regnamespace('" + schema + "') IS NOT NULL, "
        "'server_version_num', current_setting('server_version_num'))::text "
        "FROM pg_database d WHERE d.datname = current_database()"
    )
    result = _scalar(database_url, sql)
    raw = result.stdout.strip()
    if not raw:
        raise RestoreDrillError("database identity query returned no result")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RestoreDrillError(
            "database identity query returned invalid JSON"
        ) from exc
    if not isinstance(value, dict) or set(value) != {
        "database",
        "database_oid",
        "schema_exists",
        "server_version_num",
        "system_identifier",
        "user",
    }:
        raise RestoreDrillError("database identity query returned an invalid identity")
    return value


def _identity_key(identity: dict[str, object]) -> tuple[object, object, object]:
    return (
        identity["database"],
        identity["database_oid"],
        identity["system_identifier"],
    )


def _identity_sha256(identity: dict[str, object]) -> str:
    return _sha256(_canonical_json(identity))


def _single_dump(directory: Path) -> Path:
    dumps = sorted(directory.glob("pinvi-app-*.dump"))
    if len(dumps) != 1 or not dumps[0].is_file() or dumps[0].is_symlink():
        raise RestoreDrillError("backup runner did not produce exactly one dump")
    if not dumps[0].with_name(f"{dumps[0].name}.sha256").is_file():
        raise RestoreDrillError("backup runner did not produce a checksum sidecar")
    return dumps[0]


def _secure_output_parent(path: Path, *, require_root_owned: bool) -> None:
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise RestoreDrillError("restore evidence parent must be a regular directory")
    metadata = parent.stat()
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise RestoreDrillError("restore evidence parent must be mode 0700")
    if require_root_owned and metadata.st_uid != 0:
        raise RestoreDrillError("restore evidence parent must be root-owned")


def _source_revision(root: Path) -> str:
    expected = os.environ.get("PINVI_SOURCE_REVISION", "")
    if not _COMMIT_RE.fullmatch(expected):
        raise RestoreDrillError(
            "restore producer requires a full PINVI_SOURCE_REVISION"
        )
    try:
        revision = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            env=_command_env(),
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
            env=_command_env(),
        ).stdout
        if revision != expected or status:
            raise RestoreDrillError(
                "restore producer checkout is not a clean PINVI_SOURCE_REVISION"
            )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RestoreDrillError(
            "restore producer source revision could not be verified"
        ) from exc
    if not _COMMIT_RE.fullmatch(revision):
        raise RestoreDrillError("restore producer source revision is invalid")
    return revision


def _run_drill(args: argparse.Namespace) -> int:
    output: Path = args.output
    _secure_output_parent(output, require_root_owned=args.require_root_owned)
    if args.require_root_owned and os.environ.get("PINVI_M05_RESTORE_TEST_MODE") == "1":
        raise RestoreDrillError("restore test mode cannot produce root-owned evidence")
    if not _SCHEMA_RE.fullmatch(args.schema):
        raise RestoreDrillError("restore schema is invalid")
    if not _ROLE_RE.fullmatch(args.runtime_role):
        raise RestoreDrillError("restore runtime role is invalid")
    if not _ROLE_RE.fullmatch(args.staging_role):
        raise RestoreDrillError("restore staging role is invalid")
    if args.runtime_role == args.staging_role:
        raise RestoreDrillError("restore staging and runtime roles must differ")
    source_url = _database_url(args.source_database_url_env)
    target_url = _database_url(args.staging_database_url_env)
    runtime_url = _database_url(args.runtime_database_url_env)
    source_identity_pre = _identity(source_url, schema=args.schema)
    target_identity_pre = _identity(target_url, schema=args.schema)
    runtime_identity_pre = _identity(runtime_url, schema=args.schema)
    source_key = _identity_key(source_identity_pre)
    target_key = _identity_key(target_identity_pre)
    runtime_key = _identity_key(runtime_identity_pre)
    if source_key in {target_key, runtime_key} or target_key != runtime_key:
        raise RestoreDrillError(
            "restore source, owner target, and runtime target must be distinct database identities"
        )
    target_database = target_identity_pre.get("database")
    if (
        not isinstance(target_database, str)
        or _TARGET_DATABASE_RE.fullmatch(target_database) is None
    ):
        raise RestoreDrillError(
            "restore target database is outside the M05 disposable prefix"
        )
    _staging_role_check(
        target_url,
        expected_role=args.staging_role,
        runtime_role=args.runtime_role,
    )
    _runtime_role_check(
        runtime_url,
        schema=args.schema,
        expected_role=args.runtime_role,
    )

    root = Path(__file__).resolve().parents[1]
    backup_script = root / "scripts/backup-db.sh"
    restore_script = root / "scripts/restore-staging-drill.sh"
    for script in (backup_script, restore_script):
        if script.is_symlink() or not script.is_file():
            raise RestoreDrillError("restore runner source is not canonical")
    source_revision = _source_revision(root)

    with tempfile.TemporaryDirectory(
        prefix="pinvi-m05-restore-", dir=output.parent
    ) as temporary:
        temporary_dir = Path(temporary)
        backup_env = _command_env()
        backup_env.update(
            {
                "PINVI_BACKUP_DATABASE_URL": source_url,
                "PINVI_DATABASE_URL": "",
                "PINVI_BACKUP_SCHEMA": args.schema,
                "PINVI_BACKUP_DIR": str(temporary_dir),
                "PINVI_BACKUP_MIN_FREE_BYTES": "0",
                "PINVI_BACKUP_DOCKER_FALLBACK": "1",
            }
        )
        backup = _run([_BASH, str(backup_script)], env=backup_env)
        dump = _single_dump(temporary_dir)
        source_identity_after_backup = _identity(source_url, schema=args.schema)
        target_identity_before_restore = _identity(target_url, schema=args.schema)
        if _identity_key(source_identity_after_backup) != source_key:
            raise RestoreDrillError("source database identity changed during backup")
        if _identity_key(target_identity_before_restore) != target_key:
            raise RestoreDrillError("target database identity changed before restore")

        restore_env = _command_env()
        restore_env.update(
            {
                "PINVI_RESTORE_STAGING_DATABASE_URL": target_url,
                "PINVI_RESTORE_DATABASE_URL": target_url,
                "PINVI_RESTORE_SCHEMA": args.schema,
                "PINVI_RESTORE_APP_ROLE": args.runtime_role,
                "PINVI_RESTORE_DRILL_ROLLBACK_REHEARSAL": "precheck",
            }
        )
        restore = _run([_BASH, str(restore_script), "run", str(dump)], env=restore_env)
        required_markers = (
            "DRILL_EVIDENCE=checksum=verified",
            "DRILL_EVIDENCE=pg_restore_list=ok",
            "DRILL_EVIDENCE=rollback_rehearsal=precheck_guard_schema_unchanged",
            "DRILL_PHASE=complete:success:staging restore drill completed",
            "RESTORE_COMMAND=pg_restore --clean --if-exists --exit-on-error --no-owner --no-privileges",
        )
        if any(marker not in restore.stdout for marker in required_markers):
            raise RestoreDrillError(
                "restore staging runner did not produce all required markers"
            )

        source_revision_after = _source_revision(root)
        if source_revision_after != source_revision:
            raise RestoreDrillError("restore runner changed the source checkout")
        _runtime_role_check(
            runtime_url,
            schema=args.schema,
            expected_role=args.runtime_role,
        )
        _trigger_check(target_url, schema=args.schema)
        _trigger_bypass_is_blocked(target_url, schema=args.schema)
        target_identity = _identity(target_url, schema=args.schema)
        runtime_identity = _identity(runtime_url, schema=args.schema)
        if (
            _identity_key(target_identity) != target_key
            or _identity_key(runtime_identity) != target_key
        ):
            raise RestoreDrillError(
                "restore target identity changed or does not match the runtime target"
            )

        execution_output = (
            f"{backup.stdout}\0{backup.stderr}\0{restore.stdout}\0{restore.stderr}"
        ).encode()
        evidence = {
            "backup_runner_sha256": _sha256(backup_script.read_bytes()),
            "dump_sha256": _sha256(dump.read_bytes()),
            "execution_id": str(uuid4()),
            "no_owner_restore": True,
            "restore_command": (
                "pg_restore --clean --if-exists --exit-on-error "
                "--no-owner --no-privileges"
            ),
            "restore_output_sha256": _sha256(execution_output),
            "restore_runner_sha256": _sha256(restore_script.read_bytes()),
            "runtime_role_verified": True,
            "staging_role_verified": True,
            "runtime_role": args.runtime_role,
            "staging_role": args.staging_role,
            "source_db_identity": source_identity_pre,
            "source_db_identity_after_backup": source_identity_after_backup,
            "target_db_identity_before_restore": target_identity_before_restore,
            "target_db_identity": target_identity,
            "runtime_db_identity": runtime_identity,
            "source_db_identity_sha256": _identity_sha256(source_identity_pre),
            "source_db_identity_after_backup_sha256": _identity_sha256(
                source_identity_after_backup
            ),
            "source_revision": source_revision,
            "status": "passed",
            "target_db_identity_sha256": _identity_sha256(target_identity),
            "target_db_identity_before_restore_sha256": _identity_sha256(
                target_identity_before_restore
            ),
            "trigger_guard_verified": True,
            "runtime_db_identity_sha256": _identity_sha256(runtime_identity),
        }
    _write_json(output, evidence)
    print(f"restore_evidence_sha256={_sha256(_canonical_json(evidence))}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", choices=("run",))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--schema", default="app")
    parser.add_argument(
        "--runtime-role", default=os.environ.get("PINVI_RESTORE_RUNTIME_ROLE", "")
    )
    parser.add_argument(
        "--staging-role", default=os.environ.get("PINVI_RESTORE_STAGING_ROLE", "")
    )
    parser.add_argument(
        "--source-database-url-env",
        default="PINVI_RESTORE_SOURCE_DATABASE_URL",
    )
    parser.add_argument(
        "--staging-database-url-env",
        default="PINVI_RESTORE_STAGING_DATABASE_URL",
    )
    parser.add_argument(
        "--runtime-database-url-env",
        default="PINVI_RESTORE_RUNTIME_DATABASE_URL",
    )
    parser.add_argument("--require-root-owned", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run_drill(args)
    except (OSError, RestoreDrillError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"M05 restore drill failed: {exc}") from None


if __name__ == "__main__":
    raise SystemExit(main())
