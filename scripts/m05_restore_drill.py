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
import shutil
import socket
import stat
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

_ROLE_RE = re.compile(r"[a-z_][a-z0-9_]{0,62}\Z")
_SCHEMA_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_TARGET_DATABASE_RE = re.compile(r"pinvi_m05_restore_[a-z0-9_]+\Z")
_SAFE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_TOOL_TRUST_MANIFEST_ENV = "PINVI_M05_RESTORE_TOOL_TRUST_MANIFEST"
_TRUSTED_TOOL_NAMES = ("bash", "git", "pg_dump", "pg_restore", "psql")
_TRUSTED_TOOL_DIRECTORIES = (Path("/usr/local/bin"), Path("/usr/bin"), Path("/bin"))
_POSTGRES_TOOL_DIRECTORY_RE = re.compile(r"/usr/lib/postgresql/[0-9]+/bin\Z")
_PINNED_TOOL_PATHS: dict[str, str] = {}
_TOOL_TRUST_MANIFEST_SHA256 = ""


class RestoreDrillError(ValueError):
    """실제 복원 드릴이 M05 evidence 계약을 충족하지 못했다."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def _canonical_github_opener() -> urllib.request.OpenerDirector:
    # GitHub PR provenance must not be supplied by ambient HTTP(S) proxy variables.
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirectHandler(),
    )


def _command_env() -> dict[str, str]:
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.startswith("GIT_"):
            environment.pop(name, None)
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    if environment.get("PINVI_M05_RESTORE_TEST_MODE") != "1":
        environment["PATH"] = _SAFE_PATH
        for name in tuple(environment):
            if name.startswith("GIT_"):
                environment.pop(name, None)
        environment["GIT_CONFIG_GLOBAL"] = "/dev/null"
        environment["GIT_CONFIG_SYSTEM"] = "/dev/null"
        environment["GIT_CONFIG_NOSYSTEM"] = "1"
        environment["GIT_TERMINAL_PROMPT"] = "0"
        for name in (
            "PINVI_BACKUP_PG_DUMP_BIN",
            "PINVI_BACKUP_DOCKER_BIN",
            "PINVI_BACKUP_DOCKER_FALLBACK",
            "PINVI_BACKUP_DOCKER_IMAGE",
            "PINVI_BACKUP_DOCKER_NETWORK",
            "PINVI_BACKUP_PSQL_BIN",
            "PINVI_RESTORE_PG_RESTORE_BIN",
            "PINVI_RESTORE_PSQL_BIN",
            "PINVI_RESTORE_REQUIRE_FRESH_SCHEMA",
            "BASH_ENV",
            "CDPATH",
            "ENV",
            "LD_AUDIT",
            "LD_LIBRARY_PATH",
            "LD_PRELOAD",
            "PYTHONHOME",
            "PYTHONPATH",
            "RUBYLIB",
            "PGAPPNAME",
            "PGCONNECT_TIMEOUT",
            "PGDATABASE",
            "PGHOST",
            "PGHOSTADDR",
            "PGOPTIONS",
            "PGPASSFILE",
            "PGPASSWORD",
            "PGPORT",
            "PGSERVICE",
            "PGSERVICEFILE",
            "PGSSLCERT",
            "PGSSLMODE",
            "PGSSLKEY",
            "PGSSLROOTCERT",
            "PGTARGETSESSIONATTRS",
            "PSQLRC",
        ):
            environment.pop(name, None)
    return environment


def _tool_path(name: str) -> str:
    pinned = _PINNED_TOOL_PATHS.get(name)
    if pinned is not None:
        return pinned
    if os.environ.get("PINVI_M05_RESTORE_TEST_MODE") == "1":
        path = shutil.which(name)
        if path is None:
            raise RestoreDrillError(f"restore test tool is missing: {name}")
        return path
    candidates = [directory / name for directory in _TRUSTED_TOOL_DIRECTORIES]
    candidates.extend(
        directory / name for directory in sorted(Path("/usr/lib/postgresql").glob("*/bin"))
    )
    for candidate in candidates:
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            continue
        resolved = candidate.resolve()
        if not _trusted_tool_path(resolved, name):
            continue
        manifest_path = os.environ.get(_TOOL_TRUST_MANIFEST_ENV, "")
        if not manifest_path:
            raise RestoreDrillError("non-test restore requires a root-owned tool trust manifest")
        manifest = _tool_trust_manifest(Path(manifest_path))
        expected = manifest.get(name)
        if expected is None or expected["path"] != str(resolved):
            raise RestoreDrillError(f"restore tool is not pinned by the trust manifest: {name}")
        if expected["sha256"] != _sha256(resolved.read_bytes()):
            raise RestoreDrillError(
                f"restore tool digest does not match the trust manifest: {name}"
            )
        return str(resolved)
    raise RestoreDrillError(f"pinned restore tool is missing: {name}")


def _trusted_tool_path(path: Path, name: str) -> bool:
    if path.name != name or path.is_symlink() or not path.is_file() or not os.access(path, os.X_OK):
        return False
    parent = str(path.resolve().parent)
    return Path(parent) in _TRUSTED_TOOL_DIRECTORIES or bool(
        _POSTGRES_TOOL_DIRECTORY_RE.fullmatch(parent)
    )


def _tool_identity(name: str) -> dict[str, str]:
    path = _tool_path(name)
    return {"path": path, "sha256": _sha256(Path(path).read_bytes())}


def _copy_verified_tool(tool: dict[str, str], destination: Path) -> dict[str, str]:
    """복원 runner가 원본 PATH를 다시 참조하지 않도록 private copy를 봉인한다."""

    source = Path(tool["path"])
    if source.is_symlink() or not source.is_file() or not os.access(source, os.X_OK):
        raise RestoreDrillError("restore tool source is not a regular executable")
    target = destination / source.name
    shutil.copyfile(source, target)
    target.chmod(0o700)
    digest = _sha256(target.read_bytes())
    if digest != tool["sha256"]:
        raise RestoreDrillError(f"restore tool changed while copying: {source.name}")
    return {"path": str(target), "sha256": digest}


def _tool_trust_manifest(path: Path) -> dict[str, dict[str, str]]:
    global _TOOL_TRUST_MANIFEST_SHA256
    if path.is_symlink() or not path.is_file():
        raise RestoreDrillError("restore tool trust manifest must be a regular file")
    metadata = path.stat()
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise RestoreDrillError("restore tool trust manifest must be mode 0600")
    if metadata.st_uid != os.geteuid():
        raise RestoreDrillError("restore tool trust manifest owner is invalid")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RestoreDrillError("restore tool trust manifest is invalid JSON") from exc
    if not isinstance(value, dict) or set(value) != {"tools", "version"} or value["version"] != 1:
        raise RestoreDrillError("restore tool trust manifest schema is invalid")
    tools = value["tools"]
    if not isinstance(tools, dict) or set(tools) != set(_TRUSTED_TOOL_NAMES):
        raise RestoreDrillError("restore tool trust manifest inventory is invalid")
    result: dict[str, dict[str, str]] = {}
    for name in _TRUSTED_TOOL_NAMES:
        entry = tools[name]
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise RestoreDrillError(f"restore tool trust manifest entry is invalid: {name}")
        tool_path = entry["path"]
        digest = entry["sha256"]
        tool_file = Path(tool_path) if isinstance(tool_path, str) else Path("/")
        if (
            not isinstance(tool_path, str)
            or not tool_path.startswith("/")
            or not _trusted_tool_path(tool_file, name)
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or _sha256(tool_file.read_bytes()) != digest
        ):
            raise RestoreDrillError(f"restore tool trust manifest binding is invalid: {name}")
        result[name] = {"path": str(tool_file), "sha256": digest}
    _TOOL_TRUST_MANIFEST_SHA256 = _sha256(raw)
    return result


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
    raw = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RestoreDrillError("restore evidence output already exists or is unsafe") from exc
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
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=env,
            input=input_text,
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
    if os.environ.get("PINVI_M05_RESTORE_TEST_MODE") == "1":
        return value
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port or 5432
    except ValueError as exc:
        raise RestoreDrillError(f"{name} is not a valid PostgreSQL URL") from exc
    if hostname is None:
        raise RestoreDrillError(f"{name} must include a database host")
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if any(key == "hostaddr" for key, _ in query):
        raise RestoreDrillError(f"{name} must not provide an unpinned hostaddr")
    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise RestoreDrillError(f"{name} host could not be resolved") from exc
    resolved_addresses = [item[4][0] for item in addresses if item[4]]
    if not resolved_addresses:
        raise RestoreDrillError(f"{name} host has no resolved address")
    query.append(("hostaddr", resolved_addresses[0]))
    return urlunsplit(parsed._replace(query=urlencode(query)))


def _scalar(database_url: str, sql: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            _tool_path("psql"),
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


def _psql_file(
    database_url: str, sql: str, *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            _tool_path("psql"),
            "--no-psqlrc",
            "--set=ON_ERROR_STOP=1",
            f"--dbname={database_url}",
            "--file=-",
        ],
        env=_command_env(),
        check=check,
        input_text=sql,
    )


def _require_true(result: subprocess.CompletedProcess[str], *, name: str) -> None:
    if result.returncode != 0 or result.stdout.strip() != "t":
        raise RestoreDrillError(f"restore verification failed: {name}")


def _runtime_role_check(
    database_url: str,
    *,
    schema: str,
    expected_role: str,
    require_schema_privileges: bool = True,
) -> None:
    if not _ROLE_RE.fullmatch(expected_role):
        raise RestoreDrillError("restore runtime role is invalid")
    if require_schema_privileges:
        schema_checks = f"""
  AND has_schema_privilege(current_user, '{schema}', 'USAGE')
  AND NOT has_schema_privilege(current_user, '{schema}', 'CREATE')
  AND NOT has_schema_privilege(current_user, 'x_extension', 'CREATE')
  AND NOT EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname IN ('{schema}', 'x_extension')
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
      WHERE n.nspname IN ('{schema}', 'x_extension')
        AND (c.relowner = r.oid OR pg_has_role(r.oid, c.relowner, 'member'))
  )
  AND NOT EXISTS (
      SELECT 1
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname IN ('{schema}', 'x_extension')
        AND (p.proowner = r.oid OR pg_has_role(r.oid, p.proowner, 'member'))
  )
  AND NOT EXISTS (
      SELECT 1
      FROM pg_type t
      JOIN pg_namespace n ON n.oid = t.typnamespace
      WHERE n.nspname IN ('{schema}', 'x_extension')
        AND (t.typowner = r.oid OR pg_has_role(r.oid, t.typowner, 'member'))
  )
  AND NOT EXISTS (
      SELECT 1
      FROM pg_extension e
      JOIN pg_namespace n ON n.oid = e.extnamespace
      WHERE n.nspname IN ('{schema}', 'x_extension')
        AND (e.extowner = r.oid OR pg_has_role(r.oid, e.extowner, 'member'))
  )
  AND NOT EXISTS (
      SELECT 1
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname IN ('{schema}', 'x_extension')
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
  )"""
    else:
        schema_checks = f"""
  AND NOT EXISTS (
      SELECT 1 FROM pg_namespace n WHERE n.nspname = '{schema}'
  )"""
    schema_checks = f"""
  AND NOT has_database_privilege(current_user, current_database(), 'CREATE')
  AND NOT has_schema_privilege(current_user, 'public', 'CREATE')
{schema_checks}"""
    sql = f"""
SELECT r.rolcanlogin
  AND current_user = '{expected_role}'
  AND NOT r.rolsuper
  AND NOT r.rolcreaterole
  AND NOT r.rolcreatedb
  AND NOT r.rolreplication
  AND NOT r.rolbypassrls
  AND NOT r.rolinherit
  AND NOT EXISTS (
      SELECT 1 FROM pg_auth_members m
      WHERE m.member = r.oid
  )
{schema_checks}
FROM pg_roles r
WHERE r.rolname = current_user
""".strip()
    _require_true(_scalar(database_url, sql), name="runtime role")


def _staging_role_check(database_url: str, *, expected_role: str, runtime_role: str) -> None:
    if not _ROLE_RE.fullmatch(expected_role):
        raise RestoreDrillError("restore staging role is invalid")
    if expected_role == runtime_role:
        raise RestoreDrillError("restore staging and runtime roles must differ")
    sql = f"""
SELECT current_user = '{expected_role}'
  AND r.rolcanlogin
  AND NOT r.rolsuper
  AND NOT r.rolcreaterole
  AND NOT r.rolreplication
  AND NOT r.rolbypassrls
  AND NOT EXISTS (
      SELECT 1 FROM pg_auth_members m
      WHERE m.member = r.oid
  )
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
        raise RestoreDrillError("M05 append-only trigger did not block replication bypass")


def _identity(database_url: str, *, schema: str) -> dict[str, object]:
    try:
        parsed = urlsplit(database_url)
        host = parsed.hostname
        port = parsed.port or 5432
    except ValueError as exc:
        raise RestoreDrillError("database identity URL is invalid") from exc
    if host is None:
        raise RestoreDrillError("database identity URL has no host")
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    hostaddr = query.get("hostaddr")
    if not hostaddr and os.environ.get("PINVI_M05_RESTORE_TEST_MODE") != "1":
        raise RestoreDrillError("database identity URL is missing the pinned hostaddr")
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
        raise RestoreDrillError("database identity query returned invalid JSON") from exc
    if not isinstance(value, dict) or set(value) != {
        "database",
        "database_oid",
        "schema_exists",
        "server_version_num",
        "system_identifier",
        "user",
    }:
        raise RestoreDrillError("database identity query returned an invalid identity")
    value.update(
        {
            "host": host,
            "hostaddr": hostaddr or host,
            "port": str(port),
            "sslmode": query.get("sslmode", "prefer"),
        }
    )
    return value


def _fresh_target_check(database_url: str, *, schema: str) -> None:
    """재사용 DB에서 app 스키마만 지운 상태를 fresh target으로 오인하지 않는다."""

    sql = f"""
SELECT NOT EXISTS (
    SELECT 1
    FROM pg_namespace n
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'public')
)
AND NOT EXISTS (
    SELECT 1
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
)
AND NOT EXISTS (
    SELECT 1
    FROM pg_extension e
    JOIN pg_namespace n ON n.oid = e.extnamespace
    WHERE n.nspname NOT IN ('pg_catalog', 'public')
)
AND to_regnamespace('{schema}') IS NULL
""".strip()
    _require_true(_scalar(database_url, sql), name="fresh disposable target")


def _recreate_disposable_target(
    database_url: str, *, staging_role: str, runtime_role: str
) -> None:
    """인증된 단일 연결에서 endpoint를 확인한 뒤 prefix DB를 재생성한다."""

    try:
        parsed = urlsplit(database_url)
        database_name = parsed.path.removeprefix("/")
    except ValueError as exc:
        raise RestoreDrillError("restore target URL is invalid") from exc
    if _TARGET_DATABASE_RE.fullmatch(database_name) is None:
        raise RestoreDrillError("restore target database is outside the M05 disposable prefix")
    if not _ROLE_RE.fullmatch(staging_role):
        raise RestoreDrillError("restore staging role is invalid")
    if not _ROLE_RE.fullmatch(runtime_role):
        raise RestoreDrillError("restore runtime role is invalid")
    maintenance_url = urlunsplit(parsed._replace(path="/postgres"))
    quoted_database = '"' + database_name.replace('"', '""') + '"'
    quoted_role = '"' + staging_role.replace('"', '""') + '"'
    hostaddr = parsed.query and dict(parse_qsl(parsed.query, keep_blank_values=True)).get(
        "hostaddr", ""
    )
    if not hostaddr:
        raise RestoreDrillError("restore target URL is missing the pinned hostaddr")
    expected_port = str(parsed.port or 5432)
    sql_hostaddr = hostaddr.replace("'", "''")
    sql_role = staging_role.replace("'", "''")
    sql_runtime = runtime_role.replace("'", "''")
    _psql_file(
        maintenance_url,
        f"""
DO $m05$
BEGIN
  IF current_database() <> 'postgres'
     OR current_user <> '{sql_role}'
     OR COALESCE(inet_server_addr()::text, '') <> '{sql_hostaddr}'
     OR inet_server_port()::text <> '{expected_port}'
     OR (pg_control_system()).system_identifier::text = ''
  THEN
    RAISE EXCEPTION 'restore maintenance endpoint identity mismatch';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM pg_roles r
    WHERE r.rolname = '{sql_runtime}'
      AND r.rolcanlogin
      AND NOT r.rolsuper
      AND NOT r.rolcreaterole
      AND NOT r.rolcreatedb
      AND NOT r.rolreplication
      AND NOT r.rolbypassrls
      AND NOT r.rolinherit
      AND NOT EXISTS (SELECT 1 FROM pg_auth_members m WHERE m.member = r.oid)
      AND NOT has_database_privilege(r.rolname, 'postgres', 'CREATE')
      AND NOT has_database_privilege(r.rolname, 'template1', 'CREATE')
      AND NOT has_schema_privilege(r.rolname, 'public', 'CREATE')
  ) THEN
    RAISE EXCEPTION 'restore runtime role has direct database or schema creation authority';
  END IF;
END
$m05$;
DROP DATABASE IF EXISTS {quoted_database} WITH (FORCE);
CREATE DATABASE {quoted_database} OWNER {quoted_role};
        """,
        check=True,
    )


def _identity_key(identity: dict[str, object]) -> tuple[object, ...]:
    return (
        identity["database"],
        identity["database_oid"],
        identity["system_identifier"],
        identity["hostaddr"],
        identity["port"],
        identity["sslmode"],
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
    if (
        stat.S_IMODE(metadata.st_mode) != 0o700
        and os.environ.get("PINVI_M05_RESTORE_TEST_MODE") != "1"
    ):
        raise RestoreDrillError("restore evidence parent must be mode 0700")
    if require_root_owned and metadata.st_uid != 0:
        raise RestoreDrillError("restore evidence parent must be root-owned")


def _source_revision(root: Path) -> str:
    expected = os.environ.get("PINVI_SOURCE_REVISION", "")
    if not _COMMIT_RE.fullmatch(expected):
        raise RestoreDrillError("restore producer requires a full PINVI_SOURCE_REVISION")
    try:
        top_level = subprocess.run(
            [_tool_path("git"), "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            env=_command_env(),
        ).stdout.strip()
        if Path(top_level).resolve() != root.resolve():
            raise RestoreDrillError("restore producer checkout root is not canonical")
        revision = subprocess.run(
            [_tool_path("git"), "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            env=_command_env(),
        ).stdout.strip()
        status = subprocess.run(
            [
                _tool_path("git"),
                "-C",
                str(root),
                "status",
                "--porcelain",
                "--untracked-files=all",
            ],
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
        raise RestoreDrillError("restore producer source revision could not be verified") from exc
    if not _COMMIT_RE.fullmatch(revision):
        raise RestoreDrillError("restore producer source revision is invalid")
    if os.environ.get("PINVI_M05_RESTORE_TEST_MODE") != "1":
        try:
            request = urllib.request.Request(
                "https://api.github.com/repos/digitie/pinvi/pulls/466",
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "pinvi-m05-restore-drill",
                },
            )
            token = os.environ.get("PINVI_GITHUB_TOKEN", "")
            if token:
                request.add_header("Authorization", f"Bearer {token}")
            with _canonical_github_opener().open(
                request, timeout=20
            ) as response:
                if response.geturl() != request.full_url or response.getcode() != 200:
                    raise RestoreDrillError("restore producer GitHub response origin is not canonical")
                remote_payload = json.loads(response.read())
            remote_revision = remote_payload["head"]["sha"]
            if (
                remote_payload["html_url"] != "https://github.com/digitie/pinvi/pull/466"
                or remote_payload["base"]["repo"]["full_name"] != "digitie/pinvi"
                or remote_revision != revision
            ):
                raise RestoreDrillError("restore producer is not the current canonical M05 PR head")
        except (OSError, urllib.error.URLError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise RestoreDrillError("restore producer GitHub PR head could not be verified") from exc
    return revision


def _run_drill(args: argparse.Namespace) -> int:
    output: Path = args.output
    environment = os.environ.get("PINVI_ENVIRONMENT", "")
    _secure_output_parent(output, require_root_owned=args.require_root_owned)
    if args.require_root_owned and os.environ.get("PINVI_M05_RESTORE_TEST_MODE") == "1":
        raise RestoreDrillError("restore test mode cannot produce root-owned evidence")
    if (
        os.environ.get("PINVI_M05_RESTORE_TEST_MODE") == "1"
        and os.environ.get("PINVI_ENVIRONMENT") != "test"
    ):
        raise RestoreDrillError("restore test mode requires PINVI_ENVIRONMENT=test")
    if args.require_root_owned and environment not in {"staging", "production"}:
        raise RestoreDrillError(
            "root-owned restore evidence requires PINVI_ENVIRONMENT=staging or production"
        )
    if not _SCHEMA_RE.fullmatch(args.schema):
        raise RestoreDrillError("restore schema is invalid")
    if not _ROLE_RE.fullmatch(args.runtime_role):
        raise RestoreDrillError("restore runtime role is invalid")
    if not _ROLE_RE.fullmatch(args.staging_role):
        raise RestoreDrillError("restore staging role is invalid")
    if args.runtime_role == args.staging_role:
        raise RestoreDrillError("restore staging and runtime roles must differ")
    bash_tool = _tool_identity("bash")
    _PINNED_TOOL_PATHS["bash"] = bash_tool["path"]
    psql_tool = _tool_identity("psql")
    _PINNED_TOOL_PATHS["psql"] = psql_tool["path"]
    source_url = _database_url(args.source_database_url_env)
    target_url = _database_url(args.staging_database_url_env)
    runtime_url = _database_url(args.runtime_database_url_env)
    try:
        source_database_name = urlsplit(source_url).path.removeprefix("/")
        target_database_name = urlsplit(target_url).path.removeprefix("/")
    except ValueError as exc:
        raise RestoreDrillError("restore database URL is invalid") from exc
    if source_database_name == target_database_name:
        raise RestoreDrillError("restore source and disposable target databases must differ")
    if os.environ.get("PINVI_M05_RESTORE_TEST_MODE") != "1":
        _recreate_disposable_target(
            target_url,
            staging_role=args.staging_role,
            runtime_role=args.runtime_role,
        )
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
        raise RestoreDrillError("restore target database is outside the M05 disposable prefix")
    if target_identity_pre.get("schema_exists") is not False:
        raise RestoreDrillError("restore target must be a fresh database without the app schema")
    _fresh_target_check(target_url, schema=args.schema)
    _staging_role_check(
        target_url,
        expected_role=args.staging_role,
        runtime_role=args.runtime_role,
    )
    _runtime_role_check(
        runtime_url,
        schema=args.schema,
        expected_role=args.runtime_role,
        require_schema_privileges=False,
    )

    root = Path(__file__).resolve().parents[1]
    backup_script = root / "scripts/backup-db.sh"
    restore_script = root / "scripts/restore-staging-drill.sh"
    for script in (backup_script, restore_script):
        if script.is_symlink() or not script.is_file():
            raise RestoreDrillError("restore runner source is not canonical")
    source_revision = _source_revision(root)
    backup_tool = _tool_identity("pg_dump")
    restore_tool = _tool_identity("pg_restore")

    with tempfile.TemporaryDirectory(prefix="pinvi-m05-restore-", dir=output.parent) as temporary:
        temporary_dir = Path(temporary)
        private_tools = {
            name: _copy_verified_tool(tool, temporary_dir)
            for name, tool in {
                "bash": bash_tool,
                "psql": psql_tool,
                "pg_dump": backup_tool,
                "pg_restore": restore_tool,
            }.items()
        }
        backup_env = _command_env()
        backup_env.update(
            {
                "PINVI_BACKUP_DATABASE_URL": source_url,
                "PINVI_DATABASE_URL": "",
                "PINVI_BACKUP_SCHEMA": args.schema,
                "PINVI_BACKUP_DIR": str(temporary_dir),
                "PINVI_BACKUP_MIN_FREE_BYTES": "0",
                "PINVI_BACKUP_DOCKER_FALLBACK": "0",
                "PINVI_BACKUP_PG_DUMP_BIN": private_tools["pg_dump"]["path"],
                "PINVI_BACKUP_PSQL_BIN": private_tools["psql"]["path"],
                "PINVI_BACKUP_PG_DUMP_SHA256": private_tools["pg_dump"]["sha256"],
                "PINVI_BACKUP_PRIVATE_TOOL_COPY": "1",
            }
        )
        backup = _run([private_tools["bash"]["path"], str(backup_script)], env=backup_env)
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
                "PINVI_RESTORE_DRILL_ROLLBACK_REHEARSAL": "drain",
                "PINVI_RESTORE_PG_RESTORE_BIN": private_tools["pg_restore"]["path"],
                "PINVI_RESTORE_PSQL_BIN": private_tools["psql"]["path"],
                "PINVI_RESTORE_PG_RESTORE_SHA256": private_tools["pg_restore"]["sha256"],
                "PINVI_RESTORE_PSQL_SHA256": private_tools["psql"]["sha256"],
                "PINVI_RESTORE_PRIVATE_TOOL_COPY": "1",
                "PINVI_M05_RESTORE_REQUIRE_TOOL_TRUST": "1",
                "PINVI_RESTORE_REQUIRE_FRESH_SCHEMA": "1",
            }
        )
        if os.environ.get("PINVI_M05_RESTORE_TEST_MODE") != "1":
            restore_env.update(
                {
                    "PINVI_RESTORE_EXPECTED_DATABASE_NAME": str(
                        target_identity_before_restore["database"]
                    ),
                    "PINVI_RESTORE_EXPECTED_DATABASE_OID": str(
                        target_identity_before_restore["database_oid"]
                    ),
                    "PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER": str(
                        target_identity_before_restore["system_identifier"]
                    ),
                    "PINVI_RESTORE_EXPECTED_HOSTADDR": str(
                        target_identity_before_restore["hostaddr"]
                    ),
                    "PINVI_RESTORE_EXPECTED_PORT": str(target_identity_before_restore["port"]),
                }
            )
        restore = _run(
            [private_tools["bash"]["path"], str(restore_script), "run", str(dump)],
            env=restore_env,
        )
        required_markers = [
            "DRILL_EVIDENCE=checksum=verified",
            "DRILL_EVIDENCE=pg_restore_list=ok",
            "DRILL_EVIDENCE=restore_tool_binding=verified",
            "DRILL_EVIDENCE=rollback_rehearsal=drain_failed_schema_unchanged",
            "DRILL_PHASE=complete:success:staging restore drill completed",
            "RESTORE_COMMAND=pg_restore --clean --if-exists --exit-on-error --no-owner --no-privileges",
        ]
        if os.environ.get("PINVI_M05_RESTORE_TEST_MODE") != "1":
            required_markers.append("RESTORE_TARGET_BINDING=verified")
        if any(marker not in restore.stdout for marker in required_markers):
            raise RestoreDrillError("restore staging runner did not produce all required markers")

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
            "backup_tool_path": backup_tool["path"],
            "backup_tool_sha256": backup_tool["sha256"],
            "bash_tool_path": bash_tool["path"],
            "bash_tool_sha256": bash_tool["sha256"],
            "environment": os.environ.get("PINVI_ENVIRONMENT", ""),
            "fresh_target_verified": True,
            "git_tool_path": _tool_path("git"),
            "git_tool_sha256": _sha256(Path(_tool_path("git")).read_bytes()),
            "psql_tool_path": psql_tool["path"],
            "psql_tool_sha256": psql_tool["sha256"],
            "dump_sha256": _sha256(dump.read_bytes()),
            "execution_id": str(uuid4()),
            "no_owner_restore": True,
            "restore_command": (
                "pg_restore --clean --if-exists --exit-on-error --no-owner --no-privileges"
            ),
            "restore_output_sha256": _sha256(execution_output),
            "restore_db_runner_sha256": _sha256((root / "scripts/restore-db.sh").read_bytes()),
            "hotswap_runner_sha256": _sha256(
                (root / "scripts/restore-hotswap.sh").read_bytes()
            ),
            "restore_runner_sha256": _sha256(restore_script.read_bytes()),
            "m05_restore_drill_sha256": _sha256(Path(__file__).read_bytes()),
            "restore_tool_path": restore_tool["path"],
            "restore_tool_sha256": restore_tool["sha256"],
            "tool_trust_manifest_path": os.environ.get(_TOOL_TRUST_MANIFEST_ENV, ""),
            "tool_trust_manifest_sha256": _TOOL_TRUST_MANIFEST_SHA256,
            "runtime_role_verified": True,
            "staging_role_verified": True,
            "runtime_role": args.runtime_role,
            "staging_role": args.staging_role,
            "source_db_identity": source_identity_pre,
            "source_db_identity_after_backup": source_identity_after_backup,
            "target_db_identity_before_restore": target_identity_before_restore,
            "target_db_identity": target_identity,
            "target_recreated": os.environ.get("PINVI_M05_RESTORE_TEST_MODE") != "1",
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
    parser.add_argument("--runtime-role", default=os.environ.get("PINVI_RESTORE_RUNTIME_ROLE", ""))
    parser.add_argument("--staging-role", default=os.environ.get("PINVI_RESTORE_STAGING_ROLE", ""))
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
