#!/usr/bin/python3 -I
"""staging/production M05 hotswap의 좁은 root-only host entrypoint.

ordinary API와 이 entrypoint의 권한은 의도적으로 분리한다. 이 entrypoint는 canonical
runner에 단일-IP로 pin한 PostgreSQL endpoint만 전달하고, forensic marker의 status와
read-only DB proof를 거친 recovery acknowledgement만 제공한다. M05 receipt 서명,
runtime lease 발급, Docker socket 제어 권한은 갖지 않는다.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import ipaddress
import json
import os
import re
import socket
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, NoReturn, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_POSTGRES_SCHEMES: Final = frozenset({"postgres", "postgresql", "postgresql+asyncpg"})
_ALLOWED_DATABASE_URL_QUERY_KEYS: Final = frozenset({"sslmode"})
_SSL_MODES: Final = frozenset(
    {"allow", "disable", "prefer", "require", "verify-ca", "verify-full"}
)
_STRICT_ENVIRONMENTS: Final = frozenset({"staging", "production"})
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}")
_ROLE_RE: Final = re.compile(r"[a-z_][a-z0-9_]*")
_SCHEMA_RE: Final = re.compile(r"[a-z_][a-z0-9_]*")
_UUID_RE: Final = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_STATE_DIRECTORY: Final = "/var/lib/pinvi/restore-forensics"
_DRAIN_RECEIPT_PATH: Final = Path(_STATE_DIRECTORY) / "drain-receipt.json"
_DRAIN_RECEIPT_MAX_AGE: Final = timedelta(minutes=15)
_LOCK_CLASSID: Final = 1414679892
_LOCK_OBJID: Final = 1213421392
_TOPOLOGY_FILENAME: Final = "m05_hotswap_topology.sql"
_RUNNER_UNSAFE_ENVIRONMENT_KEYS: Final = frozenset(
    {
        # The wrapper, rather than its inherited environment, chooses every
        # executable and digest consumed by the root runner.
        "PINVI_RESTORE_BASH_BIN",
        "PINVI_RESTORE_BASH_SHA256",
        "PINVI_RESTORE_DRAIN_COMMAND",
        "PINVI_RESTORE_DRAIN_RECEIPT_PATH",
        "PINVI_RESTORE_DRAIN_VERIFIED",
        "PINVI_RESTORE_HOTSWAP_EXECUTE",
        "PINVI_RESTORE_ALLOW_NO_DRAIN",
        "PINVI_RESTORE_EXTERNAL_LOCK_HOLDER_BACKEND_PID",
        "PINVI_RESTORE_EXTERNAL_LOCK_HOLDER_PID",
        "PINVI_RESTORE_PG_RESTORE_BIN",
        "PINVI_RESTORE_PG_RESTORE_SHA256",
        "PINVI_RESTORE_PRIVATE_TOOL_COPY",
        "PINVI_RESTORE_PSQL_BIN",
        "PINVI_RESTORE_PSQL_SHA256",
        "PINVI_RESTORE_TEST_FAIL_FORENSICS_HISTORY_APPEND_ONCE",
        "PINVI_RESTORE_TEST_FAIL_FORENSICS_RELEASE_ONCE",
        "PINVI_RESTORE_TEST_FAIL_AFTER_RELEASE_RECEIPT_SEAL_ONCE",
        "PINVI_RESTORE_TEST_FAIL_REFENCE_SQL_ONCE",
        "PINVI_RESTORE_TEST_FAIL_RELEASE_DATABASE_SQL_ONCE",
        "PINVI_RESTORE_TEST_FAIL_RELEASE_ONCE",
        "PINVI_RESTORE_TEST_FAIL_RELEASE_SQL_ONCE",
        "PINVI_RESTORE_TEST_FAIL_RELEASE_WINDOW_ONCE",
        "PINVI_RESTORE_TEST_FAIL_RESTORE_ONCE",
        "PINVI_RESTORE_TEST_REQUIRE_RELEASE_RECEIPT",
        "PINVI_RESTORE_TEST_SIGKILL_AFTER_RELEASE_RECEIPT_COMMIT_ONCE",
        "PINVI_RESTORE_TEST_SIGKILL_AFTER_RELEASE_RECEIPT_SEAL_ONCE",
        "PINVI_RESTORE_WRITE_ROLES",
        "PINVI_M05_FORENSICS_DRAIN_RECEIPT_SHA256",
        "PINVI_M05_FORENSICS_OPERATION_ID",
        "PINVI_M05_FORENSICS_STATE_DIR",
        "PINVI_M05_RESTORE_DRILL",
        "PINVI_M05_RESTORE_TEST_MODE",
        # These inputs are read only from /etc/pinvi/trusted-hotswap.json.
        # Keep this second guard even though the root wrapper empties env: it
        # makes direct helper reuse fail closed rather than reintroducing an
        # environment-derived operation input.
        "PINVI_BACKUP_SCHEMA",
        "PINVI_ENVIRONMENT",
        "PINVI_RESTORE_APP_ROLE",
        "PINVI_RESTORE_DATABASE_URL",
        "PINVI_RESTORE_FENCE_DATABASE_URL",
        "PINVI_RESTORE_TRUSTED_BACKUP_DIR",
        "PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_NAME",
        "PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_OID",
        "PINVI_RESTORE_EXPECTED_SOURCE_SYSTEM_IDENTIFIER",
        "PINVI_RESTORE_EXPECTED_SOURCE_HOSTADDR",
        "PINVI_RESTORE_EXPECTED_SOURCE_PORT",
        # A root wrapper reads the target once and supplies the exact values
        # to every runner SQL identity guard. Caller-provided values would
        # turn that guard into a value selected by the caller.
        "PINVI_RESTORE_EXPECTED_DATABASE_NAME",
        "PINVI_RESTORE_EXPECTED_DATABASE_OID",
        "PINVI_RESTORE_EXPECTED_HOSTADDR",
        "PINVI_RESTORE_EXPECTED_PORT",
        "PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER",
    }
)
_SOURCE_IDENTITY_CONFIGURATION: Final = (
    (
        "PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_NAME",
        "source_database_name",
        re.compile(r"[A-Za-z_][A-Za-z0-9_]*"),
    ),
    (
        "PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_OID",
        "source_database_oid",
        re.compile(r"[0-9]+"),
    ),
    (
        "PINVI_RESTORE_EXPECTED_SOURCE_SYSTEM_IDENTIFIER",
        "source_system_identifier",
        re.compile(r"[0-9]+"),
    ),
    (
        "PINVI_RESTORE_EXPECTED_SOURCE_HOSTADDR",
        "source_hostaddr",
        re.compile(r"[0-9A-Fa-f:.]+"),
    ),
    (
        "PINVI_RESTORE_EXPECTED_SOURCE_PORT",
        "source_port",
        re.compile(r"[0-9]+"),
    ),
)
_TARGET_IDENTITY_ENVIRONMENT: Final = (
    ("PINVI_RESTORE_EXPECTED_DATABASE_NAME", "database"),
    ("PINVI_RESTORE_EXPECTED_DATABASE_OID", "database_oid"),
    ("PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER", "system_identifier"),
    ("PINVI_RESTORE_EXPECTED_HOSTADDR", "hostaddr"),
    ("PINVI_RESTORE_EXPECTED_PORT", "port"),
)
_SAFE_ENVIRONMENT: Final = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
}
_CONFIG_PATH: Final = Path("/etc/pinvi/trusted-hotswap.json")
_CONFIG_FIELDS: Final = frozenset(
    {
        "app_role",
        "environment",
        "fence_database_url",
        "restore_database_url",
        "source_identity",
        "source_schema",
        "trusted_backup_dir",
    }
)
_CONFIG_SOURCE_IDENTITY_FIELDS: Final = frozenset(
    {"database_name", "database_oid", "hostaddr", "port", "system_identifier"}
)


@dataclass(frozen=True)
class TrustedHotswapConfiguration:
    """Root-only hotswap input. 호출자의 환경변수로 대체할 수 없다."""

    app_role: str
    environment: str
    fence_database_url: str
    restore_database_url: str
    source_database_name: str
    source_database_oid: str
    source_hostaddr: str
    source_port: str
    source_schema: str
    source_system_identifier: str
    trusted_backup_dir: str


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


def _canonical_runner_paths() -> tuple[Path, Path, Path]:
    script = Path(__file__)
    _safe_parent_chain(script.parent)
    entrypoint = _safe_regular_file(script)
    runner = _safe_regular_file(entrypoint.with_name("restore-hotswap.sh"))
    forensics = _safe_regular_file(entrypoint.with_name("m05_hotswap_forensics.py"))
    topology = _safe_regular_file(entrypoint.with_name(_TOPOLOGY_FILENAME))
    if (
        runner.parent != entrypoint.parent
        or forensics.parent != entrypoint.parent
        or topology.parent != entrypoint.parent
    ):
        _raise("trusted hotswap runner path is not canonical")
    return runner, forensics, topology


def _safe_trusted_executable(path: Path) -> Path:
    """root-owned executable의 final target과 parent chain을 함께 검증한다."""

    if not path.is_absolute():
        _raise("trusted hotswap executable path is invalid")
    try:
        source_metadata = path.lstat()
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except OSError:
        _raise("trusted hotswap executable is unavailable")
    if not stat.S_ISLNK(source_metadata.st_mode) and (
        not stat.S_ISREG(source_metadata.st_mode)
        or source_metadata.st_uid != 0
        or stat.S_IMODE(source_metadata.st_mode) & 0o022
    ):
        _raise("trusted hotswap executable permissions are invalid")
    _safe_parent_chain(resolved.parent)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or not os.access(resolved, os.X_OK)
    ):
        _raise("trusted hotswap executable permissions are invalid")
    return resolved


def _trusted_python_path() -> Path:
    for candidate in (
        Path("/usr/local/bin/python3"),
        Path("/usr/local/bin/python"),
        Path("/usr/bin/python3"),
    ):
        if candidate.exists():
            return _safe_trusted_executable(candidate)
    _raise("trusted hotswap Python interpreter is unavailable")


def _trusted_bash_path() -> Path:
    for candidate in (Path("/usr/bin/bash"), Path("/bin/bash")):
        if candidate.exists():
            return _safe_trusted_executable(candidate)
    _raise("trusted hotswap shell is unavailable")


def _trusted_postgres_tool_path(tool: str) -> Path:
    """고정된 system PostgreSQL client만 root runner에 전달한다."""

    candidates: list[Path] = []
    postgres_directory = Path("/usr/lib/postgresql")
    if postgres_directory.is_dir():
        candidates.extend(
            sorted(postgres_directory.glob(f"[0-9]*/bin/{tool}"), reverse=True)
        )
    # /usr/bin/psql and /usr/bin/pg_restore are pg_wrapper symlinks. The
    # wrapper selects a client by argv[0], so passing its resolved target as
    # an executable would invoke `pg_wrapper` without a client name.
    candidates.append(Path("/usr/bin") / tool)
    for candidate in candidates:
        if candidate.exists():
            return _safe_trusted_executable(candidate)
    _raise(f"trusted hotswap {tool} executable is unavailable")


def _trusted_psql_path() -> Path:
    return _trusted_postgres_tool_path("psql")


def _trusted_pg_restore_path() -> Path:
    return _trusted_postgres_tool_path("pg_restore")


def _trusted_file_sha256(path: Path) -> str:
    """검증한 root-owned executable의 digest를 wrapper가 직접 계산한다."""

    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as source:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


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
    """hostname PostgreSQL URL을 단일 DNS answer와 hostaddr로 결박한다."""

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
    if any(name not in _ALLOWED_DATABASE_URL_QUERY_KEYS for name in names):
        _raise("hotswap database URL query is not allowed")
    if any(name == "sslmode" and value not in _SSL_MODES for name, value in query):
        _raise("hotswap database URL sslmode is invalid")
    query.append(("hostaddr", _resolved_hostaddr(hostname, port)))
    return urlunsplit(parsed._replace(query=urlencode(query, safe=":")))


def _strict_environment() -> None:
    if os.geteuid() != 0:
        _raise("trusted hotswap entrypoint requires root execution")
    if dict(os.environ) != _SAFE_ENVIRONMENT:
        _raise("trusted hotswap entrypoint requires the sanitized root wrapper")


def _forensics_command(
    forensics: Path, arguments: list[str]
) -> subprocess.CompletedProcess[str]:
    # sys.executable is not a trust boundary: this wrapper may itself be
    # invoked through an arbitrary interpreter. Resolve a fixed system Python
    # and ignore Python environment/site customization for each invocation.
    return subprocess.run(
        [str(_trusted_python_path()), "-I", str(forensics), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=_SAFE_ENVIRONMENT,
    )


def _validate_recovery_ledger_proof(proof: object) -> dict[str, object]:
    """forensic module의 in-process proof ABI를 strict하게 고정한다."""

    if not isinstance(proof, dict) or set(proof) != {
        "intent_state_sequence",
        "marker_sha256",
        "recovery_acknowledgement_verification_sha256",
        "release_receipt_record_sha256",
        "root_unsealed_release_receipt_verification_sha256",
    }:
        _raise("trusted forensic history proof is invalid")
    marker_sha256 = proof.get("marker_sha256")
    receipt_record_sha256 = proof.get("release_receipt_record_sha256")
    acknowledgement_verification_sha256 = proof.get(
        "recovery_acknowledgement_verification_sha256"
    )
    root_unsealed_verification_sha256 = proof.get(
        "root_unsealed_release_receipt_verification_sha256"
    )
    sequence = proof.get("intent_state_sequence")
    if (
        not isinstance(marker_sha256, str)
        or _SHA256_RE.fullmatch(marker_sha256) is None
        or (
            receipt_record_sha256 is not None
            and (
                not isinstance(receipt_record_sha256, str)
                or _SHA256_RE.fullmatch(receipt_record_sha256) is None
            )
        )
        or (
            acknowledgement_verification_sha256 is not None
            and (
                not isinstance(acknowledgement_verification_sha256, str)
                or _SHA256_RE.fullmatch(acknowledgement_verification_sha256) is None
            )
        )
        or (
            root_unsealed_verification_sha256 is not None
            and (
                not isinstance(root_unsealed_verification_sha256, str)
                or _SHA256_RE.fullmatch(root_unsealed_verification_sha256) is None
            )
        )
        or (sequence is not None and (type(sequence) is not int or sequence < 1))
    ):
        _raise("trusted forensic history proof is invalid")
    return cast(dict[str, object], proof)


def _load_forensic_history_proof(
    forensics: Path,
    *,
    operation_id: str,
    primitive_name: str,
) -> dict[str, object]:
    """고정 forensic module의 read-only proof primitive 하나만 실행한다."""

    module_name = "_pinvi_m05_hotswap_forensics_history"
    specification = importlib.util.spec_from_file_location(module_name, forensics)
    if specification is None or specification.loader is None:
        _raise("trusted forensic history primitive is unavailable")
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    try:
        specification.loader.exec_module(module)
        validate = getattr(module, primitive_name, None)
        if not callable(validate):
            _raise("trusted forensic history primitive is unavailable")
        proof = validate(Path(_STATE_DIRECTORY), operation_id=operation_id)
        return _validate_recovery_ledger_proof(proof)
    except TrustedHotswapError:
        raise
    except Exception as exc:
        raise TrustedHotswapError(
            "trusted forensic history is not recoverable"
        ) from exc
    finally:
        sys.modules.pop(module_name, None)


def _assert_current_history_consistent_for_recovery(
    forensics: Path, *, operation_id: str
) -> dict[str, object]:
    """current pointer만 앞선 forensic transition은 archive 전에 거부한다."""

    return _load_forensic_history_proof(
        forensics,
        operation_id=operation_id,
        primitive_name="assert_current_history_consistent_for_verified_recovery",
    )


def _assert_unsealed_release_receipt_escalation_history(
    forensics: Path, *, operation_id: str
) -> dict[str, object]:
    """명시적 root escalation만 seal 없는 terminal intent를 읽을 수 있다."""

    return _load_forensic_history_proof(
        forensics,
        operation_id=operation_id,
        primitive_name="assert_unsealed_release_receipt_escalation_history",
    )


def _acknowledge_after_verified_recovery(
    forensics: Path,
    *,
    operation_id: str,
    verification_sha256: str,
    expected_marker_sha256: str,
    expected_release_receipt_record_sha256: str | None,
) -> None:
    """public helper CLI 대신 trusted proof 뒤 marker를 archive한다.

    Strict recovery acknowledgement는 public CLI가 아니라 이 root-only
    entrypoint의 in-process primitive다. 호출자는 이 함수 앞에서 반드시
    `_safe_recovery_observation`의 read-only DB 증명을 완료해야 한다.
    """

    module_name = "_pinvi_m05_hotswap_forensics"
    specification = importlib.util.spec_from_file_location(module_name, forensics)
    if specification is None or specification.loader is None:
        _raise("trusted forensic recovery primitive is unavailable")
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    try:
        specification.loader.exec_module(module)
        acknowledge = getattr(module, "acknowledge_after_verified_recovery", None)
        if not callable(acknowledge):
            _raise("trusted forensic recovery primitive is unavailable")
        acknowledge(
            Path(_STATE_DIRECTORY),
            operation_id=operation_id,
            verification_sha256=verification_sha256,
            expected_marker_sha256=expected_marker_sha256,
            expected_release_receipt_record_sha256=expected_release_receipt_record_sha256,
        )
    except TrustedHotswapError:
        raise
    except Exception as exc:
        raise TrustedHotswapError(
            "trusted recovery acknowledgement could not be written"
        ) from exc
    finally:
        sys.modules.pop(module_name, None)


def _acknowledge_unsealed_release_receipt_after_verified_recovery(
    forensics: Path,
    *,
    operation_id: str,
    verification_sha256: str,
    expected_marker_sha256: str,
    expected_release_receipt_record_sha256: str,
) -> None:
    """explicit root escalation의 full proof 뒤에만 unsealed intent를 archive한다."""

    module_name = "_pinvi_m05_hotswap_forensics_unsealed_recovery"
    specification = importlib.util.spec_from_file_location(module_name, forensics)
    if specification is None or specification.loader is None:
        _raise("trusted unsealed forensic recovery primitive is unavailable")
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    try:
        specification.loader.exec_module(module)
        acknowledge = getattr(
            module,
            "acknowledge_unsealed_release_receipt_after_verified_recovery",
            None,
        )
        if not callable(acknowledge):
            _raise("trusted unsealed forensic recovery primitive is unavailable")
        acknowledge(
            Path(_STATE_DIRECTORY),
            operation_id=operation_id,
            verification_sha256=verification_sha256,
            expected_marker_sha256=expected_marker_sha256,
            expected_release_receipt_record_sha256=expected_release_receipt_record_sha256,
        )
    except TrustedHotswapError:
        raise
    except Exception as exc:
        raise TrustedHotswapError(
            "trusted unsealed recovery acknowledgement could not be written"
        ) from exc
    finally:
        sys.modules.pop(module_name, None)


def _forensics_status(forensics: Path, *, allow_absent: bool) -> dict[str, object]:
    arguments = ["status", "--strict", "--state-dir", _STATE_DIRECTORY]
    if allow_absent:
        arguments.append("--allow-absent")
    result = _forensics_command(forensics, arguments)
    if result.returncode != 0:
        _raise("hotswap forensic marker is unavailable")
    try:
        marker = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise TrustedHotswapError("hotswap forensic marker is invalid") from exc
    if not isinstance(marker, dict):
        _raise("hotswap forensic marker is invalid")
    return cast(dict[str, object], marker)


def _read_marker(forensics: Path) -> dict[str, object]:
    return _forensics_status(forensics, allow_absent=False)


def _assert_no_active_marker(forensics: Path) -> None:
    marker = _forensics_status(forensics, allow_absent=True)
    if marker == {"active": False}:
        return
    _raise("unresolved hotswap forensic marker blocks a new hotswap")


def _assert_runner_environment_is_narrow() -> None:
    configured = sorted(
        name for name in _RUNNER_UNSAFE_ENVIRONMENT_KEYS if name in os.environ
    )
    if configured:
        _raise("trusted hotswap refuses inherited runner overrides")


def _target_identity_environment(database_url: str) -> tuple[dict[str, str], str]:
    target_identity_sha256, identity = _identity_sha256_from_psql(database_url)
    environment: dict[str, str] = {}
    for environment_name, identity_name in _TARGET_IDENTITY_ENVIRONMENT:
        value = identity.get(identity_name)
        if not isinstance(value, str):
            _raise("trusted hotswap database identity is invalid")
        environment[environment_name] = value
    return environment, target_identity_sha256


def _safe_root_only_directory(path: Path, *, mode: int) -> Path:
    if not path.is_absolute():
        _raise("trusted hotswap root-only directory is invalid")
    _safe_parent_chain(path.parent)
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError:
        _raise("trusted hotswap root-only directory is unavailable")
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) != mode
        or resolved != path
    ):
        _raise("trusted hotswap root-only directory permissions are invalid")
    return resolved


def _safe_root_only_file_metadata(
    path: Path, *, mode: int, maximum_size: int | None = 16 * 1024
) -> os.stat_result:
    if not path.is_absolute():
        _raise("trusted hotswap root-only file is invalid")
    try:
        metadata = path.lstat()
    except OSError:
        _raise("trusted hotswap root-only file is unavailable")
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) != mode
        or (maximum_size is not None and metadata.st_size > maximum_size)
    ):
        _raise("trusted hotswap root-only file permissions are invalid")
    return metadata


def _safe_root_only_file(
    path: Path, *, mode: int, maximum_size: int | None = 16 * 1024
) -> bytes:
    metadata = _safe_root_only_file_metadata(path, mode=mode, maximum_size=maximum_size)
    try:
        payload = path.read_bytes()
    except OSError:
        _raise("trusted hotswap root-only file is unavailable")
    try:
        after = path.lstat()
    except OSError:
        _raise("trusted hotswap root-only file is unavailable")
    if (
        after.st_ino != metadata.st_ino
        or after.st_dev != metadata.st_dev
        or after.st_size != metadata.st_size
        or after.st_uid != 0
        or stat.S_IMODE(after.st_mode) != mode
    ):
        _raise("trusted hotswap root-only file changed while reading")
    return payload


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    parsed: dict[str, object] = {}
    for name, value in pairs:
        if name in parsed:
            raise ValueError("duplicate JSON key")
        parsed[name] = value
    return parsed


def _configuration_string(
    value: object, *, name: str, pattern: re.Pattern[str] | None = None
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(character.isspace() for character in value)
    ):
        _raise(f"trusted hotswap configuration {name} is invalid")
    if pattern is not None and pattern.fullmatch(value) is None:
        _raise(f"trusted hotswap configuration {name} is invalid")
    return value


def _load_trusted_configuration() -> TrustedHotswapConfiguration:
    """root-owned static config만 root runner의 operation input으로 받아들인다."""

    _safe_parent_chain(_CONFIG_PATH.parent)
    payload = _safe_root_only_file(_CONFIG_PATH, mode=0o600)
    try:
        raw = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise TrustedHotswapError("trusted hotswap configuration is invalid") from exc
    if not isinstance(raw, dict) or set(raw) != _CONFIG_FIELDS:
        _raise("trusted hotswap configuration is invalid")
    source_identity = raw.get("source_identity")
    if (
        not isinstance(source_identity, dict)
        or set(source_identity) != _CONFIG_SOURCE_IDENTITY_FIELDS
    ):
        _raise("trusted hotswap configuration source identity is invalid")

    environment = _configuration_string(raw.get("environment"), name="environment")
    if environment not in _STRICT_ENVIRONMENTS:
        _raise("trusted hotswap configuration environment is invalid")
    trusted_backup_dir = _configuration_string(
        raw.get("trusted_backup_dir"), name="trusted_backup_dir"
    )
    if not Path(trusted_backup_dir).is_absolute():
        _raise("trusted hotswap configuration trusted_backup_dir is invalid")

    source_values: dict[str, str] = {}
    source_patterns = {
        "database_name": re.compile(r"[A-Za-z_][A-Za-z0-9_]*"),
        "database_oid": re.compile(r"[0-9]+"),
        "hostaddr": re.compile(r"[0-9A-Fa-f:.]+"),
        "port": re.compile(r"[0-9]+"),
        "system_identifier": re.compile(r"[0-9]+"),
    }
    for field, pattern in source_patterns.items():
        source_values[field] = _configuration_string(
            source_identity.get(field),
            name=f"source_identity.{field}",
            pattern=pattern,
        )

    return TrustedHotswapConfiguration(
        app_role=_configuration_string(
            raw.get("app_role"), name="app_role", pattern=_ROLE_RE
        ),
        environment=environment,
        fence_database_url=_configuration_string(
            raw.get("fence_database_url"), name="fence_database_url"
        ),
        restore_database_url=_configuration_string(
            raw.get("restore_database_url"), name="restore_database_url"
        ),
        source_database_name=source_values["database_name"],
        source_database_oid=source_values["database_oid"],
        source_hostaddr=source_values["hostaddr"],
        source_port=source_values["port"],
        source_schema=_configuration_string(
            raw.get("source_schema"), name="source_schema", pattern=_SCHEMA_RE
        ),
        source_system_identifier=source_values["system_identifier"],
        trusted_backup_dir=trusted_backup_dir,
    )


def _parse_receipt_timestamp(name: str, value: object) -> datetime:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value)
        is None
    ):
        _raise(f"trusted hotswap drain receipt {name} is invalid")
    try:
        return datetime.fromisoformat(f"{value[:-1]}+00:00").astimezone(UTC)
    except ValueError:
        _raise(f"trusted hotswap drain receipt {name} is invalid")


def _trusted_snapshot_sha256(snapshot: str, trusted_directory: Path) -> str:
    snapshot_path = Path(snapshot)
    if not snapshot_path.is_absolute() or snapshot_path.parent != trusted_directory:
        _raise("trusted hotswap snapshot is outside the trusted backup directory")
    metadata = _safe_root_only_file_metadata(
        snapshot_path, mode=0o600, maximum_size=None
    )
    sidecar = _safe_root_only_file(
        snapshot_path.with_name(f"{snapshot_path.name}.sha256"), mode=0o600
    )
    expected = sidecar.decode("ascii", errors="strict").split(maxsplit=1)
    if len(expected) != 2 or _SHA256_RE.fullmatch(expected[0]) is None:
        _raise("trusted hotswap snapshot checksum sidecar is invalid")
    digest = hashlib.sha256()
    try:
        with snapshot_path.open("rb", buffering=0) as source:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        _raise("trusted hotswap snapshot is unavailable")
    try:
        after = snapshot_path.lstat()
    except OSError:
        _raise("trusted hotswap snapshot is unavailable")
    if (
        after.st_ino != metadata.st_ino
        or after.st_dev != metadata.st_dev
        or after.st_size != metadata.st_size
        or after.st_uid != 0
        or stat.S_IMODE(after.st_mode) != 0o600
    ):
        _raise("trusted hotswap snapshot changed while reading")
    actual = digest.hexdigest()
    if actual != expected[0]:
        _raise("trusted hotswap snapshot checksum failed")
    return actual


def _prepare_trusted_drain_receipt(
    *,
    snapshot: str,
    operation_id: str,
    app_role: str,
    source_schema: str,
    trusted_directory: Path,
) -> tuple[dict[str, object], str]:
    """DB 접속 전 sealed receipt·snapshot·TTL을 fail-closed로 검증한다."""

    _safe_root_only_directory(_DRAIN_RECEIPT_PATH.parent, mode=0o700)
    payload = _safe_root_only_file(_DRAIN_RECEIPT_PATH, mode=0o600)
    try:
        receipt = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustedHotswapError("trusted hotswap drain receipt is invalid") from exc
    required_keys = {
        "app_role",
        "expires_at_utc",
        "operation_id",
        "quiescent",
        "snapshot_sha256",
        "source_schema",
        "target_identity_sha256",
        "verified_at_utc",
        "version",
    }
    if not isinstance(receipt, dict) or set(receipt) != required_keys:
        _raise("trusted hotswap drain receipt is invalid")
    if (
        receipt.get("version") != 1
        or receipt.get("operation_id") != operation_id
        or receipt.get("app_role") != app_role
        or receipt.get("source_schema") != source_schema
        or receipt.get("quiescent") is not True
        or not isinstance(receipt.get("snapshot_sha256"), str)
        or _SHA256_RE.fullmatch(cast(str, receipt["snapshot_sha256"])) is None
        or not isinstance(receipt.get("target_identity_sha256"), str)
        or _SHA256_RE.fullmatch(cast(str, receipt["target_identity_sha256"])) is None
    ):
        _raise("trusted hotswap drain receipt does not match the operation")
    verified_at = _parse_receipt_timestamp(
        "verified_at_utc", receipt.get("verified_at_utc")
    )
    expires_at = _parse_receipt_timestamp(
        "expires_at_utc", receipt.get("expires_at_utc")
    )
    now = datetime.now(UTC)
    if (
        verified_at > now
        or expires_at <= now
        or expires_at < verified_at
        or now - verified_at > _DRAIN_RECEIPT_MAX_AGE
        or expires_at - verified_at > _DRAIN_RECEIPT_MAX_AGE
    ):
        _raise("trusted hotswap drain receipt is expired or has an invalid lifetime")

    snapshot_sha256 = _trusted_snapshot_sha256(snapshot, trusted_directory)
    if receipt["snapshot_sha256"] != snapshot_sha256:
        _raise("trusted hotswap drain receipt does not match the snapshot")
    return cast(dict[str, object], receipt), hashlib.sha256(payload).hexdigest()


def _consume_trusted_drain_receipt(operation_id: str, receipt_sha256: str) -> None:
    """single-use receipt를 marker 전 root-only archive로 link+unlink 한다."""

    if (
        _UUID_RE.fullmatch(operation_id) is None
        or _SHA256_RE.fullmatch(receipt_sha256) is None
    ):
        _raise("trusted hotswap drain receipt consumption input is invalid")
    state_directory = _safe_root_only_directory(_DRAIN_RECEIPT_PATH.parent, mode=0o700)
    payload = _safe_root_only_file(_DRAIN_RECEIPT_PATH, mode=0o600)
    if hashlib.sha256(payload).hexdigest() != receipt_sha256:
        _raise("trusted hotswap drain receipt changed while consuming")
    consumed_directory = state_directory / "consumed-drain-receipts"
    try:
        consumed_directory.mkdir(mode=0o700, exist_ok=True)
    except OSError:
        _raise("trusted hotswap drain receipt archive is unavailable")
    _safe_root_only_directory(consumed_directory, mode=0o700)
    destination = consumed_directory / f"{operation_id}.json"
    try:
        os.link(_DRAIN_RECEIPT_PATH, destination, follow_symlinks=False)
    except FileExistsError:
        _raise("trusted hotswap drain receipt was already consumed")
    except OSError:
        _raise("trusted hotswap drain receipt could not be consumed")
    try:
        os.unlink(_DRAIN_RECEIPT_PATH)
    except OSError:
        _raise("trusted hotswap drain receipt could not be consumed")


def _receipt_timestamp(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _write_trusted_drain_receipt(receipt: dict[str, object]) -> None:
    """root-only receipt를 replace 없이 단 한 번 생성한다."""

    operation_id = receipt.get("operation_id")
    if not isinstance(operation_id, str) or _UUID_RE.fullmatch(operation_id) is None:
        _raise("trusted hotswap drain receipt is invalid")
    state_directory = _safe_root_only_directory(_DRAIN_RECEIPT_PATH.parent, mode=0o700)
    consumed_directory = state_directory / "consumed-drain-receipts"
    try:
        consumed_directory.mkdir(mode=0o700, exist_ok=True)
    except OSError:
        _raise("trusted hotswap drain receipt archive is unavailable")
    _safe_root_only_directory(consumed_directory, mode=0o700)
    if (consumed_directory / f"{operation_id}.json").exists():
        _raise("trusted hotswap drain receipt was already consumed")
    payload = _canonical_json(receipt) + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(_DRAIN_RECEIPT_PATH, flags, 0o600)
    except FileExistsError:
        _raise("trusted hotswap drain receipt is already pending")
    except OSError:
        _raise("trusted hotswap drain receipt could not be written")
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as destination:
            destination.write(payload)
            destination.flush()
            os.fsync(destination.fileno())
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size != len(payload)
        ):
            _raise("trusted hotswap drain receipt permissions are invalid")
    except OSError:
        _raise("trusted hotswap drain receipt could not be written")
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


def _assert_drain_quiescent(database_url: str, app_role: str) -> None:
    """receipt 직전의 DB writer drain·M05 lock 부재를 관찰한다.

    이 관찰은 runner의 DB fence를 대체하지 않는다. 짧은 TTL receipt로 operator가
    reverse proxy/orchestrator drain을 마친 직후 run을 시작하도록 결박하고, run은
    별도로 fence를 적용해 그 사이 재접속도 종료한다.
    """

    output = _run_psql(
        database_url,
        command="""
SELECT json_build_object(
  'advisory_lock_absent', NOT EXISTS (
    SELECT 1 FROM pg_locks
    WHERE locktype = 'advisory' AND classid = 1414679892 AND objid = 1213421392
      AND granted
  ),
  'app_sessions_absent', NOT EXISTS (
    SELECT 1 FROM pg_stat_activity
    WHERE usename = :'app_role' AND pid <> pg_backend_pid()
  )
)::text;
""",
        variables={"app_role": app_role},
        failure="trusted hotswap drain state could not be read",
    )
    try:
        observation = json.loads(output)
    except json.JSONDecodeError as exc:
        raise TrustedHotswapError("trusted hotswap drain state is invalid") from exc
    if observation != {"advisory_lock_absent": True, "app_sessions_absent": True}:
        _raise("trusted hotswap drain state does not prove a quiescent writer")


def _prepare_drain_receipt(args: argparse.Namespace) -> int:
    _strict_environment()
    if not args.confirm:
        _raise("trusted hotswap drain receipt requires --confirm")
    if _UUID_RE.fullmatch(args.operation_id) is None:
        _raise("trusted hotswap drain receipt operation id is invalid")
    configuration = _load_trusted_configuration()
    _, forensics, _ = _canonical_runner_paths()
    _assert_no_active_marker(forensics)
    database_url = pin_database_url(configuration.restore_database_url)
    trusted_directory = _safe_root_only_directory(
        Path(configuration.trusted_backup_dir), mode=0o700
    )
    snapshot_sha256 = _trusted_snapshot_sha256(args.snapshot, trusted_directory)
    _, target_identity_sha256 = _target_identity_environment(database_url)
    _assert_drain_quiescent(database_url, configuration.app_role)
    verified_at = datetime.now(UTC)
    receipt: dict[str, object] = {
        "app_role": configuration.app_role,
        "expires_at_utc": _receipt_timestamp(verified_at + _DRAIN_RECEIPT_MAX_AGE),
        "operation_id": args.operation_id,
        "quiescent": True,
        "snapshot_sha256": snapshot_sha256,
        "source_schema": configuration.source_schema,
        "target_identity_sha256": target_identity_sha256,
        "verified_at_utc": _receipt_timestamp(verified_at),
        "version": 1,
    }
    _write_trusted_drain_receipt(receipt)
    sys.stdout.buffer.write(
        _canonical_json(
            {
                "expires_at_utc": receipt["expires_at_utc"],
                "operation_id": args.operation_id,
                "status": "prepared",
            }
        )
        + b"\n"
    )
    return 0


def _runner_environment(
    configuration: TrustedHotswapConfiguration,
    database_url: str,
    fence_url: str,
    *,
    snapshot: str,
    operation_id: str,
) -> dict[str, str]:
    """root runner에 필요한 immutable operation input만 복사한다."""

    _assert_runner_environment_is_narrow()
    if _UUID_RE.fullmatch(operation_id) is None:
        _raise("trusted hotswap trusted backup directory is missing or invalid")
    trusted_directory = _safe_root_only_directory(
        Path(configuration.trusted_backup_dir), mode=0o700
    )
    receipt, receipt_sha256 = _prepare_trusted_drain_receipt(
        snapshot=snapshot,
        operation_id=operation_id,
        app_role=configuration.app_role,
        source_schema=configuration.source_schema,
        trusted_directory=trusted_directory,
    )
    target_environment, target_identity_sha256 = _target_identity_environment(
        database_url
    )
    if receipt["target_identity_sha256"] != target_identity_sha256:
        _raise("trusted hotswap drain receipt does not match the target")
    _consume_trusted_drain_receipt(operation_id, receipt_sha256)

    environment: dict[str, str] = {
        **_SAFE_ENVIRONMENT,
        "PINVI_BACKUP_SCHEMA": configuration.source_schema,
        "PINVI_ENVIRONMENT": configuration.environment,
        "PINVI_RESTORE_ALLOW_NO_DRAIN": "1",
        "PINVI_RESTORE_API_TRIGGER": "1",
        "PINVI_RESTORE_APP_ROLE": configuration.app_role,
        "PINVI_RESTORE_DATABASE_URL": database_url,
        "PINVI_RESTORE_DRAIN_VERIFIED": "1",
        "PINVI_RESTORE_FENCE_DATABASE_URL": fence_url,
        "PINVI_RESTORE_HOTSWAP_EXECUTE": "1",
        "PINVI_RESTORE_TRUSTED_BACKUP_DIR": str(trusted_directory),
        "PINVI_M05_FORENSICS_DRAIN_RECEIPT_SHA256": receipt_sha256,
        "PINVI_M05_FORENSICS_OPERATION_ID": operation_id,
        "PINVI_M05_FORENSICS_STATE_DIR": _STATE_DIRECTORY,
    }
    for environment_name, configuration_name, _ in _SOURCE_IDENTITY_CONFIGURATION:
        environment[environment_name] = getattr(configuration, configuration_name)

    trusted_tools = (
        ("PINVI_RESTORE_BASH", _trusted_bash_path()),
        ("PINVI_RESTORE_PG_RESTORE", _trusted_pg_restore_path()),
        ("PINVI_RESTORE_PSQL", _trusted_psql_path()),
    )
    for prefix, path in trusted_tools:
        environment[f"{prefix}_BIN"] = str(path)
        environment[f"{prefix}_SHA256"] = _trusted_file_sha256(path)
    environment.update(target_environment)
    return environment


def _run_psql(
    database_url: str,
    *,
    command: str | None = None,
    file: Path | None = None,
    variables: dict[str, str] | None = None,
    failure: str,
) -> str:
    if (command is None) == (file is None):
        _raise("trusted recovery psql invocation is invalid")
    arguments = [
        str(_trusted_psql_path()),
        "--no-psqlrc",
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-Atq",
        "--dbname",
        database_url,
    ]
    for name, value in sorted((variables or {}).items()):
        arguments.append(f"--set={name}={value}")
    if command is not None:
        # psql does not interpolate :variables in --command text. Feed the
        # fixed SQL through stdin so recovery observations use the validated
        # psql variables instead of sending an unexpanded colon token.
        arguments.extend(["--file", "-"])
    if file is not None:
        arguments.extend(["--file", str(file)])
    result = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        input=command,
        text=True,
        # Every invocation in this entrypoint is an independent observation.
        # This server-side GUC makes an accidental write fail even if a future
        # query stops looking like a SELECT.
        env={**_SAFE_ENVIRONMENT, "PGOPTIONS": "-c default_transaction_read_only=on"},
    )
    if result.returncode != 0:
        _raise(failure)
    return result.stdout


def _identity_sha256_from_psql(database_url: str) -> tuple[str, dict[str, object]]:
    identity_sql = """
SELECT current_database() || '|' || d.oid::text || '|' ||
       (pg_control_system()).system_identifier::text || '|' ||
       COALESCE(host(inet_server_addr()), '') || '|' || inet_server_port()::text
FROM pg_database d
WHERE d.datname = current_database();
"""
    value = _run_psql(
        database_url,
        command=identity_sql,
        failure="trusted recovery database identity could not be read",
    ).strip()
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


def _assert_fence_database_identity(
    fence_database_url: str, fields: dict[str, object]
) -> str:
    """receipt/topology 관찰도 marker가 결박한 동일 target DB에서만 허용한다."""

    actual_target, _ = _identity_sha256_from_psql(fence_database_url)
    if actual_target != fields["expected_target"]:
        _raise("trusted recovery fence database identity does not match the marker")
    return actual_target


def _recovery_marker_fields(marker: dict[str, object]) -> dict[str, object]:
    """helper schema 검증 뒤에도 recovery에 필요한 fields를 독립적으로 좁힌다."""

    operation_id = marker.get("operation_id")
    source_schema = marker.get("source_schema")
    previous_schema = marker.get("previous_schema")
    restore_schema = marker.get("restore_schema")
    app_role = marker.get("app_role")
    fence_role = marker.get("fence_executor_role")
    script_sha256 = marker.get("script_sha256")
    snapshot_sha256 = marker.get("snapshot_sha256")
    drain_receipt_sha256 = marker.get("drain_receipt_sha256")
    pg_restore_list_sha256 = marker.get("pg_restore_list_sha256")
    source_identity_sha256 = marker.get("source_identity_sha256")
    expected_target = marker.get("target_identity_sha256")
    expected_topology = marker.get("acl_topology_sha256")
    source_oid = marker.get("source_schema_oid_before")
    state = marker.get("state")
    recovery_required = marker.get("recovery_required")
    public_connect_was_granted = marker.get("public_connect_was_granted")
    grants = marker.get("connect_restore_grants")
    restore_executor_role = marker.get("restore_executor_role")
    restore_executor_grants = marker.get("restore_executor_connect_restore_grants")
    if (
        not isinstance(operation_id, str)
        or _UUID_RE.fullmatch(operation_id) is None
        or not isinstance(source_schema, str)
        or _SCHEMA_RE.fullmatch(source_schema) is None
        or not isinstance(previous_schema, str)
        or _SCHEMA_RE.fullmatch(previous_schema) is None
        or not isinstance(restore_schema, str)
        or _SCHEMA_RE.fullmatch(restore_schema) is None
        or not isinstance(app_role, str)
        or _ROLE_RE.fullmatch(app_role) is None
        or not isinstance(fence_role, str)
        or _ROLE_RE.fullmatch(fence_role) is None
        or not isinstance(script_sha256, str)
        or _SHA256_RE.fullmatch(script_sha256) is None
        or not isinstance(snapshot_sha256, str)
        or _SHA256_RE.fullmatch(snapshot_sha256) is None
        or not isinstance(drain_receipt_sha256, str)
        or _SHA256_RE.fullmatch(drain_receipt_sha256) is None
        or not isinstance(pg_restore_list_sha256, str)
        or _SHA256_RE.fullmatch(pg_restore_list_sha256) is None
        or not isinstance(source_identity_sha256, str)
        or _SHA256_RE.fullmatch(source_identity_sha256) is None
        or not isinstance(restore_executor_role, str)
        or _ROLE_RE.fullmatch(restore_executor_role) is None
        or not isinstance(expected_target, str)
        or _SHA256_RE.fullmatch(expected_target) is None
        or not isinstance(expected_topology, str)
        or _SHA256_RE.fullmatch(expected_topology) is None
        or type(source_oid) is not int
        or source_oid < 1
        or state not in {"prepared", "fence_release_intent"}
        or type(recovery_required) is not bool
        or type(public_connect_was_granted) is not bool
        or not isinstance(grants, list)
        or not isinstance(restore_executor_grants, list)
    ):
        _raise("hotswap forensic marker recovery fields are invalid")
    if len(
        {source_schema, previous_schema, restore_schema}
    ) != 3 or restore_executor_role in {app_role, fence_role}:
        _raise("hotswap forensic marker recovery fields are invalid")

    def normalize_grants(
        value: list[object], *, expected_role: str
    ) -> list[dict[str, object]]:
        normalized: list[dict[str, object]] = []
        previous_role = ""
        for grant in value:
            if not isinstance(grant, dict) or set(grant) != {"grant_option", "role"}:
                _raise("hotswap forensic marker recovery fields are invalid")
            role = grant.get("role")
            grant_option = grant.get("grant_option")
            if (
                not isinstance(role, str)
                or _ROLE_RE.fullmatch(role) is None
                or role != expected_role
                or type(grant_option) is not bool
                or role <= previous_role
            ):
                _raise("hotswap forensic marker recovery fields are invalid")
            normalized.append({"grant_option": grant_option, "role": role})
            previous_role = role
        return normalized

    normalized_grants = normalize_grants(grants, expected_role=app_role)
    normalized_restore_executor_grants = normalize_grants(
        restore_executor_grants, expected_role=restore_executor_role
    )
    fields: dict[str, object] = {
        "app_role": app_role,
        "connect_restore_grants": normalized_grants,
        "expected_target": expected_target,
        "fence_role": fence_role,
        "drain_receipt_sha256": drain_receipt_sha256,
        "operation_id": operation_id,
        "pg_restore_list_sha256": pg_restore_list_sha256,
        "previous_schema": previous_schema,
        "public_connect_was_granted": public_connect_was_granted,
        "recovery_required": recovery_required,
        "restore_executor_connect_restore_grants": normalized_restore_executor_grants,
        "restore_executor_role": restore_executor_role,
        "restore_schema": restore_schema,
        "source_oid": source_oid,
        "source_identity_sha256": source_identity_sha256,
        "source_schema": source_schema,
        "script_sha256": script_sha256,
        "snapshot_sha256": snapshot_sha256,
        "state": state,
        "pre_release_topology_sha256": expected_topology,
        "topology_sha256": expected_topology,
    }
    if state == "prepared":
        if recovery_required:
            _raise("recovery-latched prepared marker cannot be acknowledged")
        return fields

    terminal_schema_mode = marker.get("terminal_schema_mode")
    if terminal_schema_mode != "switched":
        _raise("hotswap forensic marker terminal fields are invalid")
    fields["terminal_schema_mode"] = terminal_schema_mode
    app_oid = marker.get("app_schema_oid_after_switch")
    previous_oid = marker.get("previous_schema_oid_after_switch")
    restore_oid = marker.get("restore_schema_oid")
    if (
        type(app_oid) is not int
        or type(previous_oid) is not int
        or type(restore_oid) is not int
        or app_oid < 1
        or previous_oid < 1
        or restore_oid < 1
        or app_oid != restore_oid
        or previous_oid != source_oid
    ):
        _raise("hotswap forensic marker switch matrix is invalid")
    fields["app_oid"] = app_oid
    fields["previous_oid"] = previous_oid
    fields["restore_oid"] = restore_oid
    return fields


def _topology_sha256(
    database_url: str, marker: dict[str, object], topology: Path
) -> str:
    fields = _recovery_marker_fields(marker)
    output = _run_psql(
        database_url,
        file=topology,
        variables={
            "app_role": cast(str, fields["app_role"]),
            "fence_role": cast(str, fields["fence_role"]),
            "previous_schema": cast(str, fields["previous_schema"]),
            "restore_schema": cast(str, fields["restore_schema"]),
            "source_schema": cast(str, fields["source_schema"]),
        },
        failure="trusted recovery ACL topology could not be read",
    ).strip()
    if _SHA256_RE.fullmatch(output) is None:
        _raise("trusted recovery ACL topology is invalid")
    return output


def _read_release_receipt(
    marker: dict[str, object], *, marker_sha256: str, fence_database_url: str
) -> dict[str, object]:
    """fence DB owner만 읽을 수 있는 0101 release receipt를 marker에 결박한다."""

    fields = _recovery_marker_fields(marker)
    if fields["state"] == "prepared":
        _raise("prepared marker does not have a release receipt")
    _assert_fence_database_identity(fence_database_url, fields)
    receipt_sql = """
SELECT json_build_object(
  'receipt', to_jsonb(receipt),
  'record_sha256_valid', ops.verify_m05_hotswap_release_receipt(
    receipt.operation_id, receipt.marker_sha256
  ),
  'session_is_configured_fence_database_owner', session_user = current_user
    AND current_user = :'fence_role'::name
    AND current_user = (
      SELECT database_row.datdba::regrole::text
      FROM pg_database database_row
      WHERE database_row.datname = current_database()
    )
)::text
FROM ops.m05_hotswap_release_receipts receipt
WHERE receipt.operation_id = :'operation_id'::uuid;
"""
    output = _run_psql(
        fence_database_url,
        command=receipt_sql,
        variables={
            "fence_role": cast(str, fields["fence_role"]),
            "operation_id": cast(str, fields["operation_id"]),
        },
        failure="trusted recovery release receipt could not be read",
    ).strip()
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise TrustedHotswapError(
            "trusted recovery release receipt is invalid"
        ) from exc
    if not isinstance(payload, dict) or set(payload) != {
        "receipt",
        "record_sha256_valid",
        "session_is_configured_fence_database_owner",
    }:
        _raise("trusted recovery release receipt is invalid")
    receipt = payload.get("receipt")
    if (
        not isinstance(receipt, dict)
        or payload.get("record_sha256_valid") is not True
        or payload.get("session_is_configured_fence_database_owner") is not True
    ):
        _raise("trusted recovery release receipt is invalid")
    required = {
        "operation_id",
        "marker_sha256",
        "script_sha256",
        "snapshot_sha256",
        "drain_receipt_sha256",
        "pg_restore_list_sha256",
        "target_identity_sha256",
        "source_identity_sha256",
        "source_schema",
        "restore_schema",
        "previous_schema",
        "app_role",
        "fence_role",
        "restore_executor_role",
        "source_schema_oid_before",
        "restore_schema_oid",
        "app_schema_oid_after_switch",
        "previous_schema_oid_after_switch",
        "connect_restore_grants",
        "restore_executor_connect_restore_grants",
        "public_connect_was_granted",
        "pre_release_acl_topology_sha256",
        "post_release_acl_topology_sha256",
        "observed_at",
        "record_sha256",
    }
    if set(receipt) != required:
        _raise("trusted recovery release receipt is invalid")
    expected: dict[str, object] = {
        "operation_id": fields["operation_id"],
        "marker_sha256": marker_sha256,
        "script_sha256": fields["script_sha256"],
        "snapshot_sha256": fields["snapshot_sha256"],
        "drain_receipt_sha256": fields["drain_receipt_sha256"],
        "pg_restore_list_sha256": fields["pg_restore_list_sha256"],
        "target_identity_sha256": fields["expected_target"],
        "source_identity_sha256": fields["source_identity_sha256"],
        "source_schema": fields["source_schema"],
        "restore_schema": fields["restore_schema"],
        "previous_schema": fields["previous_schema"],
        "app_role": fields["app_role"],
        "fence_role": fields["fence_role"],
        "restore_executor_role": fields["restore_executor_role"],
        "source_schema_oid_before": fields["source_oid"],
        "restore_schema_oid": fields["restore_oid"],
        "app_schema_oid_after_switch": fields["app_oid"],
        "previous_schema_oid_after_switch": fields["previous_oid"],
        "connect_restore_grants": fields["connect_restore_grants"],
        "restore_executor_connect_restore_grants": fields[
            "restore_executor_connect_restore_grants"
        ],
        "public_connect_was_granted": fields["public_connect_was_granted"],
        "pre_release_acl_topology_sha256": fields["pre_release_topology_sha256"],
    }
    if any(receipt[name] != value for name, value in expected.items()):
        _raise("trusted recovery release receipt does not match the marker")
    post_topology = receipt.get("post_release_acl_topology_sha256")
    record_sha256 = receipt.get("record_sha256")
    observed_at = receipt.get("observed_at")
    if (
        not isinstance(post_topology, str)
        or _SHA256_RE.fullmatch(post_topology) is None
        or not isinstance(record_sha256, str)
        or _SHA256_RE.fullmatch(record_sha256) is None
        or not isinstance(observed_at, str)
        or not observed_at
    ):
        _raise("trusted recovery release receipt is invalid")
    return cast(dict[str, object], receipt)


def _release_receipt_topology_sha256(
    fence_database_url: str, fields: dict[str, object]
) -> tuple[str, str]:
    """receipt commit과 같은 DB canonical function으로 terminal topology를 재계산한다."""

    fence_target_identity_sha256 = _assert_fence_database_identity(
        fence_database_url, fields
    )
    output = _run_psql(
        fence_database_url,
        command="""
SELECT ops.m05_hotswap_release_topology_sha256(
  :'source_schema'::name,
  :'previous_schema'::name,
  :'restore_schema'::name,
  :'app_role'::name,
  :'fence_role'::name,
  :'restore_executor_role'::name
);
""",
        variables={
            "app_role": cast(str, fields["app_role"]),
            "fence_role": cast(str, fields["fence_role"]),
            "previous_schema": cast(str, fields["previous_schema"]),
            "restore_executor_role": cast(str, fields["restore_executor_role"]),
            "restore_schema": cast(str, fields["restore_schema"]),
            "source_schema": cast(str, fields["source_schema"]),
        },
        failure="trusted recovery release receipt topology could not be read",
    ).strip()
    if _SHA256_RE.fullmatch(output) is None:
        _raise("trusted recovery release receipt topology is invalid")
    return output, fence_target_identity_sha256


def _safe_recovery_observation(
    marker: dict[str, object],
    database_url: str,
    topology: Path,
    *,
    marker_sha256: str,
    receipt: dict[str, object] | None,
    fence_database_url: str | None,
) -> str:
    fields = _recovery_marker_fields(marker)
    actual_target, _ = _identity_sha256_from_psql(database_url)
    if actual_target != fields["expected_target"]:
        _raise("trusted recovery database identity does not match the marker")

    observation_sql = """
SELECT json_build_object(
  'advisory_lock_absent', NOT EXISTS (
    SELECT 1 FROM pg_locks
    WHERE locktype = 'advisory' AND classid = 1414679892 AND objid = 1213421392 AND granted
  ),
  'app_connect', has_database_privilege(:'app_role', current_database(), 'CONNECT'),
  'app_database_create_absent', NOT has_database_privilege(
    :'app_role', current_database(), 'CREATE'
  ),
  'app_oid', COALESCE((SELECT oid::text FROM pg_namespace WHERE nspname = :'source_schema'), ''),
  'app_role_safe', EXISTS (
    SELECT 1
    FROM pg_roles role_row
    WHERE role_row.rolname = :'app_role'
      AND role_row.rolcanlogin
      AND NOT role_row.rolsuper
      AND NOT role_row.rolinherit
      AND NOT role_row.rolcreaterole
      AND NOT role_row.rolcreatedb
      AND NOT role_row.rolreplication
      AND NOT role_row.rolbypassrls
      AND NOT EXISTS (
        SELECT 1 FROM pg_auth_members membership
        WHERE membership.member = role_row.oid OR membership.roleid = role_row.oid
      )
  ),
  'app_public_create_absent', NOT has_schema_privilege(
    :'app_role', 'public', 'CREATE'
  ),
  'app_usage', has_schema_privilege(:'app_role', :'source_schema', 'USAGE'),
  'connect_restore_grants', COALESCE((
    SELECT json_agg(
      json_build_object('grant_option', acl.is_grantable, 'role', role_row.rolname)
      ORDER BY role_row.rolname
    )
    FROM pg_database database_row
    CROSS JOIN LATERAL aclexplode(
      COALESCE(database_row.datacl, acldefault('d', database_row.datdba))
    ) AS acl
    JOIN pg_roles AS role_row ON role_row.oid = acl.grantee
    WHERE database_row.datname = current_database()
      AND acl.privilege_type = 'CONNECT'
      AND role_row.rolname = :'app_role'
  ), '[]'::json),
  'fence_role_safe', EXISTS (
    SELECT 1
    FROM pg_roles role_row
    WHERE role_row.rolname = :'fence_role'
      AND role_row.rolcanlogin
      AND NOT role_row.rolsuper
      AND NOT role_row.rolinherit
      AND NOT role_row.rolcreaterole
      AND NOT role_row.rolcreatedb
      AND NOT role_row.rolreplication
      AND NOT role_row.rolbypassrls
      AND NOT EXISTS (
        SELECT 1 FROM pg_auth_members membership
        WHERE membership.member = role_row.oid OR membership.roleid = role_row.oid
      )
  ),
  'previous_oid', COALESCE((SELECT oid::text FROM pg_namespace WHERE nspname = :'previous_schema'), ''),
  'public_connect_granted', EXISTS (
    SELECT 1
    FROM pg_database database_row
    CROSS JOIN LATERAL aclexplode(
      COALESCE(database_row.datacl, acldefault('d', database_row.datdba))
    ) AS acl
    WHERE database_row.datname = current_database()
      AND acl.grantee = 0
      AND acl.privilege_type = 'CONNECT'
  ),
  'restore_executor_role', current_user,
  'restore_executor_connect_restore_grants', COALESCE((
    SELECT json_agg(
      json_build_object('grant_option', acl.is_grantable, 'role', role_row.rolname)
      ORDER BY role_row.rolname
    )
    FROM pg_database database_row
    CROSS JOIN LATERAL aclexplode(
      COALESCE(database_row.datacl, acldefault('d', database_row.datdba))
    ) AS acl
    JOIN pg_roles AS role_row ON role_row.oid = acl.grantee
    WHERE database_row.datname = current_database()
      AND acl.privilege_type = 'CONNECT'
      AND role_row.rolname = current_user
  ), '[]'::json),
  'restore_executor_safe', current_user <> :'app_role'
    AND current_user <> :'fence_role'
    AND EXISTS (
      SELECT 1
      FROM pg_roles role_row
      WHERE role_row.rolname = current_user
        AND NOT role_row.rolsuper
        AND NOT role_row.rolcreaterole
        AND NOT role_row.rolcreatedb
        AND NOT role_row.rolreplication
        AND NOT role_row.rolbypassrls
    ),
  'restore_oid', COALESCE((SELECT oid::text FROM pg_namespace WHERE nspname = :'restore_schema'), '')
)::text;
"""
    output = _run_psql(
        database_url,
        command=observation_sql,
        variables={
            "app_role": cast(str, fields["app_role"]),
            "fence_role": cast(str, fields["fence_role"]),
            "previous_schema": cast(str, fields["previous_schema"]),
            "restore_schema": cast(str, fields["restore_schema"]),
            "source_schema": cast(str, fields["source_schema"]),
        },
        failure="trusted recovery state could not be read",
    )
    try:
        observation = json.loads(output)
    except json.JSONDecodeError as exc:
        raise TrustedHotswapError("trusted recovery state is invalid") from exc
    if not isinstance(observation, dict) or set(observation) != {
        "advisory_lock_absent",
        "app_connect",
        "app_database_create_absent",
        "app_oid",
        "app_role_safe",
        "app_public_create_absent",
        "app_usage",
        "connect_restore_grants",
        "fence_role_safe",
        "previous_oid",
        "public_connect_granted",
        "restore_executor_connect_restore_grants",
        "restore_executor_role",
        "restore_executor_safe",
        "restore_oid",
    }:
        _raise("trusted recovery state is invalid")
    string_keys = {"app_oid", "previous_oid", "restore_executor_role", "restore_oid"}
    boolean_keys = {
        "advisory_lock_absent",
        "app_connect",
        "app_database_create_absent",
        "app_role_safe",
        "app_public_create_absent",
        "app_usage",
        "fence_role_safe",
        "public_connect_granted",
        "restore_executor_safe",
    }
    state = cast(str, fields["state"])
    if (
        any(not isinstance(observation[key], str) for key in string_keys)
        or any(type(observation[key]) is not bool for key in boolean_keys)
        or not isinstance(observation["connect_restore_grants"], list)
        or not isinstance(observation["restore_executor_connect_restore_grants"], list)
        or _ROLE_RE.fullmatch(cast(str, observation["restore_executor_role"])) is None
        or observation["advisory_lock_absent"] is not True
        or observation["app_connect"] is not True
        or observation["app_database_create_absent"] is not True
        or observation["app_role_safe"] is not True
        or observation["app_public_create_absent"] is not True
        or observation["app_usage"] is not True
        or observation["fence_role_safe"] is not True
        or observation["restore_executor_safe"] is not True
        or observation["restore_executor_role"] != fields["restore_executor_role"]
    ):
        _raise("trusted recovery state does not prove a safe writer release")
    if state != "prepared" and (
        observation["connect_restore_grants"] != fields["connect_restore_grants"]
        or observation["restore_executor_connect_restore_grants"]
        != fields["restore_executor_connect_restore_grants"]
        or observation["public_connect_granted"] != fields["public_connect_was_granted"]
    ):
        _raise("trusted recovery database CONNECT grants do not match the marker")
    fence_target_identity_sha256: str | None = None
    if state == "prepared":
        if (
            observation["app_oid"] != str(fields["source_oid"])
            or observation["previous_oid"] != ""
            or observation["restore_oid"] != ""
        ):
            _raise("trusted recovery state does not prove an untouched prepared marker")
    else:
        if (
            observation["app_oid"] != str(fields["app_oid"])
            or observation["previous_oid"] != str(fields["previous_oid"])
            or observation["restore_oid"] != ""
        ):
            _raise("trusted recovery state does not prove a released switched schema")

    if state == "prepared":
        actual_topology = _topology_sha256(database_url, marker, topology)
        if actual_topology != fields["topology_sha256"]:
            _raise("trusted recovery ACL topology does not match the marker")
    else:
        if receipt is None or fence_database_url is None:
            _raise("trusted recovery terminal marker is missing its release receipt")
        actual_topology, fence_target_identity_sha256 = _release_receipt_topology_sha256(
            fence_database_url, fields
        )
        receipt_topology = receipt.get("post_release_acl_topology_sha256")
        if actual_topology != receipt_topology:
            _raise(
                "trusted recovery release receipt topology does not match the database"
            )
    verification: dict[str, object] = {
        "marker_sha256": marker_sha256,
        "marker_state": state,
        "observation": observation,
        "operation_id": fields["operation_id"],
        "target_identity_sha256": actual_target,
        "topology_sha256": actual_topology,
    }
    if state == "fence_release_intent":
        verification["terminal_schema_mode"] = fields["terminal_schema_mode"]
    if receipt is not None:
        if fence_target_identity_sha256 is None:
            _raise("trusted recovery terminal fence database identity is unavailable")
        verification["fence_database_identity_sha256"] = (
            fence_target_identity_sha256
        )
        verification["fence_database_role"] = fields["fence_role"]
        verification["release_receipt_record_sha256"] = receipt["record_sha256"]
        verification["release_receipt_topology_sha256"] = receipt[
            "post_release_acl_topology_sha256"
        ]
    return hashlib.sha256(_canonical_json(verification)).hexdigest()


def _run(args: argparse.Namespace) -> int:
    _strict_environment()
    configuration = _load_trusted_configuration()
    runner, forensics, _ = _canonical_runner_paths()
    _assert_no_active_marker(forensics)
    database_url = pin_database_url(configuration.restore_database_url)
    fence_url = pin_database_url(configuration.fence_database_url)
    environment = _runner_environment(
        configuration,
        database_url,
        fence_url,
        snapshot=args.snapshot,
        operation_id=args.operation_id,
    )
    bash = _trusted_bash_path()
    os.execve(
        str(bash),
        [
            str(bash),
            str(runner),
            "run",
            args.snapshot,
            args.restore_schema,
            args.previous_schema,
        ],
        environment,
    )
    return 3


def _status(_args: argparse.Namespace) -> int:
    _strict_environment()
    _load_trusted_configuration()
    _runner, forensics, _topology = _canonical_runner_paths()
    marker = _read_marker(forensics)
    sys.stdout.buffer.write(_canonical_json(marker) + b"\n")
    return 0


def _recover(args: argparse.Namespace) -> int:
    _strict_environment()
    if not args.confirm:
        _raise("trusted recovery requires --confirm")
    escalate_unsealed_release_receipt = bool(
        getattr(args, "escalate_unsealed_release_receipt", False)
    )
    expected_unsealed_marker_sha256 = getattr(args, "expected_marker_sha256", None)
    if escalate_unsealed_release_receipt and (
        not isinstance(expected_unsealed_marker_sha256, str)
        or _SHA256_RE.fullmatch(expected_unsealed_marker_sha256) is None
    ):
        _raise("unsealed release receipt escalation requires --expected-marker-sha256")
    if (
        not escalate_unsealed_release_receipt
        and expected_unsealed_marker_sha256 is not None
    ):
        _raise(
            "--expected-marker-sha256 is only valid with unsealed release receipt escalation"
        )
    configuration = _load_trusted_configuration()
    _, forensics, topology = _canonical_runner_paths()
    marker = _read_marker(forensics)
    if marker.get("operation_id") != args.operation_id:
        _raise("trusted recovery operation does not match the active marker")
    if marker.get("state") not in {
        "prepared",
        "fence_release_intent",
    }:
        _raise("trusted recovery only acknowledges a proven marker boundary")
    if marker.get("recovery_required") is not False:
        _raise("trusted recovery refuses a recovery-latched marker")
    if escalate_unsealed_release_receipt:
        if marker.get("state") != "fence_release_intent":
            _raise("unsealed release receipt escalation requires a terminal intent")
        ledger_proof = _assert_unsealed_release_receipt_escalation_history(
            forensics, operation_id=args.operation_id
        )
    else:
        ledger_proof = _assert_current_history_consistent_for_recovery(
            forensics, operation_id=args.operation_id
        )
    marker_sha256 = cast(str, ledger_proof["marker_sha256"])
    if hashlib.sha256(_canonical_json(marker)).hexdigest() != marker_sha256:
        _raise("trusted recovery marker changed while its history was verified")
    if (
        escalate_unsealed_release_receipt
        and marker_sha256 != expected_unsealed_marker_sha256
    ):
        _raise("unsealed release receipt marker does not match explicit confirmation")
    database_url = pin_database_url(configuration.restore_database_url)
    state = marker.get("state")
    fence_database_url: str | None = None
    receipt: dict[str, object] | None = None
    if state != "prepared":
        fence_database_url = pin_database_url(configuration.fence_database_url)
        receipt = _read_release_receipt(
            marker,
            marker_sha256=marker_sha256,
            fence_database_url=fence_database_url,
        )
        certified_receipt_record_sha256 = ledger_proof["release_receipt_record_sha256"]
        if (
            certified_receipt_record_sha256 is not None
            and receipt.get("record_sha256") != certified_receipt_record_sha256
        ):
            _raise(
                "trusted recovery release receipt does not match its forensic evidence"
            )
    verification_sha256 = _safe_recovery_observation(
        marker,
        database_url,
        topology,
        marker_sha256=marker_sha256,
        receipt=receipt,
        fence_database_url=fence_database_url,
    )
    if escalate_unsealed_release_receipt:
        if receipt is None or not isinstance(receipt.get("record_sha256"), str):
            _raise(
                "unsealed release receipt escalation could not bind the database receipt"
            )
        prior_root_verification_sha256 = ledger_proof[
            "root_unsealed_release_receipt_verification_sha256"
        ]
        if (
            prior_root_verification_sha256 is not None
            and prior_root_verification_sha256 != verification_sha256
        ):
            _raise(
                "unsealed release receipt root verification does not match the current read-only proof"
            )
        _acknowledge_unsealed_release_receipt_after_verified_recovery(
            forensics,
            operation_id=args.operation_id,
            verification_sha256=verification_sha256,
            expected_marker_sha256=marker_sha256,
            expected_release_receipt_record_sha256=cast(str, receipt["record_sha256"]),
        )
    else:
        _acknowledge_after_verified_recovery(
            forensics,
            operation_id=args.operation_id,
            verification_sha256=verification_sha256,
            expected_marker_sha256=marker_sha256,
            expected_release_receipt_record_sha256=cast(
                str | None, ledger_proof["release_receipt_record_sha256"]
            ),
        )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PinVi trusted hotswap entrypoint")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_drain = commands.add_parser("prepare-drain")
    prepare_drain.add_argument("--operation-id", required=True)
    prepare_drain.add_argument("--confirm", action="store_true")
    prepare_drain.add_argument("snapshot")
    run = commands.add_parser("run")
    run.add_argument("--operation-id", required=True)
    run.add_argument("snapshot")
    run.add_argument("restore_schema")
    run.add_argument("previous_schema")
    commands.add_parser("status")
    recover = commands.add_parser("recover")
    recover.add_argument("--operation-id", required=True)
    recover.add_argument("--confirm", action="store_true")
    recover.add_argument("--escalate-unsealed-release-receipt", action="store_true")
    recover.add_argument("--expected-marker-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        handlers = {
            "prepare-drain": _prepare_drain_receipt,
            "run": _run,
            "status": _status,
            "recover": _recover,
        }
        return handlers[args.command](args)
    except TrustedHotswapError as exc:
        print(f"trusted hotswap failed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
