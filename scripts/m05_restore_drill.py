#!/usr/bin/env python3
"""M05 복원 증거를 실제 source dump와 fresh target 검증으로 생성한다.

DB URL과 runtime role은 명령행에 넣지 않고 다음 환경변수로만 받는다.

* ``PINVI_RESTORE_SOURCE_DATABASE_URL`` — dump source
* ``PINVI_RESTORE_STAGING_DATABASE_URL`` — owner/migrator target
* ``PINVI_RESTORE_PROVISION_DATABASE_URL`` — root-only disposable target provisioner
* ``PINVI_RESTORE_PROVISIONER_ROLE`` — expected dedicated root-only provisioner role
* ``PINVI_RESTORE_PROVISION_DISABLE_LOGIN`` — target 생성 후 provisioner login 봉인 여부
* ``PINVI_RESTORE_FENCE_DATABASE_URL`` — dedicated target-owner fence login
* ``PINVI_RESTORE_RUNTIME_DATABASE_URL`` — non-owner runtime target login
* ``PINVI_RESTORE_TEMPLATE_DATABASE_URL`` — target-cluster template with x_extension
* ``PINVI_RESTORE_HOTSWAP_DATABASE_URL`` — dedicated schema-owner target login
* ``PINVI_RESTORE_RUNTIME_ROLE`` — runtime login name
* ``PINVI_RESTORE_FENCE_ROLE`` — target-owner fence login name
* ``PINVI_RESTORE_HOTSWAP_ROLE`` — dedicated hotswap executor role

이 도구는 repository의 backup/restore runner를 고정 호출하고, 성공한 실행의
결과만 root-owned evidence JSON으로 봉인한다. stdout/stderr에는 URL을 출력하지 않는다.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import ipaddress
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
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
_DATABASE_RE = re.compile(r"[a-z_][a-z0-9_]{0,62}\Z")
_SAFE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_TOOL_TRUST_MANIFEST_ENV = "PINVI_M05_RESTORE_TOOL_TRUST_MANIFEST"
_TRUSTED_TOOL_NAMES = ("bash", "git", "pg_dump", "pg_restore", "psql")
_TRUSTED_TOOL_DIRECTORIES = (Path("/usr/local/bin"), Path("/usr/bin"), Path("/bin"))
_POSTGRES_TOOL_DIRECTORY_RE = re.compile(r"/usr/lib/postgresql/[0-9]+/bin\Z")
_REQUIRED_TEMPLATE_EXTENSIONS = ("citext", "pgcrypto", "pg_trgm")
_REQUIRED_TEMPLATE_EXTENSIONS_SQL = ", ".join(
    f"'{extension}'" for extension in _REQUIRED_TEMPLATE_EXTENSIONS
)
_POSTGRES_SCHEMES = frozenset({"postgres", "postgresql", "postgresql+asyncpg"})
_ENDPOINT_QUERY_KEYS = frozenset({"host", "hostaddr", "port", "service", "servicefile"})
_PINNED_TOOL_PATHS: dict[str, str] = {}
_TOOL_TRUST_MANIFEST_SHA256 = ""


class RestoreDrillError(ValueError):
    """실제 복원 드릴이 M05 evidence 계약을 충족하지 못했다."""


def _acquire_root_target_lease(database_url: str):
    """root-owned drill의 disposable target을 trusted hotswap과 직렬화한다."""

    module_name = "_pinvi_m05_operation_lease_for_drill"
    module_path = Path(__file__).with_name("m05_operation_lease.py")
    specification = importlib.util.spec_from_file_location(module_name, module_path)
    if specification is None or specification.loader is None:
        raise RestoreDrillError("restore target operation lease is unavailable")
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    try:
        specification.loader.exec_module(module)
        acquire = module.acquire_root_operation_lease
        if not callable(acquire):
            raise RestoreDrillError("restore target operation lease is unavailable")
        lease = acquire(database_url)
        if not hasattr(lease, "__enter__") or not hasattr(lease, "__exit__"):
            raise RestoreDrillError("restore target operation lease is invalid")
        return lease
    except RestoreDrillError:
        raise
    except Exception as exc:
        raise RestoreDrillError("restore target operation lease is unavailable") from exc


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
    # Keep this strict endpoint contract aligned with trusted-backup-entrypoint.py:
    # every root drill endpoint must be bound to one unambiguous server address.
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port or 5432
    except ValueError as exc:
        raise RestoreDrillError(f"{name} is not a valid PostgreSQL URL") from exc
    if (
        parsed.scheme not in _POSTGRES_SCHEMES
        or not parsed.netloc
        or hostname is None
        or not parsed.path.startswith("/")
        or parsed.path == "/"
        or parsed.fragment
    ):
        raise RestoreDrillError(f"{name} is not a canonical PostgreSQL URL")
    query = parse_qsl(parsed.query, keep_blank_values=True)
    names = [key for key, _ in query]
    if any(not key for key in names) or len(set(names)) != len(names):
        raise RestoreDrillError(f"{name} query is ambiguous")
    if _ENDPOINT_QUERY_KEYS.intersection(names):
        raise RestoreDrillError(f"{name} must not preconfigure an endpoint override")
    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise RestoreDrillError(f"{name} host could not be resolved") from exc
    resolved_addresses: set[str] = set()
    for record in addresses:
        sockaddr = record[4]
        if not sockaddr or not isinstance(sockaddr[0], str):
            continue
        try:
            resolved_addresses.add(str(ipaddress.ip_address(sockaddr[0])))
        except ValueError:
            continue
    if len(resolved_addresses) != 1:
        raise RestoreDrillError(f"{name} host must resolve to exactly one address")
    query.append(("hostaddr", resolved_addresses.pop()))
    return urlunsplit(parsed._replace(query=urlencode(query, safe=":")))


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
  AND has_schema_privilege(current_user, 'x_extension', 'USAGE')
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
      WHERE m.member = r.oid OR m.roleid = r.oid
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
  AND NOT r.rolcreatedb
  AND NOT r.rolreplication
  AND NOT r.rolbypassrls
  AND NOT EXISTS (
      SELECT 1 FROM pg_auth_members m
      WHERE m.member = r.oid OR m.roleid = r.oid
  )
FROM pg_roles r
WHERE r.rolname = current_user
""".strip()
    _require_true(_scalar(database_url, sql), name="staging role")


def _fence_role_check(database_url: str, *, expected_role: str) -> None:
    if not _ROLE_RE.fullmatch(expected_role):
        raise RestoreDrillError("restore fence role is invalid")
    sql = f"""
SELECT current_user = '{expected_role}'
  AND r.rolcanlogin
  AND NOT r.rolsuper
  AND NOT r.rolcreaterole
  AND NOT r.rolcreatedb
  AND NOT r.rolreplication
  AND NOT r.rolbypassrls
  AND NOT r.rolinherit
  AND d.datdba = r.oid
  AND NOT EXISTS (
      SELECT 1 FROM pg_auth_members m
      WHERE m.member = r.oid OR m.roleid = r.oid
  )
FROM pg_roles r
JOIN pg_database d ON d.datdba = r.oid
WHERE r.rolname = current_user
  AND d.datname = current_database()
""".strip()
    _require_true(_scalar(database_url, sql), name="database fence role")


def _provisioner_role_check(
    database_url: str,
    *,
    expected_role: str,
    staging_role: str,
    fence_role: str,
    runtime_role: str,
    hotswap_role: str,
) -> None:
    """Disposable DB owner assignment은 root-only superuser one-shot으로만 수행한다."""

    roles = (staging_role, fence_role, runtime_role, hotswap_role)
    if any(_ROLE_RE.fullmatch(role) is None for role in (expected_role, *roles)):
        raise RestoreDrillError("restore provisioner role binding is invalid")
    quoted_roles = ", ".join(f"'{role}'" for role in roles)
    sql = f"""
SELECT current_database() = 'postgres'
  AND current_user = '{expected_role}'
  AND r.rolcanlogin
  AND r.rolsuper
  AND current_user <> ALL(ARRAY[{quoted_roles}])
FROM pg_roles r
WHERE r.rolname = current_user
""".strip()
    _require_true(
        _scalar(database_url, sql),
        name="dedicated root-only restore provisioner",
    )


def _hotswap_role_check(
    database_url: str,
    *,
    schema: str,
    expected_role: str,
    require_schema_owner: bool,
) -> None:
    if not _ROLE_RE.fullmatch(expected_role):
        raise RestoreDrillError("restore hotswap role is invalid")
    schema_check = (
        f"""
  AND EXISTS (
      SELECT 1 FROM pg_namespace n
      WHERE n.nspname = '{schema}' AND n.nspowner = r.oid
  )"""
        if require_schema_owner
        else f"""
  AND NOT EXISTS (
      SELECT 1 FROM pg_namespace n WHERE n.nspname = '{schema}'
  )"""
    )
    sql = f"""
SELECT current_user = '{expected_role}'
  AND r.rolcanlogin
  AND NOT r.rolsuper
  AND NOT r.rolcreaterole
  AND NOT r.rolcreatedb
  AND NOT r.rolreplication
  AND NOT r.rolbypassrls
  AND r.rolinherit
  AND has_database_privilege(current_user, current_database(), 'CREATE')
  AND has_schema_privilege(current_user, 'x_extension', 'USAGE')
  AND NOT has_schema_privilege(current_user, 'x_extension', 'CREATE')
  AND EXISTS (
      SELECT 1 FROM pg_auth_members m
      WHERE m.member = r.oid AND m.roleid = to_regrole('pg_signal_backend')
  )
  AND NOT EXISTS (
      SELECT 1 FROM pg_auth_members m
      WHERE m.member = r.oid AND m.roleid <> to_regrole('pg_signal_backend')
  )
  AND NOT EXISTS (
      SELECT 1 FROM pg_auth_members m
      WHERE m.roleid = r.oid
  )
{schema_check}
FROM pg_roles r
WHERE r.rolname = current_user
""".strip()
    _require_true(_scalar(database_url, sql), name="restore hotswap role")


def _trigger_check(database_url: str, *, schema: str) -> None:
    sql = f"""
SELECT count(*) = 6
FROM (VALUES
  ('ktm_feature_reference_reconciliation_delivery_attempts', left('trg_ktm_feature_reference_reconciliation_delivery_attempts_append_only', 63), 31),
  ('ktm_feature_reference_reconciliation_delivery_attempts', left('trg_ktm_feature_reference_reconciliation_delivery_attempts_truncate_append_only', 63), 34),
  ('ktm_feature_reference_reconciliation_applied_receipts', left('trg_ktm_feature_reference_reconciliation_applied_receipts_append_only', 63), 31),
  ('ktm_feature_reference_reconciliation_applied_receipts', left('trg_ktm_feature_reference_reconciliation_applied_receipts_truncate_append_only', 63), 34),
  ('ktm_feature_reference_reconciliation_impacts', left('trg_ktm_feature_reference_reconciliation_impacts_append_only', 63), 31),
  ('ktm_feature_reference_reconciliation_impacts', left('trg_ktm_feature_reference_reconciliation_impacts_truncate_append_only', 63), 34)
) expected(table_name, trigger_name, trigger_type)
WHERE EXISTS (
  SELECT 1
  FROM pg_trigger t
  JOIN pg_class c ON c.oid = t.tgrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_proc p ON p.oid = t.tgfoid
  JOIN pg_namespace pn ON pn.oid = p.pronamespace
  WHERE n.nspname = '{schema}'
    AND c.relname = expected.table_name
    AND t.tgname = expected.trigger_name
    AND t.tgtype = expected.trigger_type
    AND t.tgenabled = 'A'
    AND NOT t.tgisinternal
    AND p.proname = 'guard_ktm_feature_reference_reconciliation_append_only'
    AND pn.nspname = '{schema}'
    AND NOT p.prosecdef
)
""".strip()
    _require_true(_scalar(database_url, sql), name="always-enabled M05 triggers")


def _admin_audit_contract_check(database_url: str, *, schema: str) -> None:
    """Schema-swap reflection이 의존하는 admin audit ledger를 이름만으로 신뢰하지 않는다."""

    sql = f"""
SELECT
  to_regclass('{schema}.admin_audit_log') IS NOT NULL
  AND (
    SELECT count(*)
    FROM (VALUES
      ('log_id', 'bigint', true),
      ('actor_user_id', 'uuid', true),
      ('action', 'character varying(64)', true),
      ('resource_type', 'character varying(64)', true),
      ('resource_id', 'character varying(128)', false),
      ('before_state', 'jsonb', false),
      ('after_state', 'jsonb', false),
      ('access_reason', 'text', false),
      ('target_pii_fields', 'character varying(64)[]', false),
      ('ip_hash', 'character varying(64)', true),
      ('user_agent', 'character varying(512)', false),
      ('request_id', 'uuid', true),
      ('prev_hash', 'character varying(64)', true),
      ('content_hash', 'character varying(64)', true),
      ('occurred_at', 'timestamp with time zone', true)
    ) expected(column_name, type_name, not_null)
    WHERE EXISTS (
      SELECT 1
      FROM pg_attribute attribute
      JOIN pg_class relation ON relation.oid = attribute.attrelid
      JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
      WHERE namespace.nspname = '{schema}'
        AND relation.relname = 'admin_audit_log'
        AND attribute.attname = expected.column_name
        AND NOT attribute.attisdropped
        AND attribute.attnotnull = expected.not_null
        AND format_type(attribute.atttypid, attribute.atttypmod) = expected.type_name
    )
  ) = 15
  AND EXISTS (
    SELECT 1
    FROM pg_constraint constraint_row
    WHERE constraint_row.conrelid = '{schema}.admin_audit_log'::regclass
      AND constraint_row.contype = 'p'
      AND constraint_row.conkey = ARRAY[
        (SELECT attribute.attnum
         FROM pg_attribute attribute
         WHERE attribute.attrelid = '{schema}.admin_audit_log'::regclass
           AND attribute.attname = 'log_id'
           AND NOT attribute.attisdropped)
      ]::smallint[]
  )
  AND EXISTS (
    SELECT 1
    FROM pg_constraint constraint_row
    WHERE constraint_row.conrelid = '{schema}.admin_audit_log'::regclass
      AND constraint_row.contype = 'u'
      AND constraint_row.conkey = ARRAY[
        (SELECT attribute.attnum
         FROM pg_attribute attribute
         WHERE attribute.attrelid = '{schema}.admin_audit_log'::regclass
           AND attribute.attname = 'prev_hash'
           AND NOT attribute.attisdropped)
      ]::smallint[]
  )
  AND EXISTS (
    SELECT 1
    FROM pg_attrdef default_value
    WHERE default_value.adrelid = '{schema}.admin_audit_log'::regclass
      AND default_value.adnum = (
        SELECT attribute.attnum
        FROM pg_attribute attribute
        WHERE attribute.attrelid = '{schema}.admin_audit_log'::regclass
          AND attribute.attname = 'log_id'
          AND NOT attribute.attisdropped
      )
      AND pg_get_expr(default_value.adbin, default_value.adrelid) LIKE 'nextval(%'
  )
  AND EXISTS (
    SELECT 1
    FROM pg_constraint constraint_row
    WHERE constraint_row.conrelid = '{schema}.admin_audit_log'::regclass
      AND constraint_row.contype = 'f'
      AND constraint_row.confrelid = '{schema}.users'::regclass
      AND constraint_row.confdeltype = 'r'
      AND constraint_row.conkey = ARRAY[
        (SELECT attribute.attnum
         FROM pg_attribute attribute
         WHERE attribute.attrelid = '{schema}.admin_audit_log'::regclass
           AND attribute.attname = 'actor_user_id'
           AND NOT attribute.attisdropped)
      ]::smallint[]
      AND constraint_row.confkey = ARRAY[
        (SELECT attribute.attnum
         FROM pg_attribute attribute
         WHERE attribute.attrelid = '{schema}.users'::regclass
           AND attribute.attname = 'user_id'
           AND NOT attribute.attisdropped)
      ]::smallint[]
  )
  AND (
    SELECT count(*)
    FROM (VALUES
      ('trg_admin_audit_log_append_only', 31),
      ('trg_admin_audit_log_truncate_append_only', 34)
    ) expected(trigger_name, trigger_type)
    WHERE EXISTS (
      SELECT 1
      FROM pg_trigger trigger
      JOIN pg_class relation ON relation.oid = trigger.tgrelid
      JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
      JOIN pg_proc procedure ON procedure.oid = trigger.tgfoid
      JOIN pg_namespace procedure_namespace ON procedure_namespace.oid = procedure.pronamespace
      WHERE namespace.nspname = '{schema}'
        AND relation.relname = 'admin_audit_log'
        AND trigger.tgname = expected.trigger_name
        AND trigger.tgtype = expected.trigger_type
        AND trigger.tgenabled = 'A'
        AND NOT trigger.tgisinternal
        AND procedure.proname = 'guard_admin_audit_log_append_only'
        AND procedure_namespace.nspname = '{schema}'
        AND NOT procedure.prosecdef
        AND procedure.proconfig = ARRAY['search_path=pg_catalog']
        AND regexp_replace(btrim(procedure.prosrc), '[[:space:]]+', ' ', 'g') =
          'BEGIN IF TG_OP = ''INSERT'' THEN RETURN NEW; END IF; RAISE EXCEPTION ''% is append-only'', TG_TABLE_SCHEMA || ''.'' || TG_TABLE_NAME USING ERRCODE = ''55000''; END;'
    )
  ) = 2
  AND NOT EXISTS (
    WITH ordered AS (
      SELECT log_id, prev_hash, content_hash,
             lag(content_hash) OVER (ORDER BY log_id) AS previous_content_hash
      FROM {schema}.admin_audit_log
    )
    SELECT 1
    FROM ordered
    WHERE prev_hash !~ '^[0-9a-f]{{64}}$'
       OR content_hash !~ '^[0-9a-f]{{64}}$'
       OR prev_hash <> COALESCE(previous_content_hash, repeat('0', 64))
  )
""".strip()
    _require_true(_scalar(database_url, sql), name="admin audit runtime contract")


def _admin_audit_guard_is_enforced(database_url: str, *, schema: str) -> None:
    """A catalog-shaped audit guard must reject row and statement mutations."""

    sql = f"""
DO $m05$
DECLARE
  audit_row_ctid tid;
BEGIN
  BEGIN
    TRUNCATE TABLE {schema}.admin_audit_log;
    RAISE EXCEPTION 'admin audit append-only trigger unexpectedly allowed TRUNCATE';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%{schema}.admin_audit_log is append-only%' THEN
        RAISE EXCEPTION 'admin audit append-only trigger returned an unexpected TRUNCATE diagnostic';
      END IF;
  END;
  SELECT ctid
    INTO audit_row_ctid
  FROM {schema}.admin_audit_log
  ORDER BY log_id
  LIMIT 1;
  IF audit_row_ctid IS NOT NULL THEN
    BEGIN
      UPDATE {schema}.admin_audit_log
      SET action = 'm05-audit-guard-probe'
      WHERE ctid = audit_row_ctid;
      RAISE EXCEPTION 'admin audit append-only trigger unexpectedly allowed UPDATE';
    EXCEPTION
      WHEN SQLSTATE '55000' THEN
        IF SQLERRM NOT ILIKE '%{schema}.admin_audit_log is append-only%' THEN
          RAISE EXCEPTION 'admin audit append-only trigger returned an unexpected UPDATE diagnostic';
        END IF;
    END;
    BEGIN
      DELETE FROM {schema}.admin_audit_log
      WHERE ctid = audit_row_ctid;
      RAISE EXCEPTION 'admin audit append-only trigger unexpectedly allowed DELETE';
    EXCEPTION
      WHEN SQLSTATE '55000' THEN
        IF SQLERRM NOT ILIKE '%{schema}.admin_audit_log is append-only%' THEN
          RAISE EXCEPTION 'admin audit append-only trigger returned an unexpected DELETE diagnostic';
        END IF;
    END;
  END IF;
END
$m05$;
""".strip()
    result = _scalar(database_url, sql, check=False)
    if result.returncode != 0:
        raise RestoreDrillError("admin audit append-only semantic probe failed")


def _trigger_guard_is_enforced(database_url: str, *, schema: str) -> None:
    """Catalog metadata alone cannot prove that the guard body blocks every mutation."""

    sql = f"""
DO $m05$
DECLARE
  probe_nonce text := md5(
    clock_timestamp()::text || ':' || txid_current()::text || ':' || pg_backend_pid()::text
  );
  probe_sequence bigint;
  delivery_update_event uuid := md5(probe_nonce || ':delivery-update')::uuid;
  delivery_delete_event uuid := md5(probe_nonce || ':delivery-delete')::uuid;
  receipt_update_event uuid := md5(probe_nonce || ':receipt-update')::uuid;
  receipt_delete_event uuid := md5(probe_nonce || ':receipt-delete')::uuid;
  impact_update_event uuid := md5(probe_nonce || ':impact-update')::uuid;
  impact_delete_event uuid := md5(probe_nonce || ':impact-delete')::uuid;
BEGIN
  -- Do not probe the receipt table with a standalone TRUNCATE: the canonical
  -- 0060 topology makes impacts reference it with RESTRICT.  Per-table DML
  -- probes avoid that false failure; direct delivery/impact TRUNCATE probes
  -- and a receipt-first paired probe cover the statement triggers.  Every
  -- exception block rolls its allowed disposable INSERT back with 55000. The
  -- receipt table has a globally unique event_sequence, so start above its
  -- real high-water mark and derive each probe key/hash from this execution's
  -- nonce.
  SELECT COALESCE(max(event_sequence), 0)
  INTO probe_sequence
  FROM {schema}.ktm_feature_reference_reconciliation_applied_receipts;
  IF probe_sequence > 9223372036854775803 THEN
    RAISE EXCEPTION 'M05 append-only probe cannot allocate an event sequence';
  END IF;
  BEGIN
    INSERT INTO {schema}.ktm_feature_reference_reconciliation_delivery_attempts (
      event_id, attempt_sequence, event_sequence, event_sha256, status,
      block_fingerprint_sha256, observation_root_sha256
    ) VALUES (
      delivery_update_event, 1, probe_sequence + 1,
      md5(probe_nonce || ':delivery-update-event-sha-a') ||
        md5(probe_nonce || ':delivery-update-event-sha-b'),
      'applied', NULL,
      md5(probe_nonce || ':delivery-update-observation-a') ||
        md5(probe_nonce || ':delivery-update-observation-b')
    );
    UPDATE {schema}.ktm_feature_reference_reconciliation_delivery_attempts
    SET status = status
    WHERE event_id = delivery_update_event AND attempt_sequence = 1;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed UPDATE on delivery attempts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger returned an unexpected delivery-attempt UPDATE diagnostic';
      END IF;
  END;
  BEGIN
    INSERT INTO {schema}.ktm_feature_reference_reconciliation_delivery_attempts (
      event_id, attempt_sequence, event_sequence, event_sha256, status,
      block_fingerprint_sha256, observation_root_sha256
    ) VALUES (
      delivery_delete_event, 1, probe_sequence + 2,
      md5(probe_nonce || ':delivery-delete-event-sha-a') ||
        md5(probe_nonce || ':delivery-delete-event-sha-b'),
      'applied', NULL,
      md5(probe_nonce || ':delivery-delete-observation-a') ||
        md5(probe_nonce || ':delivery-delete-observation-b')
    );
    DELETE FROM {schema}.ktm_feature_reference_reconciliation_delivery_attempts
    WHERE event_id = delivery_delete_event AND attempt_sequence = 1;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed DELETE on delivery attempts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger returned an unexpected delivery-attempt DELETE diagnostic';
      END IF;
  END;
  BEGIN
    INSERT INTO {schema}.ktm_feature_reference_reconciliation_applied_receipts (
      event_id, event_sequence, event_sha256, action, old_feature_id,
      old_feature_uuid, replacement_feature_id, replacement_feature_uuid,
      impact_root_sha256, impact_count, receipt_sha256
    ) VALUES (
      receipt_update_event, probe_sequence + 1,
      md5(probe_nonce || ':receipt-update-event-sha-a') ||
        md5(probe_nonce || ':receipt-update-event-sha-b'),
      'detach', concat('m05-guard-probe-', probe_nonce),
      md5(probe_nonce || ':receipt-update-old-feature')::uuid, NULL, NULL,
      md5(probe_nonce || ':receipt-update-impact-root-a') ||
        md5(probe_nonce || ':receipt-update-impact-root-b'),
      0,
      md5(probe_nonce || ':receipt-update-receipt-sha-a') ||
        md5(probe_nonce || ':receipt-update-receipt-sha-b')
    );
    UPDATE {schema}.ktm_feature_reference_reconciliation_applied_receipts
    SET action = action
    WHERE event_id = receipt_update_event;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed UPDATE on applied receipts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger returned an unexpected applied-receipt UPDATE diagnostic';
      END IF;
  END;
  BEGIN
    INSERT INTO {schema}.ktm_feature_reference_reconciliation_applied_receipts (
      event_id, event_sequence, event_sha256, action, old_feature_id,
      old_feature_uuid, replacement_feature_id, replacement_feature_uuid,
      impact_root_sha256, impact_count, receipt_sha256
    ) VALUES (
      receipt_delete_event, probe_sequence + 2,
      md5(probe_nonce || ':receipt-delete-event-sha-a') ||
        md5(probe_nonce || ':receipt-delete-event-sha-b'),
      'detach', concat('m05-guard-probe-', probe_nonce),
      md5(probe_nonce || ':receipt-delete-old-feature')::uuid, NULL, NULL,
      md5(probe_nonce || ':receipt-delete-impact-root-a') ||
        md5(probe_nonce || ':receipt-delete-impact-root-b'),
      0,
      md5(probe_nonce || ':receipt-delete-receipt-sha-a') ||
        md5(probe_nonce || ':receipt-delete-receipt-sha-b')
    );
    DELETE FROM {schema}.ktm_feature_reference_reconciliation_applied_receipts
    WHERE event_id = receipt_delete_event;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed DELETE on applied receipts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger returned an unexpected applied-receipt DELETE diagnostic';
      END IF;
  END;
  BEGIN
    INSERT INTO {schema}.ktm_feature_reference_reconciliation_applied_receipts (
      event_id, event_sequence, event_sha256, action, old_feature_id,
      old_feature_uuid, replacement_feature_id, replacement_feature_uuid,
      impact_root_sha256, impact_count, receipt_sha256
    ) VALUES (
      impact_update_event, probe_sequence + 3,
      md5(probe_nonce || ':impact-update-event-sha-a') ||
        md5(probe_nonce || ':impact-update-event-sha-b'),
      'detach', concat('m05-guard-probe-', probe_nonce),
      md5(probe_nonce || ':impact-update-old-feature')::uuid, NULL, NULL,
      md5(probe_nonce || ':impact-update-root-a') ||
        md5(probe_nonce || ':impact-update-root-b'),
      1,
      md5(probe_nonce || ':impact-update-receipt-sha-a') ||
        md5(probe_nonce || ':impact-update-receipt-sha-b')
    );
    INSERT INTO {schema}.ktm_feature_reference_reconciliation_impacts (
      event_id, impact_index, target_relation, target_id, old_feature_id,
      old_feature_uuid, replacement_feature_id, replacement_feature_uuid, outcome
    ) VALUES (
      impact_update_event, 0, 'trip_day_pois',
      md5(probe_nonce || ':impact-update-target')::uuid,
      concat('m05-guard-probe-', probe_nonce),
      md5(probe_nonce || ':impact-update-old-feature')::uuid, NULL, NULL, 'detach'
    );
    UPDATE {schema}.ktm_feature_reference_reconciliation_impacts
    SET outcome = outcome
    WHERE event_id = impact_update_event AND impact_index = 0;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed UPDATE on impacts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger returned an unexpected impact UPDATE diagnostic';
      END IF;
  END;
  BEGIN
    INSERT INTO {schema}.ktm_feature_reference_reconciliation_applied_receipts (
      event_id, event_sequence, event_sha256, action, old_feature_id,
      old_feature_uuid, replacement_feature_id, replacement_feature_uuid,
      impact_root_sha256, impact_count, receipt_sha256
    ) VALUES (
      impact_delete_event, probe_sequence + 4,
      md5(probe_nonce || ':impact-delete-event-sha-a') ||
        md5(probe_nonce || ':impact-delete-event-sha-b'),
      'detach', concat('m05-guard-probe-', probe_nonce),
      md5(probe_nonce || ':impact-delete-old-feature')::uuid, NULL, NULL,
      md5(probe_nonce || ':impact-delete-root-a') ||
        md5(probe_nonce || ':impact-delete-root-b'),
      1,
      md5(probe_nonce || ':impact-delete-receipt-sha-a') ||
        md5(probe_nonce || ':impact-delete-receipt-sha-b')
    );
    INSERT INTO {schema}.ktm_feature_reference_reconciliation_impacts (
      event_id, impact_index, target_relation, target_id, old_feature_id,
      old_feature_uuid, replacement_feature_id, replacement_feature_uuid, outcome
    ) VALUES (
      impact_delete_event, 0, 'trip_day_pois',
      md5(probe_nonce || ':impact-delete-target')::uuid,
      concat('m05-guard-probe-', probe_nonce),
      md5(probe_nonce || ':impact-delete-old-feature')::uuid, NULL, NULL, 'detach'
    );
    DELETE FROM {schema}.ktm_feature_reference_reconciliation_impacts
    WHERE event_id = impact_delete_event AND impact_index = 0;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed DELETE on impacts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger returned an unexpected impact DELETE diagnostic';
      END IF;
  END;
  BEGIN
    TRUNCATE TABLE {schema}.ktm_feature_reference_reconciliation_delivery_attempts;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed TRUNCATE on delivery attempts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%ktm_feature_reference_reconciliation_delivery_attempts is append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger returned an unexpected delivery-attempt TRUNCATE diagnostic';
      END IF;
  END;
  BEGIN
    TRUNCATE TABLE {schema}.ktm_feature_reference_reconciliation_impacts;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed TRUNCATE on impacts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%ktm_feature_reference_reconciliation_impacts is append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger returned an unexpected impact TRUNCATE diagnostic';
      END IF;
  END;
  BEGIN
    TRUNCATE TABLE {schema}.ktm_feature_reference_reconciliation_applied_receipts,
      {schema}.ktm_feature_reference_reconciliation_impacts;
    RAISE EXCEPTION 'M05 append-only trigger unexpectedly allowed TRUNCATE on applied receipts';
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      IF SQLERRM NOT ILIKE '%ktm_feature_reference_reconciliation_applied_receipts is append-only%' THEN
        RAISE EXCEPTION 'M05 append-only trigger did not reject the receipt TRUNCATE first';
      END IF;
  END;
END
$m05$;
""".strip()
    result = _scalar(database_url, sql, check=False)
    if result.returncode != 0:
        raise RestoreDrillError("M05 append-only trigger semantic probe failed")


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
    WHERE n.nspname NOT IN ('pg_catalog', 'pg_toast', 'information_schema', 'public', 'x_extension')
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
    WHERE n.nspname NOT IN ('pg_catalog', 'public', 'x_extension')
)
AND to_regnamespace('x_extension') IS NOT NULL
AND (
    SELECT count(*)
    FROM pg_extension e
    JOIN pg_namespace n ON n.oid = e.extnamespace
    WHERE n.nspname = 'x_extension'
      AND e.extname = ANY(ARRAY[{_REQUIRED_TEMPLATE_EXTENSIONS_SQL}])
) = 3
AND to_regnamespace('{schema}') IS NULL
""".strip()
    _require_true(_scalar(database_url, sql), name="fresh disposable target")


def _recreate_disposable_target(
    database_url: str,
    *,
    staging_role: str,
    provision_url: str,
    provisioner_role: str,
    disable_provisioner_login: bool,
    fence_role: str,
    fence_url: str,
    runtime_role: str,
    hotswap_role: str,
    hotswap_url: str,
    template_url: str,
) -> None:
    """x_extension이 준비된 target template에서 prefix DB를 재생성한다."""

    try:
        parsed = urlsplit(database_url)
        provision_parsed = urlsplit(provision_url)
        fence_parsed = urlsplit(fence_url)
        hotswap_parsed = urlsplit(hotswap_url)
        template_parsed = urlsplit(template_url)
        database_name = parsed.path.removeprefix("/")
        provision_database_name = provision_parsed.path.removeprefix("/")
        fence_database_name = fence_parsed.path.removeprefix("/")
        hotswap_database_name = hotswap_parsed.path.removeprefix("/")
        template_name = template_parsed.path.removeprefix("/")
    except ValueError as exc:
        raise RestoreDrillError("restore target URL is invalid") from exc
    if _TARGET_DATABASE_RE.fullmatch(database_name) is None:
        raise RestoreDrillError("restore target database is outside the M05 disposable prefix")
    if _DATABASE_RE.fullmatch(template_name) is None or template_name == database_name:
        raise RestoreDrillError("restore target template database is invalid")
    if provision_database_name != "postgres":
        raise RestoreDrillError("restore provisioner URL must use the postgres maintenance database")
    if not _ROLE_RE.fullmatch(staging_role):
        raise RestoreDrillError("restore staging role is invalid")
    if not _ROLE_RE.fullmatch(provisioner_role):
        raise RestoreDrillError("restore provisioner role is invalid")
    if not _ROLE_RE.fullmatch(fence_role):
        raise RestoreDrillError("restore fence role is invalid")
    if not _ROLE_RE.fullmatch(runtime_role):
        raise RestoreDrillError("restore runtime role is invalid")
    if not _ROLE_RE.fullmatch(hotswap_role):
        raise RestoreDrillError("restore hotswap role is invalid")
    if hotswap_database_name != database_name:
        raise RestoreDrillError("restore hotswap URL must target the disposable database")
    if fence_database_name != database_name:
        raise RestoreDrillError("restore fence URL must target the disposable database")
    quoted_database = '"' + database_name.replace('"', '""') + '"'
    quoted_role = '"' + staging_role.replace('"', '""') + '"'
    quoted_fence_role = '"' + fence_role.replace('"', '""') + '"'
    quoted_hotswap_role = '"' + hotswap_role.replace('"', '""') + '"'
    quoted_template = '"' + template_name.replace('"', '""') + '"'
    hostaddr = parsed.query and dict(parse_qsl(parsed.query, keep_blank_values=True)).get(
        "hostaddr", ""
    )
    template_hostaddr = template_parsed.query and dict(
        parse_qsl(template_parsed.query, keep_blank_values=True)
    ).get("hostaddr", "")
    hotswap_hostaddr = hotswap_parsed.query and dict(
        parse_qsl(hotswap_parsed.query, keep_blank_values=True)
    ).get("hostaddr", "")
    provision_hostaddr = provision_parsed.query and dict(
        parse_qsl(provision_parsed.query, keep_blank_values=True)
    ).get("hostaddr", "")
    fence_hostaddr = fence_parsed.query and dict(
        parse_qsl(fence_parsed.query, keep_blank_values=True)
    ).get("hostaddr", "")
    expected_port = str(parsed.port or 5432)
    hotswap_port = str(hotswap_parsed.port or 5432)
    template_port = str(template_parsed.port or 5432)
    fence_port = str(fence_parsed.port or 5432)
    provision_port = str(provision_parsed.port or 5432)
    if (
        not hostaddr
        or not template_hostaddr
        or not hotswap_hostaddr
        or not fence_hostaddr
        or not provision_hostaddr
    ):
        raise RestoreDrillError(
            "restore target, provisioner, fence, hotswap, and template URLs need pinned hostaddr values"
        )
    if (
        hostaddr != template_hostaddr
        or hostaddr != hotswap_hostaddr
        or hostaddr != fence_hostaddr
        or hostaddr != provision_hostaddr
        or expected_port != template_port
        or expected_port != hotswap_port
        or expected_port != fence_port
        or expected_port != provision_port
    ):
        raise RestoreDrillError(
            "restore target, provisioner, fence, hotswap, and template must use the same PostgreSQL endpoint"
        )
    target_system_identifier = _scalar(
        provision_url,
        "SELECT (pg_control_system()).system_identifier::text",
    ).stdout.strip()
    if not re.fullmatch(r"[0-9]+", target_system_identifier):
        raise RestoreDrillError("restore target system identifier is invalid")
    _provisioner_role_check(
        provision_url,
        expected_role=provisioner_role,
        staging_role=staging_role,
        fence_role=fence_role,
        runtime_role=runtime_role,
        hotswap_role=hotswap_role,
    )
    sql_hostaddr = hostaddr.replace("'", "''")
    sql_role = staging_role.replace("'", "''")
    sql_fence = fence_role.replace("'", "''")
    sql_runtime = runtime_role.replace("'", "''")
    sql_hotswap = hotswap_role.replace("'", "''")
    sql_provisioner = provisioner_role.replace("'", "''")
    sql_template = template_name.replace("'", "''")
    template_check = _scalar(
        template_url,
        f"""
SELECT current_database() = '{sql_template}'
  AND current_user = '{sql_role}'
  AND COALESCE(host(inet_server_addr()), '') = '{sql_hostaddr}'
  AND inet_server_port()::text = '{expected_port}'
  AND (pg_control_system()).system_identifier::text = '{target_system_identifier}'
  AND to_regnamespace('app') IS NULL
  AND to_regnamespace('x_extension') IS NOT NULL
  AND NOT has_database_privilege('{sql_runtime}', current_database(), 'CREATE')
  AND has_schema_privilege('{sql_runtime}', 'x_extension', 'USAGE')
  AND NOT has_schema_privilege('{sql_runtime}', 'public', 'CREATE')
  AND has_database_privilege('{sql_hotswap}', current_database(), 'CREATE')
  AND has_schema_privilege('{sql_hotswap}', 'x_extension', 'USAGE')
  AND NOT has_schema_privilege('{sql_hotswap}', 'x_extension', 'CREATE')
  AND NOT EXISTS (
    SELECT 1
    FROM pg_default_acl d
    JOIN pg_roles r ON r.oid = d.defaclrole
    WHERE r.rolname = '{sql_hotswap}'
      AND d.defaclnamespace = 0
  )
  AND EXISTS (
    SELECT 1
    FROM pg_roles r
    WHERE r.rolname = '{sql_fence}'
      AND r.rolcanlogin
      AND NOT r.rolsuper
      AND NOT r.rolcreaterole
      AND NOT r.rolcreatedb
      AND NOT r.rolreplication
      AND NOT r.rolbypassrls
      AND NOT r.rolinherit
      AND NOT EXISTS (
        SELECT 1 FROM pg_auth_members m
        WHERE m.member = r.oid OR m.roleid = r.oid
      )
  )
  AND EXISTS (
    SELECT 1
    FROM pg_roles r
    WHERE r.rolname = '{sql_hotswap}'
      AND r.rolcanlogin
      AND NOT r.rolsuper
      AND NOT r.rolcreaterole
      AND NOT r.rolcreatedb
      AND NOT r.rolreplication
      AND NOT r.rolbypassrls
      AND r.rolinherit
      AND EXISTS (
        SELECT 1 FROM pg_auth_members m
        WHERE m.member = r.oid AND m.roleid = to_regrole('pg_signal_backend')
      )
      AND NOT EXISTS (
        SELECT 1 FROM pg_auth_members m
        WHERE m.member = r.oid AND m.roleid <> to_regrole('pg_signal_backend')
      )
      AND NOT EXISTS (
        SELECT 1 FROM pg_auth_members m
        WHERE m.roleid = r.oid
      )
  )
  AND (
    SELECT count(*)
    FROM pg_extension e
    JOIN pg_namespace n ON n.oid = e.extnamespace
    WHERE n.nspname = 'x_extension'
      AND e.extname = ANY(ARRAY[{_REQUIRED_TEMPLATE_EXTENSIONS_SQL}])
  ) = 3
""".strip(),
    )
    _require_true(template_check, name="restore target template")
    disable_provisioner_sql = (
        f'ALTER ROLE "{provisioner_role}" NOLOGIN;'
        if disable_provisioner_login
        else ""
    )
    postcondition_sql = f"""
SELECT EXISTS (
  SELECT 1
  FROM pg_database d
  JOIN pg_roles fence_role ON fence_role.oid = d.datdba
  WHERE d.datname = '{database_name}'
    AND fence_role.rolname = '{sql_fence}'
    AND fence_role.rolcanlogin
    AND NOT fence_role.rolsuper
    AND NOT fence_role.rolcreaterole
    AND NOT fence_role.rolcreatedb
    AND NOT fence_role.rolreplication
    AND NOT fence_role.rolbypassrls
    AND NOT fence_role.rolinherit
    AND NOT EXISTS (
      SELECT 1
      FROM pg_auth_members m
      WHERE m.member = fence_role.oid OR m.roleid = fence_role.oid
    )
)
AND NOT EXISTS (
  SELECT 1
  FROM pg_default_acl d
  JOIN pg_roles r ON r.oid = d.defaclrole
  WHERE r.rolname = '{sql_hotswap}'
    AND d.defaclnamespace = 0
)
AND EXISTS (
  SELECT 1
  FROM pg_roles r
  WHERE r.rolname = '{sql_provisioner}'
    AND r.rolcanlogin = {str(not disable_provisioner_login).lower()}
)
""".strip()
    _psql_file(
        provision_url,
        f"""
SELECT pg_advisory_lock(1414679892, 1213421392);
DO $m05$
BEGIN
  IF current_database() <> 'postgres'
     OR COALESCE(host(inet_server_addr()), '') <> '{sql_hostaddr}'
     OR inet_server_port()::text <> '{expected_port}'
     OR (pg_control_system()).system_identifier::text <> '{target_system_identifier}'
  THEN
    RAISE EXCEPTION 'restore maintenance endpoint identity mismatch';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM pg_roles r
    WHERE r.rolname = '{sql_provisioner}'
      AND current_user = '{sql_provisioner}'
      AND r.rolcanlogin
      AND r.rolsuper
  ) THEN
    RAISE EXCEPTION 'restore disposable target provisioner is not the dedicated superuser';
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
      AND NOT EXISTS (
        SELECT 1 FROM pg_auth_members m
        WHERE m.member = r.oid OR m.roleid = r.oid
      )
      AND NOT has_database_privilege(r.rolname, 'postgres', 'CREATE')
      AND NOT has_database_privilege(r.rolname, '{sql_template}', 'CREATE')
  ) THEN
    RAISE EXCEPTION 'restore runtime role has direct database or schema creation authority';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM pg_roles r
    WHERE r.rolname = '{sql_hotswap}'
      AND NOT r.rolcreatedb
      AND r.rolinherit
      AND has_database_privilege(r.rolname, '{sql_template}', 'CREATE')
      AND EXISTS (
        SELECT 1 FROM pg_auth_members m
        WHERE m.member = r.oid AND m.roleid = to_regrole('pg_signal_backend')
      )
      AND NOT EXISTS (
        SELECT 1 FROM pg_auth_members m
        WHERE (m.member = r.oid AND m.roleid <> to_regrole('pg_signal_backend'))
           OR m.roleid = r.oid
      )
  ) THEN
    RAISE EXCEPTION 'restore hotswap role is not a dedicated non-CREATEDB executor';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_stat_activity WHERE datname = '{sql_template}'
  ) THEN
    RAISE EXCEPTION 'restore target template has active connections';
  END IF;
END
$m05$;
{disable_provisioner_sql}
DROP DATABASE IF EXISTS {quoted_database} WITH (FORCE);
CREATE DATABASE {quoted_database} WITH OWNER {quoted_fence_role} TEMPLATE {quoted_template};
GRANT CONNECT ON DATABASE {quoted_database} TO {quoted_role};
GRANT CONNECT, CREATE ON DATABASE {quoted_database} TO {quoted_hotswap_role};
DO $m05$
BEGIN
  IF NOT ({postcondition_sql}) THEN
    RAISE EXCEPTION 'fresh target fence-owner postcondition failed';
  END IF;
END
$m05$;
SELECT pg_advisory_unlock(1414679892, 1213421392);
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


def _maintenance_database_url(database_url: str) -> str:
    try:
        parsed = urlsplit(database_url)
    except ValueError as exc:
        raise RestoreDrillError("restore maintenance URL is invalid") from exc
    return urlunsplit(parsed._replace(path="/postgres"))


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
            head = remote_payload["head"]
            base = remote_payload["base"]
            if not isinstance(head, dict) or not isinstance(base, dict):
                raise RestoreDrillError("restore producer GitHub PR topology is invalid")
            head_repo = head.get("repo")
            base_repo = base.get("repo")
            if (
                remote_payload["html_url"] != "https://github.com/digitie/pinvi/pull/466"
                or base.get("ref") != "main"
                or not isinstance(base_repo, dict)
                or base_repo.get("full_name") != "digitie/pinvi"
                or not isinstance(head_repo, dict)
                or head_repo.get("full_name") != "digitie/pinvi"
                or head.get("ref") != "codex/m05-activation"
            ):
                raise RestoreDrillError("restore producer is not the current canonical M05 PR")
            if os.environ.get("PINVI_ENVIRONMENT") == "production":
                if (
                    remote_payload.get("state") != "closed"
                    or remote_payload.get("draft") is not False
                    or not remote_payload.get("merged_at")
                    or remote_payload.get("merge_commit_sha") != revision
                ):
                    raise RestoreDrillError(
                        "production restore producer must be the merged M05 PR commit"
                    )
            elif remote_revision != revision:
                raise RestoreDrillError("restore producer is not the current canonical M05 PR head")
        except (OSError, urllib.error.URLError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise RestoreDrillError("restore producer GitHub PR head could not be verified") from exc
    return revision


def _run_drill(args: argparse.Namespace, *, _lease_held: bool = False) -> int:
    output: Path = args.output
    environment = os.environ.get("PINVI_ENVIRONMENT", "")
    if environment in {"staging", "production"} and not args.require_root_owned:
        raise RestoreDrillError(
            "staging/production restore drill requires a root-owned target lease"
        )
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
    if (
        os.environ.get("PINVI_M05_RESTORE_TEST_MODE") != "1"
        and not _ROLE_RE.fullmatch(args.fence_role)
    ):
        raise RestoreDrillError("restore fence role is required")
    if (
        os.environ.get("PINVI_M05_RESTORE_TEST_MODE") != "1"
        and not _ROLE_RE.fullmatch(args.provisioner_role)
    ):
        raise RestoreDrillError("restore provisioner role is required")
    if (
        os.environ.get("PINVI_M05_RESTORE_TEST_MODE") != "1"
        and not args.provision_disable_login
    ):
        raise RestoreDrillError(
            "restore provisioner login must be disabled after disposable target creation"
        )
    if args.runtime_role == args.staging_role:
        raise RestoreDrillError("restore staging and runtime roles must differ")
    bash_tool = _tool_identity("bash")
    _PINNED_TOOL_PATHS["bash"] = bash_tool["path"]
    psql_tool = _tool_identity("psql")
    _PINNED_TOOL_PATHS["psql"] = psql_tool["path"]
    source_url = _database_url(args.source_database_url_env)
    target_url = _database_url(args.staging_database_url_env)
    runtime_url = _database_url(args.runtime_database_url_env)
    if args.require_root_owned and not _lease_held:
        with _acquire_root_target_lease(target_url):
            return _run_drill(args, _lease_held=True)
    hotswap_url = ""
    fence_url = ""
    provision_url = ""
    hotswap_role = ""
    template_url = ""
    if os.environ.get("PINVI_M05_RESTORE_TEST_MODE") != "1":
        if not _ROLE_RE.fullmatch(args.hotswap_role):
            raise RestoreDrillError("restore hotswap role is required")
        hotswap_role = args.hotswap_role
        hotswap_url = _database_url(args.hotswap_database_url_env)
        fence_url = _database_url(args.fence_database_url_env)
        provision_url = _database_url(args.provision_database_url_env)
        template_url = _database_url(args.template_database_url_env)
    try:
        source_database_name = urlsplit(source_url).path.removeprefix("/")
        target_database_name = urlsplit(target_url).path.removeprefix("/")
        provision_database_name = urlsplit(provision_url).path.removeprefix("/")
        hotswap_database_name = urlsplit(hotswap_url).path.removeprefix("/")
        fence_database_name = urlsplit(fence_url).path.removeprefix("/")
    except ValueError as exc:
        raise RestoreDrillError("restore database URL is invalid") from exc
    if source_database_name == target_database_name:
        raise RestoreDrillError("restore source and disposable target databases must differ")
    if hotswap_url and hotswap_database_name != target_database_name:
        raise RestoreDrillError("restore hotswap database must match the disposable target")
    if fence_url and fence_database_name != target_database_name:
        raise RestoreDrillError("restore fence database must match the disposable target")
    if provision_url and provision_database_name != "postgres":
        raise RestoreDrillError("restore provisioner URL must use the postgres maintenance database")
    if os.environ.get("PINVI_M05_RESTORE_TEST_MODE") != "1":
        _staging_role_check(
            _maintenance_database_url(target_url),
            expected_role=args.staging_role,
            runtime_role=args.runtime_role,
        )
        _recreate_disposable_target(
            target_url,
            staging_role=args.staging_role,
            provision_url=provision_url,
            provisioner_role=args.provisioner_role,
            disable_provisioner_login=args.provision_disable_login,
            fence_role=args.fence_role,
            fence_url=fence_url,
            runtime_role=args.runtime_role,
            hotswap_role=hotswap_role,
            hotswap_url=hotswap_url,
            template_url=template_url,
        )
    source_identity_pre = _identity(source_url, schema=args.schema)
    target_identity_pre = _identity(target_url, schema=args.schema)
    runtime_identity_pre = _identity(runtime_url, schema=args.schema)
    fence_identity_pre = _identity(fence_url, schema=args.schema) if fence_url else None
    hotswap_identity_pre = _identity(hotswap_url, schema=args.schema) if hotswap_url else None
    source_key = _identity_key(source_identity_pre)
    target_key = _identity_key(target_identity_pre)
    runtime_key = _identity_key(runtime_identity_pre)
    fence_key = _identity_key(fence_identity_pre) if fence_identity_pre else None
    hotswap_key = _identity_key(hotswap_identity_pre) if hotswap_identity_pre else None
    if (
        source_key in {target_key, runtime_key}
        or target_key != runtime_key
        or (fence_key is not None and fence_key != target_key)
        or (hotswap_key is not None and hotswap_key != target_key)
    ):
        raise RestoreDrillError(
            "restore source, owner target, hotswap target, and runtime target identities are invalid"
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
    if fence_url:
        _fence_role_check(fence_url, expected_role=args.fence_role)
    if hotswap_url:
        _hotswap_role_check(
            hotswap_url,
            schema=args.schema,
            expected_role=hotswap_role,
            require_schema_owner=False,
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
                "PINVI_BACKUP_CATALOG_PATH": str(temporary_dir / "backup-catalog.json"),
                "PINVI_BACKUP_TRUSTED": "1",
                # The drill resolves source_url itself under its root-only
                # source/target identity gate before invoking the canonical
                # runner.  Compose maintenance uses trusted-backup-entrypoint
                # for the same one-time hostname-to-hostaddr transition.
                "PINVI_M05_RESTORE_PRODUCER": "1",
                "PINVI_BACKUP_MIN_FREE_BYTES": "0",
                "PINVI_BACKUP_DOCKER_FALLBACK": "0",
                "PINVI_BACKUP_PG_DUMP_BIN": private_tools["pg_dump"]["path"],
                "PINVI_BACKUP_PG_RESTORE_BIN": private_tools["pg_restore"]["path"],
                "PINVI_BACKUP_PSQL_BIN": private_tools["psql"]["path"],
                "PINVI_BACKUP_PG_DUMP_SHA256": private_tools["pg_dump"]["sha256"],
                "PINVI_BACKUP_PG_RESTORE_SHA256": private_tools["pg_restore"]["sha256"],
                "PINVI_BACKUP_PSQL_SHA256": private_tools["psql"]["sha256"],
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
                "PINVI_RESTORE_FENCE_DATABASE_URL": fence_url,
                "PINVI_RESTORE_SCHEMA": args.schema,
                "PINVI_RESTORE_APP_ROLE": args.runtime_role,
                # 범용 drill은 DB precheck까지만 증명한다. schema-swap execution과
                # terminal evidence는 root-only trusted entrypoint가 전담한다.
                "PINVI_RESTORE_DRILL_ROLLBACK_REHEARSAL": "precheck",
                "PINVI_RESTORE_PG_RESTORE_BIN": private_tools["pg_restore"]["path"],
                "PINVI_RESTORE_PSQL_BIN": private_tools["psql"]["path"],
                "PINVI_RESTORE_PG_RESTORE_SHA256": private_tools["pg_restore"]["sha256"],
                "PINVI_RESTORE_PSQL_SHA256": private_tools["psql"]["sha256"],
                "PINVI_RESTORE_PRIVATE_TOOL_COPY": "1",
                "PINVI_M05_RESTORE_REQUIRE_TOOL_TRUST": "1",
                "PINVI_RESTORE_REQUIRE_FRESH_SCHEMA": "1",
            }
        )
        if hotswap_url:
            restore_env["PINVI_RESTORE_HOTSWAP_DATABASE_URL"] = hotswap_url
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
                    "PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_NAME": str(
                        source_identity_pre["database"]
                    ),
                    "PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_OID": str(
                        source_identity_pre["database_oid"]
                    ),
                    "PINVI_RESTORE_EXPECTED_SOURCE_SYSTEM_IDENTIFIER": str(
                        source_identity_pre["system_identifier"]
                    ),
                    "PINVI_RESTORE_EXPECTED_SOURCE_HOSTADDR": str(
                        source_identity_pre["hostaddr"]
                    ),
                    "PINVI_RESTORE_EXPECTED_SOURCE_PORT": str(source_identity_pre["port"]),
                    "PINVI_RESTORE_TRUSTED_BACKUP_DIR": str(temporary_dir),
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
            "DRILL_EVIDENCE=rollback_rehearsal=precheck_guard_schema_unchanged",
            "DRILL_PHASE=complete:success:staging restore drill completed",
            "RESTORE_COMMAND=pg_restore --clean --if-exists --exit-on-error --no-owner --no-privileges",
        ]
        if os.environ.get("PINVI_M05_RESTORE_TEST_MODE") != "1":
            required_markers.append("RESTORE_TARGET_BINDING=verified")
            required_markers.append("RESTORE_SOURCE_BINDING=verified")
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
        if fence_url:
            _fence_role_check(fence_url, expected_role=args.fence_role)
        if hotswap_url:
            _hotswap_role_check(
                hotswap_url,
                schema=args.schema,
                expected_role=hotswap_role,
                require_schema_owner=True,
            )
        trigger_url = hotswap_url or target_url
        _admin_audit_contract_check(trigger_url, schema=args.schema)
        _admin_audit_guard_is_enforced(trigger_url, schema=args.schema)
        _trigger_check(trigger_url, schema=args.schema)
        _trigger_guard_is_enforced(trigger_url, schema=args.schema)
        target_identity = _identity(target_url, schema=args.schema)
        runtime_identity = _identity(runtime_url, schema=args.schema)
        fence_identity = _identity(fence_url, schema=args.schema) if fence_url else None
        hotswap_identity = _identity(hotswap_url, schema=args.schema) if hotswap_url else None
        if (
            _identity_key(target_identity) != target_key
            or _identity_key(runtime_identity) != target_key
            or (fence_identity is not None and _identity_key(fence_identity) != target_key)
            or (
                hotswap_identity is not None
                and _identity_key(hotswap_identity) != target_key
            )
        ):
            raise RestoreDrillError(
                "restore target identity changed or does not match the runtime target"
            )

        hotswap_success = False
        hotswap_success_marker = ""
        hotswap_success_output_sha256 = ""
        hotswap_schema_oid_before = ""
        hotswap_schema_oid_after = ""
        hotswap_previous_schema_oid = ""
        hotswap_previous_schema_present = False
        hotswap_restore_schema_absent = False
        hotswap_advisory_lock_released = False
        hotswap_fence_restored = False
        hotswap_executor_reconnect_fenced = False

        execution_output = (
            f"{backup.stdout}\0{backup.stderr}\0{restore.stdout}\0{restore.stderr}"
            f"\0{hotswap_success_output_sha256}"
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
            "provisioner_login_disabled": bool(
                provision_url and args.provision_disable_login
            ),
            "provisioner_role": args.provisioner_role,
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
            "fence_role_verified": fence_identity is not None,
            "fence_role": args.fence_role,
            "source_db_identity": source_identity_pre,
            "source_db_identity_after_backup": source_identity_after_backup,
            "target_db_identity_before_restore": target_identity_before_restore,
            "target_db_identity": target_identity,
            "target_recreated": os.environ.get("PINVI_M05_RESTORE_TEST_MODE") != "1",
            "runtime_db_identity": runtime_identity,
            "fence_db_identity_before_restore": fence_identity_pre,
            "fence_db_identity": fence_identity,
            "fence_db_identity_before_restore_sha256": (
                _identity_sha256(fence_identity_pre) if fence_identity_pre is not None else ""
            ),
            "fence_db_identity_sha256": (
                _identity_sha256(fence_identity) if fence_identity is not None else ""
            ),
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
            "hotswap_success": hotswap_success,
            "hotswap_success_marker": hotswap_success_marker,
            "hotswap_success_output_sha256": hotswap_success_output_sha256,
            "hotswap_schema_oid_before": hotswap_schema_oid_before,
            "hotswap_schema_oid_after": hotswap_schema_oid_after,
            "hotswap_previous_schema_oid": hotswap_previous_schema_oid,
            "hotswap_previous_schema_present": hotswap_previous_schema_present,
            "hotswap_restore_schema_absent": hotswap_restore_schema_absent,
            "hotswap_advisory_lock_released": hotswap_advisory_lock_released,
            "hotswap_fence_restored": hotswap_fence_restored,
            "hotswap_executor_reconnect_fenced": hotswap_executor_reconnect_fenced,
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
        "--fence-database-url-env",
        default="PINVI_RESTORE_FENCE_DATABASE_URL",
    )
    parser.add_argument(
        "--provision-database-url-env",
        default="PINVI_RESTORE_PROVISION_DATABASE_URL",
    )
    parser.add_argument(
        "--provisioner-role",
        default=os.environ.get("PINVI_RESTORE_PROVISIONER_ROLE", ""),
    )
    parser.add_argument(
        "--provision-disable-login",
        action="store_true",
        default=os.environ.get("PINVI_RESTORE_PROVISION_DISABLE_LOGIN", "0") == "1",
    )
    parser.add_argument(
        "--runtime-database-url-env",
        default="PINVI_RESTORE_RUNTIME_DATABASE_URL",
    )
    parser.add_argument(
        "--template-database-url-env",
        default="PINVI_RESTORE_TEMPLATE_DATABASE_URL",
    )
    parser.add_argument(
        "--hotswap-database-url-env",
        default="PINVI_RESTORE_HOTSWAP_DATABASE_URL",
    )
    parser.add_argument(
        "--hotswap-role",
        default=os.environ.get("PINVI_RESTORE_HOTSWAP_ROLE", ""),
    )
    parser.add_argument(
        "--fence-role",
        default=os.environ.get("PINVI_RESTORE_FENCE_ROLE", ""),
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
