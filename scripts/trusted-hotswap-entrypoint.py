#!/usr/bin/env python3
"""staging/production M05 hotswap의 좁은 root-only host entrypoint.

ordinary API와 이 entrypoint의 권한은 의도적으로 분리한다. 이 entrypoint는 canonical
runner에 단일-IP로 pin한 PostgreSQL endpoint만 전달하고, forensic marker의 status와
recovery acknowledgement만 제공한다. M05 receipt 서명, runtime lease 발급, Docker socket
제어 권한은 갖지 않는다.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import socket
import stat
import subprocess
import sys
from pathlib import Path
from typing import Final, NoReturn, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_POSTGRES_SCHEMES: Final = frozenset({"postgres", "postgresql", "postgresql+asyncpg"})
_ENDPOINT_QUERY_KEYS: Final = frozenset(
    {"host", "hostaddr", "port", "service", "servicefile"}
)
_STRICT_ENVIRONMENTS: Final = frozenset({"staging", "production"})
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}")
_ROLE_RE: Final = re.compile(r"[a-z_][a-z0-9_]*")
_SCHEMA_RE: Final = re.compile(r"[a-z_][a-z0-9_]*")
_UUID_RE: Final = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_STATE_DIRECTORY: Final = "/var/lib/pinvi/restore-forensics"
_LOCK_CLASSID: Final = 1414679892
_LOCK_OBJID: Final = 1213421392


class TrustedHotswapError(RuntimeError):
    """trusted root hotswap entrypoint precondition failure."""


def _raise(message: str) -> NoReturn:
    raise TrustedHotswapError(message)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _safe_regular_file(path: Path) -> Path:
    if path.is_symlink() or not path.is_file():
        _raise("trusted hotswap runner is unavailable")
    metadata = path.stat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        _raise("trusted hotswap runner permissions are invalid")
    return path.resolve(strict=True)


def _safe_parent_chain(path: Path) -> None:
    if not path.is_absolute():
        _raise("trusted hotswap runner path is invalid")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except OSError:
            _raise("trusted hotswap runner parent is unavailable")
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            _raise("trusted hotswap runner parent permissions are invalid")


def _canonical_runner_paths() -> tuple[Path, Path]:
    script = Path(__file__)
    _safe_parent_chain(script.parent)
    entrypoint = _safe_regular_file(script)
    runner = _safe_regular_file(entrypoint.with_name("restore-hotswap.sh"))
    forensics = _safe_regular_file(entrypoint.with_name("m05_hotswap_forensics.py"))
    if runner.parent != entrypoint.parent or forensics.parent != entrypoint.parent:
        _raise("trusted hotswap runner path is not canonical")
    return runner, forensics


def _resolved_hostaddr(hostname: str, port: int) -> str:
    try:
        records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise TrustedHotswapError(
            "hotswap database host could not be resolved"
        ) from exc
    addresses: set[str] = set()
    for record in records:
        sockaddr = record[4]
        if not sockaddr or not isinstance(sockaddr[0], str):
            continue
        try:
            addresses.add(str(ipaddress.ip_address(sockaddr[0])))
        except ValueError:
            continue
    if len(addresses) != 1:
        _raise("hotswap database host must resolve to exactly one address")
    return addresses.pop()


def pin_database_url(value: str) -> str:
    """hostname PostgreSQL URL을 단일 DNS answer와 ``hostaddr``로 결박한다."""

    if not value or any(character.isspace() for character in value):
        _raise("hotswap database URL is missing or malformed")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port or 5432
    except ValueError as exc:
        raise TrustedHotswapError("hotswap database URL is invalid") from exc
    if (
        parsed.scheme not in _POSTGRES_SCHEMES
        or not parsed.netloc
        or hostname is None
        or not parsed.path.startswith("/")
        or parsed.path == "/"
        or parsed.fragment
    ):
        _raise("hotswap database URL is not a canonical PostgreSQL URL")
    query = parse_qsl(parsed.query, keep_blank_values=True)
    names = [name for name, _ in query]
    if any(not name for name in names) or len(set(names)) != len(names):
        _raise("hotswap database URL query is ambiguous")
    if _ENDPOINT_QUERY_KEYS.intersection(names):
        _raise("hotswap database URL must not preconfigure an endpoint override")
    query.append(("hostaddr", _resolved_hostaddr(hostname, port)))
    return urlunsplit(parsed._replace(query=urlencode(query, safe=":")))


def _strict_environment() -> None:
    if os.geteuid() != 0:
        _raise("trusted hotswap entrypoint requires root execution")
    if os.environ.get("PINVI_ENVIRONMENT", "") not in _STRICT_ENVIRONMENTS:
        _raise("trusted hotswap entrypoint requires staging or production")


def _forensics_command(
    forensics: Path, arguments: list[str]
) -> subprocess.CompletedProcess[str]:
    # fixed root-owned Python helper and literal argv.
    return subprocess.run(
        [sys.executable, str(forensics), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
    )


def _read_marker(forensics: Path) -> dict[str, object]:
    result = _forensics_command(
        forensics,
        ["status", "--strict", "--state-dir", _STATE_DIRECTORY],
    )
    if result.returncode != 0:
        _raise("hotswap forensic marker is unavailable")
    try:
        marker = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise TrustedHotswapError("hotswap forensic marker is invalid") from exc
    if not isinstance(marker, dict):
        _raise("hotswap forensic marker is invalid")
    return cast(dict[str, object], marker)


def _identity_sha256_from_psql(database_url: str) -> tuple[str, dict[str, object]]:
    psql = os.environ.get("PINVI_RESTORE_PSQL_BIN", "/usr/bin/psql")
    path = Path(psql)
    if path != Path("/usr/bin/psql") and not re.fullmatch(
        r"/usr/lib/postgresql/[0-9]+/bin/psql", psql
    ):
        _raise("trusted recovery psql path is invalid")
    if path.is_symlink() or not path.is_file() or not os.access(path, os.X_OK):
        _raise("trusted recovery psql is unavailable")
    identity_sql = """
SELECT current_database() || '|' || d.oid::text || '|' ||
       (pg_control_system()).system_identifier::text || '|' ||
       COALESCE(host(inet_server_addr()), '') || '|' || inet_server_port()::text
FROM pg_database d
WHERE d.datname = current_database();
"""
    # psql path has a strict allowlist.
    result = subprocess.run(
        [
            str(path),
            "--no-psqlrc",
            "-Atq",
            "--dbname",
            database_url,
            "--command",
            identity_sql,
        ],
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
    )
    if result.returncode != 0:
        _raise("trusted recovery database identity could not be read")
    value = result.stdout.strip()
    values = value.split("|")
    if len(values) != 5 or any(not item for item in values):
        _raise("trusted recovery database identity is invalid")
    return hashlib.sha256(value.encode("utf-8")).hexdigest(), {
        "database": values[0],
        "database_oid": values[1],
        "hostaddr": values[3],
        "port": values[4],
        "system_identifier": values[2],
    }


def _safe_recovery_observation(marker: dict[str, object], database_url: str) -> str:
    operation_id = marker.get("operation_id")
    source_schema = marker.get("source_schema")
    previous_schema = marker.get("previous_schema")
    app_role = marker.get("app_role")
    expected_target = marker.get("target_identity_sha256")
    expected_app_oid = marker.get("app_schema_oid_after_switch")
    expected_previous_oid = marker.get("previous_schema_oid_after_switch")
    if (
        not isinstance(operation_id, str)
        or _UUID_RE.fullmatch(operation_id) is None
        or not isinstance(source_schema, str)
        or _SCHEMA_RE.fullmatch(source_schema) is None
        or not isinstance(previous_schema, str)
        or _SCHEMA_RE.fullmatch(previous_schema) is None
        or not isinstance(app_role, str)
        or _ROLE_RE.fullmatch(app_role) is None
        or not isinstance(expected_target, str)
        or _SHA256_RE.fullmatch(expected_target) is None
        or type(expected_app_oid) is not int
        or type(expected_previous_oid) is not int
    ):
        _raise("hotswap forensic marker recovery fields are invalid")
    actual_target, _ = _identity_sha256_from_psql(database_url)
    if actual_target != expected_target:
        _raise("trusted recovery database identity does not match the marker")
    psql = os.environ.get("PINVI_RESTORE_PSQL_BIN", "/usr/bin/psql")
    observation_sql = f"""
SELECT json_build_object(
  'advisory_lock_absent', NOT EXISTS (
    SELECT 1 FROM pg_locks
    WHERE locktype = 'advisory' AND classid = {_LOCK_CLASSID} AND objid = {_LOCK_OBJID} AND granted
  ),
  'app_connect', has_database_privilege('{app_role}', current_database(), 'CONNECT'),
  'app_oid', COALESCE((SELECT oid::text FROM pg_namespace WHERE nspname = '{source_schema}'), ''),
  'app_usage', has_schema_privilege('{app_role}', '{source_schema}', 'USAGE'),
  'previous_oid', COALESCE((SELECT oid::text FROM pg_namespace WHERE nspname = '{previous_schema}'), '')
)::text;
"""
    # psql path was checked by the identity query above.
    result = subprocess.run(
        [
            psql,
            "--no-psqlrc",
            "-Atq",
            "--dbname",
            database_url,
            "--command",
            observation_sql,
        ],
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
    )
    if result.returncode != 0:
        _raise("trusted recovery state could not be read")
    try:
        observation = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise TrustedHotswapError("trusted recovery state is invalid") from exc
    if not isinstance(observation, dict) or set(observation) != {
        "advisory_lock_absent",
        "app_connect",
        "app_oid",
        "app_usage",
        "previous_oid",
    }:
        _raise("trusted recovery state is invalid")
    if (
        observation["advisory_lock_absent"] is not True
        or observation["app_connect"] is not True
        or observation["app_usage"] is not True
        or observation["app_oid"] != str(expected_app_oid)
        or observation["previous_oid"] != str(expected_previous_oid)
    ):
        _raise("trusted recovery state does not prove a released switched schema")
    return hashlib.sha256(_canonical_json(observation)).hexdigest()


def _run(args: argparse.Namespace) -> int:
    _strict_environment()
    runner, _ = _canonical_runner_paths()
    database_url = pin_database_url(os.environ.get("PINVI_RESTORE_DATABASE_URL", ""))
    fence_url = pin_database_url(os.environ.get("PINVI_RESTORE_FENCE_DATABASE_URL", ""))
    environment = os.environ.copy()
    environment.update(
        {
            "PINVI_RESTORE_DATABASE_URL": database_url,
            "PINVI_RESTORE_FENCE_DATABASE_URL": fence_url,
            "PINVI_RESTORE_HOTSWAP_TRUSTED_ENTRYPOINT": "1",
        }
    )
    os.execve(
        str(runner),
        [str(runner), "run", args.snapshot, args.restore_schema, args.previous_schema],
        environment,
    )
    return 3


def _status(_: argparse.Namespace) -> int:
    _strict_environment()
    _, forensics = _canonical_runner_paths()
    marker = _read_marker(forensics)
    sys.stdout.buffer.write(_canonical_json(marker) + b"\n")
    return 0


def _recover(args: argparse.Namespace) -> int:
    _strict_environment()
    if not args.confirm:
        _raise("trusted recovery requires --confirm")
    _, forensics = _canonical_runner_paths()
    marker = _read_marker(forensics)
    if marker.get("operation_id") != args.operation_id:
        _raise("trusted recovery operation does not match the active marker")
    if marker.get("state") != "fence_released":
        _raise("trusted recovery only acknowledges a released writer fence")
    database_url = pin_database_url(os.environ.get("PINVI_RESTORE_DATABASE_URL", ""))
    verification_sha256 = _safe_recovery_observation(marker, database_url)
    result = _forensics_command(
        forensics,
        [
            "acknowledge",
            "--strict",
            "--state-dir",
            _STATE_DIRECTORY,
            "--operation-id",
            args.operation_id,
            "--verification-sha256",
            verification_sha256,
            "--confirm",
        ],
    )
    if result.returncode != 0:
        _raise("trusted recovery acknowledgement could not be written")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PinVi trusted hotswap entrypoint")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("snapshot")
    run.add_argument("restore_schema")
    run.add_argument("previous_schema")
    commands.add_parser("status")
    recover = commands.add_parser("recover")
    recover.add_argument("--operation-id", required=True)
    recover.add_argument("--confirm", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        handlers = {"run": _run, "status": _status, "recover": _recover}
        return handlers[args.command](args)
    except TrustedHotswapError as exc:
        print(f"trusted hotswap failed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
