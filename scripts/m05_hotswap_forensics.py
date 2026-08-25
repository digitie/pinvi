#!/usr/bin/env python3
"""M05 schema-swap의 root-only forensic state를 안전하게 보관한다.

이 파일은 shell hotswap runner가 쓰는 작은 persistence primitive다.  staging/production
경로는 고정된 state directory 아래에서만 동작하며, URL·password·token·host 원문은
입력 schema 자체가 허용하지 않는다.  ``current.json``은 현재 unresolved operation을
fail-close하기 위한 편의 포인터이고, ``operations/<operation-id>.jsonl``은 상태 전이의
append-only forensic record다.

복구 acknowledgement는 별도 trusted host entrypoint가 read-only DB 검증을 끝낸 뒤에만
기록한다. 이 helper는 임의 SQL을 실행하거나 M05 runtime lease를 발급하지 않는다.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, NoReturn, cast

DEFAULT_STATE_DIRECTORY: Final = Path("/var/lib/pinvi/restore-forensics")
_CURRENT_NAME: Final = "current.json"
_LOCK_NAME: Final = ".state.lock"
_OPERATIONS_NAME: Final = "operations"
_RECOVERY_NAME: Final = "recovery"
_MAX_DOCUMENT_BYTES: Final = 64 * 1024
_MAX_HISTORY_LINE_BYTES: Final = 16 * 1024
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}")
_ROLE_RE: Final = re.compile(r"[a-z_][a-z0-9_]*")
_SCHEMA_RE: Final = re.compile(r"[a-z_][a-z0-9_]*")
_CODE_RE: Final = re.compile(r"[a-z][a-z0-9_]{0,63}")
_UUID_RE: Final = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_LOCK_KEY: Final = "1414679892:1213421392"
_RELEASE_RECEIPT_SEAL_TYPE: Final = "release_receipt_committed"
_ROOT_UNSEALED_RELEASE_RECEIPT_VERIFICATION_TYPE: Final = (
    "root_unsealed_release_receipt_verified"
)
_STATE_ORDER: Final = (
    "prepared",
    "fence_intent",
    "fence_applied",
    "restore_ready",
    "switched",
    "fence_release_intent",
)
_STATES: Final = frozenset(_STATE_ORDER)
_NEXT_STATES: Final = {
    "prepared": frozenset({"fence_intent"}),
    "fence_intent": frozenset({"fence_applied"}),
    "fence_applied": frozenset({"restore_ready"}),
    "restore_ready": frozenset({"switched"}),
    "switched": frozenset({"fence_release_intent"}),
}
MarkerState = Literal[
    "prepared",
    "fence_intent",
    "fence_applied",
    "restore_ready",
    "switched",
    "fence_release_intent",
]


class ForensicsError(RuntimeError):
    """Forensic state를 안전하게 읽거나 쓸 수 없을 때 발생한다."""


class _DuplicateJsonKeyError(ValueError):
    """JSON key ambiguity는 forensic evidence에서 허용하지 않는다."""


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateJsonKeyError
        value[key] = item
    return value


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _raise(message: str) -> NoReturn:
    raise ForensicsError(message)


def _validate_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _raise(f"forensic marker {field} is invalid")
    return value


def _validate_identifier(value: object, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        _raise(f"forensic marker {field} is invalid")
    return value


def _validate_positive_int(value: object, field: str) -> int:
    if type(value) is not int or value < 1:
        _raise(f"forensic marker {field} is invalid")
    return value


def _validate_uuid(value: object, field: str = "operation_id") -> str:
    if not isinstance(value, str) or _UUID_RE.fullmatch(value) is None:
        _raise(f"forensic marker {field} is invalid")
    return value


def _validate_role_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or _ROLE_RE.fullmatch(item) is None for item in value
    ):
        _raise(f"forensic marker {field} is invalid")
    roles = cast(list[str], value)
    if roles != sorted(set(roles)):
        _raise(f"forensic marker {field} is not canonical")
    return roles


def _validate_connect_restore_grants(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        _raise("forensic marker connect_restore_grants is invalid")
    grants: list[dict[str, object]] = []
    previous_role = ""
    for item in value:
        if not isinstance(item, dict) or set(item) != {"grant_option", "role"}:
            _raise("forensic marker connect_restore_grants is invalid")
        role = _validate_identifier(item.get("role"), "connect restore role", _ROLE_RE)
        if type(item.get("grant_option")) is not bool or role <= previous_role:
            _raise("forensic marker connect_restore_grants is not canonical")
        grants.append({"grant_option": item["grant_option"], "role": role})
        previous_role = role
    return grants


def _validate_state_history(value: object, *, state: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value:
        _raise("forensic marker state_history is invalid")
    history: list[dict[str, object]] = []
    previous_sequence = 0
    previous_state: str | None = None
    for item in value:
        if not isinstance(item, dict) or set(item) != {"at_utc", "sequence", "state"}:
            _raise("forensic marker state_history is invalid")
        item_state = item.get("state")
        sequence = item.get("sequence")
        at_utc = item.get("at_utc")
        if (
            not isinstance(item_state, str)
            or item_state not in _STATES
            or type(sequence) is not int
            or sequence != previous_sequence + 1
            or not isinstance(at_utc, str)
            or not at_utc.endswith("Z")
        ):
            _raise("forensic marker state_history is invalid")
        if previous_state is not None:
            normal_transition = item_state in _NEXT_STATES.get(
                previous_state, frozenset()
            )
            if not normal_transition:
                _raise("forensic marker state_history transition is invalid")
        history.append({"at_utc": at_utc, "sequence": sequence, "state": item_state})
        previous_sequence = sequence
        previous_state = item_state
    if history[0]["state"] != "prepared":
        _raise("forensic marker state_history must start at prepared")
    if history[-1]["state"] != state:
        _raise("forensic marker current state does not match its history")
    return history


def _validate_failure(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"code", "phase"}:
        _raise("forensic marker failure is invalid")
    return {
        "code": _validate_identifier(value.get("code"), "failure code", _CODE_RE),
        "phase": _validate_identifier(value.get("phase"), "failure phase", _CODE_RE),
    }


def _validate_marker(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        _raise("forensic marker is not an object")
    fields = {
        "acl_topology_sha256",
        "app_role",
        "connect_restore_grants",
        "drain_receipt_sha256",
        "failure",
        "fence_executor_role",
        "fenced_connect_roles",
        "format_version",
        "holder_backend_pid",
        "lock_key",
        "operation_id",
        "pg_restore_list_sha256",
        "previous_schema",
        "public_connect_was_granted",
        "recovery_required",
        "restore_executor_connect_restore_grants",
        "restore_executor_role",
        "restore_schema",
        "script_sha256",
        "snapshot_sha256",
        "source_identity_sha256",
        "source_schema",
        "source_schema_oid_before",
        "state",
        "state_history",
        "target_identity_sha256",
        "write_roles",
    }
    optional = {
        "app_schema_oid_after_switch",
        "previous_schema_oid_after_switch",
        "restore_schema_oid",
        "terminal_schema_mode",
    }
    if set(value).difference(fields | optional) or not fields.issubset(value):
        _raise("forensic marker schema is invalid")
    if value.get("format_version") != 1:
        _raise("forensic marker version is invalid")
    state = value.get("state")
    if not isinstance(state, str) or state not in _STATES:
        _raise("forensic marker state is invalid")
    recovery_required = value.get("recovery_required")
    if type(recovery_required) is not bool:
        _raise("forensic marker recovery latch is invalid")
    marker: dict[str, object] = {
        "acl_topology_sha256": _validate_sha256(
            value.get("acl_topology_sha256"), "acl topology"
        ),
        "app_role": _validate_identifier(value.get("app_role"), "app role", _ROLE_RE),
        "connect_restore_grants": _validate_connect_restore_grants(
            value.get("connect_restore_grants")
        ),
        "drain_receipt_sha256": _validate_sha256(
            value.get("drain_receipt_sha256"), "drain receipt"
        ),
        "failure": _validate_failure(value.get("failure")),
        "fence_executor_role": _validate_identifier(
            value.get("fence_executor_role"), "fence executor role", _ROLE_RE
        ),
        "fenced_connect_roles": _validate_role_list(
            value.get("fenced_connect_roles"), "fenced connect roles"
        ),
        "format_version": 1,
        "holder_backend_pid": _validate_positive_int(
            value.get("holder_backend_pid"), "holder backend pid"
        ),
        "lock_key": _LOCK_KEY,
        "operation_id": _validate_uuid(value.get("operation_id")),
        "pg_restore_list_sha256": _validate_sha256(
            value.get("pg_restore_list_sha256"), "pg restore list"
        ),
        "previous_schema": _validate_identifier(
            value.get("previous_schema"), "previous schema", _SCHEMA_RE
        ),
        "public_connect_was_granted": value.get("public_connect_was_granted"),
        "recovery_required": recovery_required,
        "restore_executor_connect_restore_grants": _validate_connect_restore_grants(
            value.get("restore_executor_connect_restore_grants")
        ),
        "restore_executor_role": _validate_identifier(
            value.get("restore_executor_role"), "restore executor role", _ROLE_RE
        ),
        "restore_schema": _validate_identifier(
            value.get("restore_schema"), "restore schema", _SCHEMA_RE
        ),
        "script_sha256": _validate_sha256(value.get("script_sha256"), "script"),
        "snapshot_sha256": _validate_sha256(value.get("snapshot_sha256"), "snapshot"),
        "source_identity_sha256": _validate_sha256(
            value.get("source_identity_sha256"), "source identity"
        ),
        "source_schema": _validate_identifier(
            value.get("source_schema"), "source schema", _SCHEMA_RE
        ),
        "source_schema_oid_before": _validate_positive_int(
            value.get("source_schema_oid_before"), "source schema oid"
        ),
        "state": state,
        "state_history": _validate_state_history(
            value.get("state_history"), state=state
        ),
        "target_identity_sha256": _validate_sha256(
            value.get("target_identity_sha256"), "target identity"
        ),
        "write_roles": _validate_role_list(value.get("write_roles"), "write roles"),
    }
    if type(marker["public_connect_was_granted"]) is not bool:
        _raise("forensic marker public CONNECT state is invalid")
    if marker["lock_key"] != value.get("lock_key"):
        _raise("forensic marker advisory lock key is invalid")
    if (
        marker["source_schema"] == marker["restore_schema"]
        or marker["source_schema"] == marker["previous_schema"]
        or marker["restore_schema"] == marker["previous_schema"]
    ):
        _raise("forensic marker schema names must be distinct")
    if marker["fence_executor_role"] == marker["app_role"]:
        _raise("forensic marker fence executor must be distinct from the app role")
    if marker["restore_executor_role"] in {
        marker["app_role"],
        marker["fence_executor_role"],
    }:
        _raise("forensic marker restore executor must be distinct from runtime roles")
    if marker["write_roles"] != [marker["app_role"]]:
        _raise("forensic marker writer inventory is not the strict M05 app role")
    for name in optional:
        if name == "terminal_schema_mode":
            continue
        item = value.get(name)
        if item is None:
            continue
        marker[name] = _validate_positive_int(item, name)
    historical_states = {
        cast(str, item["state"])
        for item in cast(list[dict[str, object]], marker["state_history"])
    }
    fence_started = historical_states - {"prepared"}
    if fence_started and marker["fenced_connect_roles"] != [marker["app_role"]]:
        _raise("forensic marker fenced role inventory is not the strict M05 app role")
    if not fence_started and (
        marker["fenced_connect_roles"]
        or marker["connect_restore_grants"]
        or marker["restore_executor_connect_restore_grants"]
    ):
        _raise("forensic marker pre-fence inventory is not empty")
    if any(
        grant["role"] != marker["app_role"]
        for grant in cast(list[dict[str, object]], marker["connect_restore_grants"])
    ):
        _raise("forensic marker app CONNECT grant inventory is invalid")
    if any(
        grant["role"] != marker["restore_executor_role"]
        for grant in cast(
            list[dict[str, object]], marker["restore_executor_connect_restore_grants"]
        )
    ):
        _raise("forensic marker restore executor CONNECT grant inventory is invalid")
    if "restore_ready" in historical_states and "restore_schema_oid" not in marker:
        _raise("forensic marker restore schema oid is missing")
    if "restore_schema_oid" in marker and "restore_ready" not in historical_states:
        _raise("forensic marker restore schema oid is premature")
    if (
        "restore_schema_oid" in marker
        and marker["restore_schema_oid"] == marker["source_schema_oid_before"]
    ):
        _raise("forensic marker restored schema oid must differ from the source schema")
    terminal_schema_mode = value.get("terminal_schema_mode")
    if state == "fence_release_intent" and terminal_schema_mode != "switched":
        _raise("forensic marker terminal schema mode is invalid")
    if state != "fence_release_intent" and terminal_schema_mode is not None:
        _raise("forensic marker terminal schema mode is premature")
    if terminal_schema_mode is not None:
        marker["terminal_schema_mode"] = terminal_schema_mode
    if terminal_schema_mode == "switched" and (
        "app_schema_oid_after_switch" not in marker
        or "previous_schema_oid_after_switch" not in marker
    ):
        _raise("forensic marker switch oid matrix is missing")
    switched = "switched" in historical_states
    has_switch_matrix = (
        "app_schema_oid_after_switch" in marker
        and "previous_schema_oid_after_switch" in marker
    )
    if switched and not has_switch_matrix:
        _raise("forensic marker switched state is missing its oid matrix")
    if not switched and has_switch_matrix:
        _raise("forensic marker has a switch oid matrix before the switch")
    if switched and (
        marker.get("app_schema_oid_after_switch") != marker.get("restore_schema_oid")
        or marker.get("previous_schema_oid_after_switch")
        != marker.get("source_schema_oid_before")
    ):
        _raise("forensic marker switched oid matrix is inconsistent")
    if terminal_schema_mode == "switched" and not switched:
        _raise("forensic marker switched terminal mode lacks a switch state")
    if marker["failure"] is None and marker["recovery_required"]:
        _raise("forensic marker recovery latch lacks failure evidence")
    if marker["failure"] is not None and not marker["recovery_required"]:
        _raise("forensic marker failure is not recovery latched")
    return marker


def _strict_parent_chain(path: Path) -> None:
    if not path.is_absolute():
        _raise("forensic state directory is invalid")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except OSError:
            _raise("forensic state directory parent is unavailable")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _raise("forensic state directory contains a symlink or non-directory")
        if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022:
            _raise("forensic state directory parent permissions are unsafe")


@dataclass(frozen=True)
class _StateDirectory:
    path: Path
    strict: bool

    @classmethod
    def open(cls, path: Path, *, strict: bool, test_mode: bool) -> _StateDirectory:
        if strict:
            if test_mode or path != DEFAULT_STATE_DIRECTORY:
                _raise("strict forensic state directory is not canonical")
            if os.geteuid() != 0:
                _raise("strict forensic operations require root execution")
            _strict_parent_chain(path.parent)
        if path.is_symlink() or not path.is_dir():
            _raise("forensic state directory is unavailable")
        metadata = path.stat()
        expected_uid = 0 if strict else os.geteuid()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != expected_uid
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            _raise("forensic state directory permissions are invalid")
        for child in (_OPERATIONS_NAME, _RECOVERY_NAME):
            child_path = path / child
            if not child_path.exists():
                try:
                    child_path.mkdir(mode=0o700)
                except OSError:
                    _raise("forensic state subdirectory could not be created")
            if child_path.is_symlink() or not child_path.is_dir():
                _raise("forensic state subdirectory is invalid")
            child_metadata = child_path.stat()
            if (
                child_metadata.st_uid != expected_uid
                or stat.S_IMODE(child_metadata.st_mode) != 0o700
            ):
                _raise("forensic state subdirectory permissions are invalid")
        store = cls(path=path, strict=strict)
        store._ensure_lock_file()
        return store

    def _directory_fd(self, relative: str = ".") -> int:
        try:
            descriptor = os.open(
                self.path / relative,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
        except OSError:
            _raise("forensic state directory is unavailable")
        metadata = os.fstat(descriptor)
        expected_uid = 0 if self.strict else os.geteuid()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != expected_uid
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            os.close(descriptor)
            _raise("forensic state directory permissions are invalid")
        return descriptor

    def _ensure_lock_file(self) -> None:
        """Create or verify the fixed local mutation lock without following links."""

        directory_fd = self._directory_fd()
        try:
            try:
                descriptor = os.open(
                    _LOCK_NAME,
                    os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=directory_fd,
                )
            except OSError:
                _raise("forensic state lock is unavailable")
            try:
                os.fchmod(descriptor, 0o600)
                metadata = os.fstat(descriptor)
                expected_uid = 0 if self.strict else os.geteuid()
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != expected_uid
                    or stat.S_IMODE(metadata.st_mode) != 0o600
                ):
                    _raise("forensic state lock permissions are invalid")
                os.fsync(descriptor)
                os.fsync(directory_fd)
            finally:
                os.close(descriptor)
        finally:
            os.close(directory_fd)

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        """Serialize each read/check/write state transition across host processes."""

        directory_fd = self._directory_fd()
        try:
            try:
                descriptor = os.open(
                    _LOCK_NAME,
                    os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=directory_fd,
                )
            except OSError:
                _raise("forensic state lock is unavailable")
            try:
                metadata = os.fstat(descriptor)
                expected_uid = 0 if self.strict else os.geteuid()
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != expected_uid
                    or stat.S_IMODE(metadata.st_mode) != 0o600
                ):
                    _raise("forensic state lock permissions are invalid")
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX)
                except OSError:
                    _raise("forensic state lock could not be acquired")
                try:
                    yield
                finally:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                    except OSError:
                        pass
            finally:
                os.close(descriptor)
        finally:
            os.close(directory_fd)

    def _read_regular(self, relative: str) -> bytes:
        directory, name = os.path.split(relative)
        directory_fd = self._directory_fd(directory or ".")
        try:
            try:
                descriptor = os.open(
                    name,
                    os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=directory_fd,
                )
            except OSError:
                _raise("forensic marker is unavailable")
            try:
                before = os.fstat(descriptor)
                expected_uid = 0 if self.strict else os.geteuid()
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_uid != expected_uid
                    or stat.S_IMODE(before.st_mode) != 0o600
                    or before.st_size < 1
                    or before.st_size > _MAX_DOCUMENT_BYTES
                ):
                    _raise("forensic marker permissions are invalid")
                raw = bytearray()
                while len(raw) <= _MAX_DOCUMENT_BYTES:
                    chunk = os.read(
                        descriptor, min(8192, _MAX_DOCUMENT_BYTES + 1 - len(raw))
                    )
                    if not chunk:
                        break
                    raw.extend(chunk)
                after = os.fstat(descriptor)
                if (
                    len(raw) > _MAX_DOCUMENT_BYTES
                    or len(raw) != before.st_size
                    or (
                        before.st_dev,
                        before.st_ino,
                        before.st_size,
                        before.st_mtime_ns,
                    )
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                ):
                    _raise("forensic marker changed while reading")
                return bytes(raw)
            finally:
                os.close(descriptor)
        finally:
            os.close(directory_fd)

    @staticmethod
    def _write_all(descriptor: int, raw: bytes) -> None:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]

    def _write_new_regular(self, relative: str, raw: bytes) -> None:
        directory, name = os.path.split(relative)
        directory_fd = self._directory_fd(directory or ".")
        temporary_name = f".{name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        try:
            try:
                descriptor = os.open(
                    temporary_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=directory_fd,
                )
            except OSError:
                _raise("forensic marker temporary file could not be created")
            try:
                os.fchmod(descriptor, 0o600)
                self._write_all(descriptor, raw)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            try:
                os.link(
                    temporary_name,
                    name,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except FileExistsError:
                _raise("forensic marker already exists")
            except OSError:
                _raise("forensic marker could not be committed")
            finally:
                try:
                    os.unlink(temporary_name, dir_fd=directory_fd)
                except OSError:
                    pass
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _replace_regular(self, relative: str, raw: bytes) -> None:
        directory, name = os.path.split(relative)
        directory_fd = self._directory_fd(directory or ".")
        temporary_name = f".{name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        try:
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
            try:
                os.fchmod(descriptor, 0o600)
                self._write_all(descriptor, raw)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            try:
                os.replace(
                    temporary_name,
                    name,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                )
            except OSError:
                _raise("forensic marker could not be replaced")
            os.fsync(directory_fd)
        finally:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except OSError:
                pass
            os.close(directory_fd)

    def _append_history(self, operation_id: str, event: dict[str, object]) -> None:
        directory_fd = self._directory_fd(_OPERATIONS_NAME)
        raw = _canonical_json(event) + b"\n"
        if len(raw) > _MAX_HISTORY_LINE_BYTES:
            _raise("forensic history event is too large")
        try:
            descriptor = os.open(
                f"{operation_id}.jsonl",
                os.O_WRONLY | os.O_APPEND | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
        except OSError:
            os.close(directory_fd)
            _raise("forensic operation history is unavailable")
        try:
            metadata = os.fstat(descriptor)
            expected_uid = 0 if self.strict else os.geteuid()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != expected_uid
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                _raise("forensic operation history permissions are invalid")
            self._write_all(descriptor, raw)
            os.fsync(descriptor)
            os.fsync(directory_fd)
        finally:
            os.close(descriptor)
            os.close(directory_fd)

    def _unlink_current(self) -> None:
        directory_fd = self._directory_fd()
        try:
            metadata = os.stat(
                _CURRENT_NAME, dir_fd=directory_fd, follow_symlinks=False
            )
            expected_uid = 0 if self.strict else os.geteuid()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != expected_uid
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                _raise("forensic marker permissions are invalid")
            os.unlink(_CURRENT_NAME, dir_fd=directory_fd)
            os.fsync(directory_fd)
        except FileNotFoundError:
            _raise("forensic marker is unavailable")
        finally:
            os.close(directory_fd)

    def _current_unlocked(self) -> tuple[dict[str, object], bytes]:
        raw = self._read_regular(_CURRENT_NAME)
        try:
            parsed = json.loads(
                raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys
            )
        except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateJsonKeyError):
            _raise("forensic marker is invalid JSON")
        return _validate_marker(parsed), raw

    def current(self) -> tuple[dict[str, object], bytes]:
        """Read the current marker without taking the writer lock."""

        return self._current_unlocked()

    def current_if_present(self) -> tuple[dict[str, object], bytes] | None:
        """Return no marker only for an absent current pointer; corruption fails closed."""

        directory_fd = self._directory_fd()
        try:
            try:
                os.stat(_CURRENT_NAME, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                return None
        finally:
            os.close(directory_fd)
        return self._current_unlocked()

    def _recovery_ledger_proof_unlocked(
        self,
        operation_id: str,
        *,
        require_release_receipt_seal: bool,
        allow_root_unsealed_release_receipt_verification: bool = False,
    ) -> dict[str, object]:
        """현재 marker와 append-only ledger의 exact recovery boundary를 검증한다.

        ``current.json``은 state transition에서 history보다 먼저 바뀔 수 있다. 반면
        release receipt seal은 marker를 다시 쓰지 않는 terminal forensic commit이다.
        따라서 recovery와 cleanup 모두 raw marker SHA, 모든 state event의 순서, 그리고
        intent 뒤 하나뿐인 seal을 같은 ledger read에서 묶어 검증해야 한다.
        """

        marker, raw = self._current_unlocked()
        if marker["operation_id"] != operation_id:
            _raise("forensic marker operation does not match")
        marker_sha256 = _sha256(raw)
        history_raw = self._read_regular(f"{_OPERATIONS_NAME}/{operation_id}.jsonl")
        expected_history = cast(list[dict[str, object]], marker["state_history"])
        state_events: list[dict[str, object]] = []
        seal: dict[str, object] | None = None
        root_unsealed_release_receipt_verification: dict[str, object] | None = None
        recovery_acknowledgement: dict[str, object] | None = None
        saw_prepared_intent = False
        for event_index, line in enumerate(history_raw.splitlines()):
            if not line or len(line) > _MAX_HISTORY_LINE_BYTES:
                _raise("forensic operation history is invalid")
            try:
                event = json.loads(
                    line.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys
                )
            except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateJsonKeyError):
                _raise("forensic operation history is invalid")
            if not isinstance(event, dict) or _canonical_json(event) != line:
                _raise("forensic operation history is invalid")
            event_type = event.get("type")
            if event_type == "prepared_intent":
                if (
                    saw_prepared_intent
                    or event_index != 0
                    or set(event)
                    != {
                        "at_utc",
                        "marker_sha256",
                        "operation_id",
                        "sequence",
                        "state",
                        "type",
                    }
                    or event.get("state") != "prepared"
                    or event.get("sequence") != 1
                ):
                    _raise("forensic operation history is invalid")
                saw_prepared_intent = True
            elif event_type == "state":
                if (
                    not saw_prepared_intent
                    or seal is not None
                    or root_unsealed_release_receipt_verification is not None
                    or recovery_acknowledgement is not None
                    or set(event)
                    != {
                        "at_utc",
                        "marker_sha256",
                        "operation_id",
                        "sequence",
                        "state",
                        "type",
                    }
                ):
                    _raise("forensic operation history is invalid")
                state_events.append(event)
            elif event_type == _RELEASE_RECEIPT_SEAL_TYPE:
                if (
                    not saw_prepared_intent
                    or seal is not None
                    or root_unsealed_release_receipt_verification is not None
                    or recovery_acknowledgement is not None
                    or set(event)
                    != {
                        "at_utc",
                        "intent_marker_sha256",
                        "intent_state_sequence",
                        "operation_id",
                        "receipt_record_sha256",
                        "type",
                    }
                ):
                    _raise("forensic release receipt seal is invalid")
                seal = event
            elif event_type == _ROOT_UNSEALED_RELEASE_RECEIPT_VERIFICATION_TYPE:
                if (
                    not saw_prepared_intent
                    or seal is not None
                    or root_unsealed_release_receipt_verification is not None
                    or recovery_acknowledgement is not None
                    or set(event)
                    != {
                        "at_utc",
                        "intent_marker_sha256",
                        "intent_state_sequence",
                        "operation_id",
                        "receipt_record_sha256",
                        "type",
                        "verification_sha256",
                    }
                ):
                    _raise(
                        "forensic root unsealed release receipt verification is invalid"
                    )
                root_unsealed_release_receipt_verification = event
            elif event_type == "recovery_acknowledged":
                if (
                    not saw_prepared_intent
                    or recovery_acknowledgement is not None
                    or set(event)
                    != {
                        "at_utc",
                        "marker_sha256",
                        "operation_id",
                        "outcome",
                        "sequence",
                        "state",
                        "type",
                        "verification_sha256",
                    }
                    or event.get("outcome") != "recovery_acknowledged"
                ):
                    _raise("forensic recovery acknowledgement is invalid")
                recovery_acknowledgement = event
            else:
                # failure/recovery acknowledgement이 남아 있으면 current marker는
                # 이미 latched 또는 archived여야 한다. 이 primitive는 unlatched
                # marker의 archive 전 증명에만 사용한다.
                _raise("forensic operation history is not recoverable")

            if (
                event.get("operation_id") != operation_id
                or not isinstance(event.get("at_utc"), str)
                or not cast(str, event["at_utc"]).endswith("Z")
            ):
                _raise("forensic operation history is invalid")
            if event_type in {"prepared_intent", "state"} and (
                type(event.get("sequence")) is not int
                or cast(int, event["sequence"]) < 1
                or event.get("state") not in _STATES
                or not isinstance(event.get("marker_sha256"), str)
                or _SHA256_RE.fullmatch(cast(str, event["marker_sha256"])) is None
            ):
                _raise("forensic operation history is invalid")
            if event_type == _RELEASE_RECEIPT_SEAL_TYPE and (
                type(event.get("intent_state_sequence")) is not int
                or cast(int, event["intent_state_sequence"]) < 1
                or not isinstance(event.get("intent_marker_sha256"), str)
                or _SHA256_RE.fullmatch(cast(str, event["intent_marker_sha256"]))
                is None
                or not isinstance(event.get("receipt_record_sha256"), str)
                or _SHA256_RE.fullmatch(cast(str, event["receipt_record_sha256"]))
                is None
            ):
                _raise("forensic release receipt seal is invalid")
            if event_type == _ROOT_UNSEALED_RELEASE_RECEIPT_VERIFICATION_TYPE and (
                type(event.get("intent_state_sequence")) is not int
                or cast(int, event["intent_state_sequence"]) < 1
                or not isinstance(event.get("intent_marker_sha256"), str)
                or _SHA256_RE.fullmatch(cast(str, event["intent_marker_sha256"]))
                is None
                or not isinstance(event.get("receipt_record_sha256"), str)
                or _SHA256_RE.fullmatch(cast(str, event["receipt_record_sha256"]))
                is None
                or not isinstance(event.get("verification_sha256"), str)
                or _SHA256_RE.fullmatch(cast(str, event["verification_sha256"])) is None
            ):
                _raise("forensic root unsealed release receipt verification is invalid")
            if event_type == "recovery_acknowledged" and (
                type(event.get("sequence")) is not int
                or cast(int, event["sequence"]) < 1
                or event.get("state") not in _STATES
                or not isinstance(event.get("marker_sha256"), str)
                or _SHA256_RE.fullmatch(cast(str, event["marker_sha256"])) is None
                or not isinstance(event.get("verification_sha256"), str)
                or _SHA256_RE.fullmatch(cast(str, event["verification_sha256"])) is None
            ):
                _raise("forensic recovery acknowledgement is invalid")
        if not saw_prepared_intent or len(state_events) != len(expected_history):
            _raise("forensic current marker is not fully represented in history")
        for expected, event in zip(expected_history, state_events, strict=True):
            if (
                event["sequence"] != expected["sequence"]
                or event["state"] != expected["state"]
            ):
                _raise("forensic current marker history sequence is inconsistent")
        if state_events[-1].get("marker_sha256") != marker_sha256:
            _raise("forensic current marker hash is not committed in history")

        state = cast(str, marker["state"])
        receipt_record_sha256: str | None = None
        root_unsealed_verification_sha256: str | None = None
        if state == "fence_release_intent":
            intent_state_sequence = len(expected_history)
            if seal is None:
                if root_unsealed_release_receipt_verification is not None:
                    if (
                        root_unsealed_release_receipt_verification.get(
                            "intent_marker_sha256"
                        )
                        != marker_sha256
                        or root_unsealed_release_receipt_verification.get(
                            "intent_state_sequence"
                        )
                        != intent_state_sequence
                    ):
                        _raise(
                            "forensic root unsealed release receipt verification does not match the intent marker"
                        )
                    if not allow_root_unsealed_release_receipt_verification:
                        _raise(
                            "forensic unsealed release receipt requires explicit root escalation"
                        )
                    receipt_record_sha256 = cast(
                        str,
                        root_unsealed_release_receipt_verification[
                            "receipt_record_sha256"
                        ],
                    )
                    root_unsealed_verification_sha256 = cast(
                        str,
                        root_unsealed_release_receipt_verification[
                            "verification_sha256"
                        ],
                    )
                elif require_release_receipt_seal:
                    _raise("forensic release receipt seal is missing")
            elif (
                seal.get("intent_marker_sha256") != marker_sha256
                or seal.get("intent_state_sequence") != intent_state_sequence
            ):
                _raise("forensic release receipt seal does not match the intent marker")
            else:
                receipt_record_sha256 = cast(str, seal["receipt_record_sha256"])
        elif seal is not None or root_unsealed_release_receipt_verification is not None:
            _raise("forensic release receipt terminal evidence is premature")

        acknowledgement_verification_sha256: str | None = None
        if recovery_acknowledgement is not None:
            if (
                recovery_acknowledgement.get("state") != state
                or recovery_acknowledgement.get("sequence") != len(expected_history)
                or recovery_acknowledgement.get("marker_sha256") != marker_sha256
            ):
                _raise("forensic recovery acknowledgement does not match the marker")
            final_marker = self._read_regular(
                f"{_OPERATIONS_NAME}/{operation_id}.final.json"
            )
            if final_marker != raw:
                _raise("forensic final marker does not match the active marker")
            acknowledgement_raw = self._read_regular(
                f"{_RECOVERY_NAME}/{operation_id}.json"
            )
            try:
                acknowledgement = json.loads(
                    acknowledgement_raw.decode("utf-8"),
                    object_pairs_hook=_reject_duplicate_json_keys,
                )
            except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateJsonKeyError):
                _raise("forensic recovery acknowledgement is invalid")
            if (
                not isinstance(acknowledgement, dict)
                or set(acknowledgement)
                != {
                    "at_utc",
                    "marker_sha256",
                    "operation_id",
                    "outcome",
                    "verification_sha256",
                    "version",
                }
                or not isinstance(acknowledgement.get("at_utc"), str)
                or not cast(str, acknowledgement["at_utc"]).endswith("Z")
                or acknowledgement.get("version") != 1
                or acknowledgement.get("outcome") != "recovery_acknowledged"
                or acknowledgement.get("operation_id") != operation_id
                or acknowledgement.get("marker_sha256") != marker_sha256
                or acknowledgement.get("verification_sha256")
                != recovery_acknowledgement.get("verification_sha256")
            ):
                _raise("forensic recovery acknowledgement does not match the marker")
            if (
                root_unsealed_verification_sha256 is not None
                and recovery_acknowledgement.get("verification_sha256")
                != root_unsealed_verification_sha256
            ):
                _raise(
                    "forensic recovery acknowledgement does not match the root unsealed release receipt verification"
                )
            acknowledgement_verification_sha256 = cast(
                str, recovery_acknowledgement["verification_sha256"]
            )

        return {
            "intent_state_sequence": (
                len(expected_history) if state == "fence_release_intent" else None
            ),
            "marker_sha256": marker_sha256,
            "recovery_acknowledgement_verification_sha256": acknowledgement_verification_sha256,
            "release_receipt_record_sha256": receipt_record_sha256,
            "root_unsealed_release_receipt_verification_sha256": root_unsealed_verification_sha256,
        }

    def assert_current_history_consistent_for_recovery(
        self, operation_id: str
    ) -> dict[str, object]:
        """root archive 전 완전한 state ledger 및 release receipt seal을 증명한다."""

        return self._recovery_ledger_proof_unlocked(
            operation_id, require_release_receipt_seal=True
        )

    def seal_release_receipt(
        self,
        operation_id: str,
        *,
        intent_marker_sha256: str,
        receipt_record_sha256: str,
        test_fail_history_append: bool = False,
    ) -> None:
        """검증 완료한 DB release receipt를 marker를 바꾸지 않고 ledger에 봉인한다.

        append/fsync error는 event가 durable하지 않았다는 뜻이 아니다. 같은 lock 안에서
        exact event를 재독해 하나만 남아 있으면 성공으로 수렴하고, 부분/중복/다른
        binding은 fail-close하여 caller cleanup이 database fence를 다시 적용하게 한다.
        """

        intent_marker_sha256 = _validate_sha256(
            intent_marker_sha256, "release receipt intent marker"
        )
        receipt_record_sha256 = _validate_sha256(
            receipt_record_sha256, "release receipt record"
        )
        with self._exclusive_lock():
            marker, raw = self._current_unlocked()
            if marker["operation_id"] != operation_id:
                _raise("forensic marker operation does not match")
            if marker["state"] != "fence_release_intent" or marker["recovery_required"]:
                _raise("forensic marker is not a sealable release intent")
            if _sha256(raw) != intent_marker_sha256:
                _raise("forensic release receipt intent marker changed")
            proof = self._recovery_ledger_proof_unlocked(
                operation_id, require_release_receipt_seal=False
            )
            if proof["recovery_acknowledgement_verification_sha256"] is not None:
                _raise("forensic release receipt seal follows recovery acknowledgement")
            existing_record_sha256 = proof["release_receipt_record_sha256"]
            if existing_record_sha256 is not None:
                if existing_record_sha256 != receipt_record_sha256:
                    _raise("forensic release receipt seal does not match the receipt")
                return
            sequence = proof["intent_state_sequence"]
            if type(sequence) is not int:
                _raise("forensic release receipt intent sequence is invalid")
            event = {
                "at_utc": _utc_now(),
                "intent_marker_sha256": intent_marker_sha256,
                "intent_state_sequence": sequence,
                "operation_id": operation_id,
                "receipt_record_sha256": receipt_record_sha256,
                "type": _RELEASE_RECEIPT_SEAL_TYPE,
            }
            try:
                if test_fail_history_append:
                    _raise("test-only forensic history append failure injected")
                self._append_history(operation_id, event)
            except ForensicsError:
                recovered = self._recovery_ledger_proof_unlocked(
                    operation_id, require_release_receipt_seal=False
                )
                if recovered["release_receipt_record_sha256"] == receipt_record_sha256:
                    return
                raise
            verified = self._recovery_ledger_proof_unlocked(
                operation_id, require_release_receipt_seal=True
            )
            if verified["release_receipt_record_sha256"] != receipt_record_sha256:
                _raise("forensic release receipt seal could not be verified")

    def assert_exact_release_receipt_seal(
        self,
        operation_id: str,
        *,
        intent_marker_sha256: str,
        receipt_record_sha256: str,
    ) -> None:
        """cleanup/root가 raw intent와 receipt record의 exact seal만 신뢰하게 한다."""

        intent_marker_sha256 = _validate_sha256(
            intent_marker_sha256, "release receipt intent marker"
        )
        receipt_record_sha256 = _validate_sha256(
            receipt_record_sha256, "release receipt record"
        )
        with self._exclusive_lock():
            proof = self._recovery_ledger_proof_unlocked(
                operation_id, require_release_receipt_seal=True
            )
            if (
                proof["marker_sha256"] != intent_marker_sha256
                or proof["release_receipt_record_sha256"] != receipt_record_sha256
            ):
                _raise("forensic release receipt seal does not match the active marker")

    def _write_new_or_match(self, relative: str, raw: bytes, *, mismatch: str) -> bool:
        """Persist an immutable artifact, or accept an exact crash-resume duplicate."""

        try:
            self._write_new_regular(relative, raw)
            return True
        except ForensicsError:
            existing = self._read_regular(relative)
            if existing != raw:
                _raise(mismatch)
            return False

    def _history_has_acknowledgement(
        self,
        operation_id: str,
        *,
        marker_sha256: str,
        verification_sha256: str,
    ) -> bool:
        raw = self._read_regular(f"{_OPERATIONS_NAME}/{operation_id}.jsonl")
        for line in raw.splitlines():
            try:
                event = json.loads(
                    line.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys
                )
            except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateJsonKeyError):
                _raise("forensic operation history is invalid")
            if not isinstance(event, dict):
                _raise("forensic operation history is invalid")
            if (
                event.get("type") == "recovery_acknowledged"
                and event.get("operation_id") == operation_id
                and event.get("marker_sha256") == marker_sha256
                and event.get("verification_sha256") == verification_sha256
            ):
                return True
        return False

    def _append_root_unsealed_release_receipt_verification_unlocked(
        self,
        operation_id: str,
        *,
        intent_marker_sha256: str,
        intent_state_sequence: int,
        receipt_record_sha256: str,
        verification_sha256: str,
    ) -> None:
        """DB commit 뒤 seal 전 crash를 root 증명으로만 봉인한다.

        이 event는 normal runner가 release 직후 남기는 ``release_receipt_committed``
        seal과 다른 의미다. root entrypoint가 다시 수행한 full read-only DB proof를
        binding하므로, append/fsync 결과가 불명확할 때도 같은 lock 아래 exact readback
        하나만 성공으로 인정한다.
        """

        event = {
            "at_utc": _utc_now(),
            "intent_marker_sha256": intent_marker_sha256,
            "intent_state_sequence": intent_state_sequence,
            "operation_id": operation_id,
            "receipt_record_sha256": receipt_record_sha256,
            "type": _ROOT_UNSEALED_RELEASE_RECEIPT_VERIFICATION_TYPE,
            "verification_sha256": verification_sha256,
        }
        try:
            self._append_history(operation_id, event)
        except ForensicsError:
            recovered = self._recovery_ledger_proof_unlocked(
                operation_id,
                require_release_receipt_seal=False,
                allow_root_unsealed_release_receipt_verification=True,
            )
            if (
                recovered["marker_sha256"] == intent_marker_sha256
                and recovered["intent_state_sequence"] == intent_state_sequence
                and recovered["release_receipt_record_sha256"] == receipt_record_sha256
                and recovered["root_unsealed_release_receipt_verification_sha256"]
                == verification_sha256
            ):
                return
            raise
        verified = self._recovery_ledger_proof_unlocked(
            operation_id,
            require_release_receipt_seal=False,
            allow_root_unsealed_release_receipt_verification=True,
        )
        if (
            verified["marker_sha256"] != intent_marker_sha256
            or verified["intent_state_sequence"] != intent_state_sequence
            or verified["release_receipt_record_sha256"] != receipt_record_sha256
            or verified["root_unsealed_release_receipt_verification_sha256"]
            != verification_sha256
        ):
            _raise(
                "forensic root unsealed release receipt verification could not be verified"
            )

    def _archive_verified_recovery_unlocked(
        self,
        operation_id: str,
        marker: dict[str, object],
        raw: bytes,
        proof: dict[str, object],
        *,
        verification_sha256: str,
    ) -> None:
        """이미 lock 안에서 검증한 marker를 acknowledgement와 함께 archive한다."""

        marker_sha256 = _sha256(raw)
        pending_verification = proof["recovery_acknowledgement_verification_sha256"]
        if pending_verification is not None:
            if pending_verification != verification_sha256:
                _raise("forensic recovery acknowledgement verification changed")
            self._unlink_current()
            return
        self._write_new_or_match(
            f"{_OPERATIONS_NAME}/{operation_id}.final.json",
            raw,
            mismatch="forensic final marker does not match the active marker",
        )
        acknowledgement_path = f"{_RECOVERY_NAME}/{operation_id}.json"
        acknowledgement = {
            "at_utc": _utc_now(),
            "marker_sha256": marker_sha256,
            "operation_id": operation_id,
            "outcome": "recovery_acknowledged",
            "verification_sha256": verification_sha256,
            "version": 1,
        }
        wrote_acknowledgement = False
        try:
            self._write_new_regular(
                acknowledgement_path, _canonical_json(acknowledgement)
            )
            wrote_acknowledgement = True
        except ForensicsError:
            try:
                existing = json.loads(
                    self._read_regular(acknowledgement_path).decode("utf-8"),
                    object_pairs_hook=_reject_duplicate_json_keys,
                )
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                _DuplicateJsonKeyError,
            ):
                _raise("forensic recovery acknowledgement is invalid")
            if (
                not isinstance(existing, dict)
                or set(existing)
                != {
                    "at_utc",
                    "marker_sha256",
                    "operation_id",
                    "outcome",
                    "verification_sha256",
                    "version",
                }
                or not isinstance(existing.get("at_utc"), str)
                or not cast(str, existing["at_utc"]).endswith("Z")
                or existing.get("version") != 1
                or existing.get("outcome") != "recovery_acknowledged"
                or existing.get("operation_id") != operation_id
                or existing.get("marker_sha256") != marker_sha256
                or existing.get("verification_sha256") != verification_sha256
            ):
                _raise("forensic recovery acknowledgement does not match the marker")
        if wrote_acknowledgement or not self._history_has_acknowledgement(
            operation_id,
            marker_sha256=marker_sha256,
            verification_sha256=verification_sha256,
        ):
            self._append_history(
                operation_id,
                {
                    "at_utc": _utc_now(),
                    "marker_sha256": marker_sha256,
                    "operation_id": operation_id,
                    "outcome": "recovery_acknowledged",
                    "sequence": len(cast(list[object], marker["state_history"])),
                    "state": marker["state"],
                    "type": "recovery_acknowledged",
                    "verification_sha256": verification_sha256,
                },
            )
        self._unlink_current()

    def begin(self, marker: dict[str, object]) -> None:
        marker = _validate_marker(marker)
        operation_id = cast(str, marker["operation_id"])
        raw = _canonical_json(marker)
        intent = {
            "at_utc": _utc_now(),
            "marker_sha256": _sha256(raw),
            "operation_id": operation_id,
            "sequence": 1,
            "state": "prepared",
            "type": "prepared_intent",
        }
        event = {
            **intent,
            "at_utc": _utc_now(),
            "type": "state",
        }
        with self._exclusive_lock():
            # Keep an orphan-safe intent first, then make the pointer authoritative.
            # A crash after the pointer write still leaves a history file for verified
            # recovery, but no history line claims a committed future state beforehand.
            self._write_new_regular(
                f"{_OPERATIONS_NAME}/{operation_id}.jsonl",
                _canonical_json(intent) + b"\n",
            )
            self._write_new_regular(_CURRENT_NAME, raw)
            self._append_history(operation_id, event)

    def transition(
        self,
        operation_id: str,
        state: MarkerState,
        updates: dict[str, object],
        *,
        test_fail_history_append: bool = False,
    ) -> None:
        with self._exclusive_lock():
            marker, _ = self._current_unlocked()
            if marker["operation_id"] != operation_id:
                _raise("forensic marker operation does not match")
            current_state = cast(str, marker["state"])
            if marker["recovery_required"]:
                _raise("forensic marker is recovery latched")
            if state not in _NEXT_STATES.get(current_state, frozenset()):
                _raise("forensic marker state transition is invalid")
            marker.update(updates)
            history = cast(list[dict[str, object]], marker["state_history"])
            marker["state"] = state
            marker["state_history"] = [
                *history,
                {"at_utc": _utc_now(), "sequence": len(history) + 1, "state": state},
            ]
            marker = _validate_marker(marker)
            raw = _canonical_json(marker)
            # Current is authoritative; append-only history follows the durable state.
            self._replace_regular(_CURRENT_NAME, raw)
            if test_fail_history_append:
                _raise("test-only forensic history append failure injected")
            self._append_history(
                operation_id,
                {
                    "at_utc": _utc_now(),
                    "marker_sha256": _sha256(raw),
                    "operation_id": operation_id,
                    "sequence": len(cast(list[object], marker["state_history"])),
                    "state": state,
                    "type": "state",
                },
            )

    def record_failure(self, operation_id: str, *, phase: str, code: str) -> None:
        failure = {
            "code": _validate_identifier(code, "failure code", _CODE_RE),
            "phase": _validate_identifier(phase, "failure phase", _CODE_RE),
        }
        with self._exclusive_lock():
            marker, _ = self._current_unlocked()
            if marker["operation_id"] != operation_id:
                _raise("forensic marker operation does not match")
            if marker["recovery_required"]:
                if marker["failure"] == failure:
                    return
                _raise("forensic marker is already recovery latched")
            marker["failure"] = failure
            marker["recovery_required"] = True
            marker = _validate_marker(marker)
            raw = _canonical_json(marker)
            # Record the fail-close marker before an audit line. It cannot be advanced
            # by the normal runner after a crash; only verified root recovery may close it.
            self._replace_regular(_CURRENT_NAME, raw)
            self._append_history(
                operation_id,
                {
                    "at_utc": _utc_now(),
                    "marker_sha256": _sha256(raw),
                    "operation_id": operation_id,
                    "sequence": len(cast(list[object], marker["state_history"])),
                    "state": marker["state"],
                    "type": "failure",
                },
            )

    def acknowledge_and_archive(
        self,
        operation_id: str,
        *,
        verification_sha256: str,
        expected_marker_sha256: str | None = None,
        expected_release_receipt_record_sha256: str | None = None,
        trusted_release_intent: bool = False,
    ) -> None:
        verification_sha256 = _validate_sha256(
            verification_sha256, "recovery verification"
        )
        if expected_marker_sha256 is not None:
            expected_marker_sha256 = _validate_sha256(
                expected_marker_sha256, "verified recovery marker"
            )
        if expected_release_receipt_record_sha256 is not None:
            expected_release_receipt_record_sha256 = _validate_sha256(
                expected_release_receipt_record_sha256,
                "verified recovery release receipt",
            )
        with self._exclusive_lock():
            marker, raw = self._current_unlocked()
            if marker["operation_id"] != operation_id:
                _raise("forensic marker operation does not match")
            marker_sha256 = _sha256(raw)
            # The trusted entrypoint proves the current marker and the live DB
            # separately.  Re-read and compare while holding the writer lock so
            # it cannot archive a newer marker that appeared after that proof.
            if (
                expected_marker_sha256 is not None
                and marker_sha256 != expected_marker_sha256
            ):
                _raise("forensic marker changed after verified recovery")
            allowed_states = {"prepared"}
            if trusted_release_intent:
                allowed_states.add("fence_release_intent")
            if marker["state"] not in allowed_states or marker["recovery_required"]:
                _raise("forensic marker is not safe for recovery acknowledgement")
            # Recheck the ledger inside the same lock as the current marker CAS.
            # The raw marker can remain unchanged while an interrupted writer has
            # left a partial/extra JSONL event; archive must not race that state.
            proof = self.assert_current_history_consistent_for_recovery(operation_id)
            if proof["marker_sha256"] != marker_sha256:
                _raise("forensic marker history changed after verified recovery")
            if marker["state"] == "fence_release_intent":
                if (
                    expected_release_receipt_record_sha256 is None
                    or proof["release_receipt_record_sha256"]
                    != expected_release_receipt_record_sha256
                ):
                    _raise("forensic release receipt changed after verified recovery")
            elif expected_release_receipt_record_sha256 is not None:
                _raise("prepared recovery cannot bind a release receipt")
            self._archive_verified_recovery_unlocked(
                operation_id,
                marker,
                raw,
                proof,
                verification_sha256=verification_sha256,
            )

    def acknowledge_unsealed_release_receipt_and_archive(
        self,
        operation_id: str,
        *,
        verification_sha256: str,
        expected_marker_sha256: str,
        expected_release_receipt_record_sha256: str,
    ) -> None:
        """명시적 root escalation만 unsealed release receipt를 종료할 수 있다.

        정상 runner의 release seal이 없는 intent는 일반 acknowledgement에서 절대
        archive하지 않는다. 이 primitive의 caller는 raw marker SHA를 외부에서 다시
        확인하고, same operation의 DB receipt와 full read-only topology proof를 완료한
        trusted root entrypoint여야 한다.
        """

        verification_sha256 = _validate_sha256(
            verification_sha256, "recovery verification"
        )
        expected_marker_sha256 = _validate_sha256(
            expected_marker_sha256, "verified recovery marker"
        )
        expected_release_receipt_record_sha256 = _validate_sha256(
            expected_release_receipt_record_sha256,
            "verified recovery release receipt",
        )
        with self._exclusive_lock():
            marker, raw = self._current_unlocked()
            if marker["operation_id"] != operation_id:
                _raise("forensic marker operation does not match")
            marker_sha256 = _sha256(raw)
            if marker_sha256 != expected_marker_sha256:
                _raise("forensic marker changed after verified recovery")
            if marker["state"] != "fence_release_intent" or marker["recovery_required"]:
                _raise("forensic marker is not an unsealed release intent")
            proof = self._recovery_ledger_proof_unlocked(
                operation_id,
                require_release_receipt_seal=False,
                allow_root_unsealed_release_receipt_verification=True,
            )
            if proof["marker_sha256"] != marker_sha256:
                _raise("forensic marker history changed after verified recovery")
            intent_state_sequence = proof["intent_state_sequence"]
            if type(intent_state_sequence) is not int:
                _raise("forensic release receipt intent sequence is invalid")
            root_verification_sha256 = proof[
                "root_unsealed_release_receipt_verification_sha256"
            ]
            receipt_record_sha256 = proof["release_receipt_record_sha256"]
            if root_verification_sha256 is None:
                if receipt_record_sha256 is not None:
                    _raise("forensic normal release receipt seal cannot be escalated")
                self._append_root_unsealed_release_receipt_verification_unlocked(
                    operation_id,
                    intent_marker_sha256=marker_sha256,
                    intent_state_sequence=intent_state_sequence,
                    receipt_record_sha256=expected_release_receipt_record_sha256,
                    verification_sha256=verification_sha256,
                )
                proof = self._recovery_ledger_proof_unlocked(
                    operation_id,
                    require_release_receipt_seal=False,
                    allow_root_unsealed_release_receipt_verification=True,
                )
                root_verification_sha256 = proof[
                    "root_unsealed_release_receipt_verification_sha256"
                ]
                receipt_record_sha256 = proof["release_receipt_record_sha256"]
            if (
                root_verification_sha256 != verification_sha256
                or receipt_record_sha256 != expected_release_receipt_record_sha256
            ):
                _raise(
                    "forensic root unsealed release receipt verification changed after recovery proof"
                )
            self._archive_verified_recovery_unlocked(
                operation_id,
                marker,
                raw,
                proof,
                verification_sha256=verification_sha256,
            )


def acknowledge_after_verified_recovery(
    state_directory: Path,
    *,
    operation_id: str,
    verification_sha256: str,
    expected_marker_sha256: str,
    expected_release_receipt_record_sha256: str | None,
) -> None:
    """trusted entrypoint의 DB 관찰 뒤 strict marker만 archive한다.

    Strict acknowledgement는 public helper CLI에서 제공하지 않는다. 이 작은
    in-process primitive는 trusted root entrypoint가 `_safe_recovery_observation`
    을 마친 뒤에만 호출한다.
    """

    store = _StateDirectory.open(state_directory, strict=True, test_mode=False)
    store.acknowledge_and_archive(
        operation_id,
        verification_sha256=verification_sha256,
        expected_marker_sha256=expected_marker_sha256,
        expected_release_receipt_record_sha256=expected_release_receipt_record_sha256,
        trusted_release_intent=True,
    )


def acknowledge_unsealed_release_receipt_after_verified_recovery(
    state_directory: Path,
    *,
    operation_id: str,
    verification_sha256: str,
    expected_marker_sha256: str,
    expected_release_receipt_record_sha256: str,
) -> None:
    """root-only explicit escalation 뒤 unsealed terminal intent를 archive한다."""

    store = _StateDirectory.open(state_directory, strict=True, test_mode=False)
    store.acknowledge_unsealed_release_receipt_and_archive(
        operation_id,
        verification_sha256=verification_sha256,
        expected_marker_sha256=expected_marker_sha256,
        expected_release_receipt_record_sha256=expected_release_receipt_record_sha256,
    )


def assert_current_history_consistent_for_verified_recovery(
    state_directory: Path, *, operation_id: str
) -> dict[str, object]:
    """trusted entrypoint가 archive 전에 호출하는 strict ledger proof primitive다."""

    store = _StateDirectory.open(state_directory, strict=True, test_mode=False)
    return store.assert_current_history_consistent_for_recovery(operation_id)


def assert_unsealed_release_receipt_escalation_history(
    state_directory: Path, *, operation_id: str
) -> dict[str, object]:
    """root escalation 전에 unsealed intent의 exact ledger만 읽는다.

    이 primitive는 seal 없는 release window의 live DB proof를 건너뛰지 않는다.
    caller는 이 반환값으로 raw marker SHA를 operator confirmation과 CAS하고, 이후
    fence-owner receipt 및 full read-only topology proof를 다시 수행해야 한다.
    """

    store = _StateDirectory.open(state_directory, strict=True, test_mode=False)
    proof = store._recovery_ledger_proof_unlocked(
        operation_id,
        require_release_receipt_seal=False,
        allow_root_unsealed_release_receipt_verification=True,
    )
    if proof["intent_state_sequence"] is None:
        _raise("forensic marker is not an unsealed release intent")
    if (
        proof["release_receipt_record_sha256"] is not None
        and proof["root_unsealed_release_receipt_verification_sha256"] is None
    ):
        _raise("forensic normal release receipt seal cannot be escalated")
    return proof


def _split_roles(value: str, field: str) -> list[str]:
    if not value:
        return []
    roles = value.split(",")
    if any(_ROLE_RE.fullmatch(role) is None for role in roles) or roles != sorted(
        set(roles)
    ):
        _raise(f"{field} is invalid")
    return roles


def _parse_grants(value: str) -> list[dict[str, object]]:
    if not value:
        return []
    grants: list[dict[str, object]] = []
    previous = ""
    for specification in value.split(","):
        role, separator, grant_option = specification.partition(":")
        if (
            separator != ":"
            or _ROLE_RE.fullmatch(role) is None
            or grant_option not in {"0", "1"}
            or role <= previous
        ):
            _raise("connect restore grants are invalid")
        grants.append({"grant_option": grant_option == "1", "role": role})
        previous = role
    return grants


def _marker_from_begin(args: argparse.Namespace) -> dict[str, object]:
    operation_id = args.operation_id or str(uuid.uuid4())
    _validate_uuid(operation_id)
    return {
        "acl_topology_sha256": args.acl_topology_sha256,
        "app_role": args.app_role,
        "connect_restore_grants": [],
        "drain_receipt_sha256": args.drain_receipt_sha256,
        "failure": None,
        "fence_executor_role": args.fence_executor_role,
        "fenced_connect_roles": [],
        "format_version": 1,
        "holder_backend_pid": args.holder_backend_pid,
        "lock_key": _LOCK_KEY,
        "operation_id": operation_id,
        "pg_restore_list_sha256": args.pg_restore_list_sha256,
        "previous_schema": args.previous_schema,
        "public_connect_was_granted": False,
        "recovery_required": False,
        "restore_executor_connect_restore_grants": [],
        "restore_executor_role": args.restore_executor_role,
        "restore_schema": args.restore_schema,
        "script_sha256": args.script_sha256,
        "snapshot_sha256": args.snapshot_sha256,
        "source_identity_sha256": args.source_identity_sha256,
        "source_schema": args.source_schema,
        "source_schema_oid_before": args.source_schema_oid_before,
        "state": "prepared",
        "state_history": [{"at_utc": _utc_now(), "sequence": 1, "state": "prepared"}],
        "target_identity_sha256": args.target_identity_sha256,
        "write_roles": _split_roles(args.write_roles, "writer roles"),
    }


def _store_from_args(args: argparse.Namespace) -> _StateDirectory:
    return _StateDirectory.open(
        Path(args.state_dir), strict=args.strict, test_mode=args.test_mode
    )


def _command_begin(args: argparse.Namespace) -> int:
    store = _store_from_args(args)
    marker = _marker_from_begin(args)
    store.begin(marker)
    print(cast(str, marker["operation_id"]))
    return 0


def _command_transition(args: argparse.Namespace) -> int:
    store = _store_from_args(args)
    state = cast(MarkerState, args.state)
    updates: dict[str, object] = {}
    if state == "fence_intent":
        updates = {
            "acl_topology_sha256": args.acl_topology_sha256,
            "connect_restore_grants": _parse_grants(args.connect_restore_grants),
            "fenced_connect_roles": _split_roles(
                args.fenced_connect_roles, "fenced roles"
            ),
            "public_connect_was_granted": args.public_connect_was_granted == "1",
            "restore_executor_connect_restore_grants": _parse_grants(
                args.restore_executor_connect_restore_grants
            ),
            "source_schema_oid_before": args.source_schema_oid_before,
            "write_roles": _split_roles(args.write_roles, "writer roles"),
        }
    elif state == "fence_release_intent":
        updates = {"terminal_schema_mode": args.terminal_schema_mode}
    elif state == "restore_ready":
        updates = {"restore_schema_oid": args.restore_schema_oid}
    elif state == "switched":
        updates = {
            "app_schema_oid_after_switch": args.app_schema_oid_after_switch,
            "previous_schema_oid_after_switch": args.previous_schema_oid_after_switch,
        }
    if args.test_fail_history_append_once and not args.test_mode:
        _raise("test-only forensic history failure requires test mode")
    store.transition(
        args.operation_id,
        state,
        updates,
        test_fail_history_append=args.test_fail_history_append_once,
    )
    return 0


def _command_failure(args: argparse.Namespace) -> int:
    store = _store_from_args(args)
    store.record_failure(args.operation_id, phase=args.phase, code=args.code)
    return 0


def _command_seal_release_receipt(args: argparse.Namespace) -> int:
    store = _store_from_args(args)
    if args.test_fail_history_append_once and not args.test_mode:
        _raise("test-only forensic history failure requires test mode")
    store.seal_release_receipt(
        args.operation_id,
        intent_marker_sha256=args.intent_marker_sha256,
        receipt_record_sha256=args.receipt_record_sha256,
        test_fail_history_append=args.test_fail_history_append_once,
    )
    return 0


def _command_assert_release_receipt_seal(args: argparse.Namespace) -> int:
    store = _store_from_args(args)
    store.assert_exact_release_receipt_seal(
        args.operation_id,
        intent_marker_sha256=args.intent_marker_sha256,
        receipt_record_sha256=args.receipt_record_sha256,
    )
    return 0


def _command_status(args: argparse.Namespace) -> int:
    store = _store_from_args(args)
    if args.allow_absent:
        current = store.current_if_present()
        if current is None:
            sys.stdout.buffer.write(b'{"active":false}\n')
            return 0
        marker, _ = current
    else:
        marker, _ = store.current()
    sys.stdout.buffer.write(_canonical_json(marker) + b"\n")
    return 0


def _is_canonical_state_directory_alias(value: str) -> bool:
    """공개 CLI가 canonical root store의 별칭을 archive하지 못하게 한다.

    ``Path(...) == DEFAULT_STATE_DIRECTORY`` 같은 문자열 비교는 ``..`` 및
    ``//`` alias를 놓친다.  먼저 resolve된 canonical path를 비교하고, 실제
    directory가 존재할 때는 O_NOFOLLOW fd의 device/inode도 확인한다. 이 함수는
    허용 판단이 아닌 *거부* 경계이므로 path를 열 수 없으면 lexical canonical
    identity만으로도 fail-closed한다.
    """

    candidate = Path(value)
    try:
        if candidate.resolve(strict=False) == DEFAULT_STATE_DIRECTORY.resolve(
            strict=False
        ):
            return True
    except (OSError, RuntimeError):
        # resolve 실패는 canonical store를 public CLI로 열 권한을 주는 근거가
        # 될 수 없다. 아래 fd 비교도 할 수 없으면 noncanonical test store만
        # _StateDirectory.open에서 별도 검증한다.
        return False

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    candidate_fd: int | None = None
    default_fd: int | None = None
    try:
        candidate_fd = os.open(candidate, flags)
        default_fd = os.open(DEFAULT_STATE_DIRECTORY, flags)
        candidate_stat = os.fstat(candidate_fd)
        default_stat = os.fstat(default_fd)
        return (
            candidate_stat.st_dev == default_stat.st_dev
            and candidate_stat.st_ino == default_stat.st_ino
        )
    except OSError:
        return False
    finally:
        if candidate_fd is not None:
            os.close(candidate_fd)
        if default_fd is not None:
            os.close(default_fd)


def _command_acknowledge(args: argparse.Namespace) -> int:
    if not args.confirm:
        _raise("recovery acknowledgement requires --confirm")
    # The canonical production directory is never acknowledgeable through the
    # public helper CLI, even when a caller omits --strict or lies with
    # --test-mode.  Only the trusted entrypoint's in-process primitive can
    # archive that marker after its independent read-only DB proof.
    if (
        not args.test_mode
        or args.strict
        or _is_canonical_state_directory_alias(args.state_dir)
    ):
        _raise("strict recovery acknowledgement must use the trusted entrypoint")
    store = _store_from_args(args)
    store.acknowledge_and_archive(
        args.operation_id, verification_sha256=args.verification_sha256
    )
    return 0


def _add_store_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--test-mode", action="store_true")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M05 hotswap forensic state helper")
    commands = parser.add_subparsers(dest="command", required=True)

    begin = commands.add_parser("begin")
    _add_store_arguments(begin)
    begin.add_argument("--operation-id", default="")
    begin.add_argument("--script-sha256", required=True)
    begin.add_argument("--snapshot-sha256", required=True)
    begin.add_argument("--drain-receipt-sha256", required=True)
    begin.add_argument("--pg-restore-list-sha256", required=True)
    begin.add_argument("--source-identity-sha256", required=True)
    begin.add_argument("--target-identity-sha256", required=True)
    begin.add_argument("--acl-topology-sha256", required=True)
    begin.add_argument("--holder-backend-pid", type=int, required=True)
    begin.add_argument("--source-schema", required=True)
    begin.add_argument("--restore-schema", required=True)
    begin.add_argument("--previous-schema", required=True)
    begin.add_argument("--app-role", required=True)
    begin.add_argument("--fence-executor-role", required=True)
    begin.add_argument("--restore-executor-role", required=True)
    begin.add_argument("--source-schema-oid-before", type=int, required=True)
    begin.add_argument("--write-roles", required=True)

    transition = commands.add_parser("transition")
    _add_store_arguments(transition)
    transition.add_argument("--operation-id", required=True)
    transition.add_argument(
        "--state", choices=sorted(_STATES - {"prepared"}), required=True
    )
    transition.add_argument("--acl-topology-sha256", default="")
    transition.add_argument("--connect-restore-grants", default="")
    transition.add_argument("--restore-executor-connect-restore-grants", default="")
    transition.add_argument("--fenced-connect-roles", default="")
    transition.add_argument(
        "--public-connect-was-granted", choices=("0", "1"), default="0"
    )
    transition.add_argument("--source-schema-oid-before", type=int, default=0)
    transition.add_argument("--write-roles", default="")
    transition.add_argument("--restore-schema-oid", type=int, default=0)
    transition.add_argument("--app-schema-oid-after-switch", type=int, default=0)
    transition.add_argument("--previous-schema-oid-after-switch", type=int, default=0)
    transition.add_argument("--test-fail-history-append-once", action="store_true")
    transition.add_argument("--terminal-schema-mode", choices=("switched",), default="")

    failure = commands.add_parser("failure")
    _add_store_arguments(failure)
    failure.add_argument("--operation-id", required=True)
    failure.add_argument("--phase", required=True)
    failure.add_argument("--code", required=True)

    seal_release_receipt = commands.add_parser("seal-release-receipt")
    _add_store_arguments(seal_release_receipt)
    seal_release_receipt.add_argument("--operation-id", required=True)
    seal_release_receipt.add_argument("--intent-marker-sha256", required=True)
    seal_release_receipt.add_argument("--receipt-record-sha256", required=True)
    seal_release_receipt.add_argument(
        "--test-fail-history-append-once", action="store_true"
    )

    assert_release_receipt_seal = commands.add_parser("assert-release-receipt-seal")
    _add_store_arguments(assert_release_receipt_seal)
    assert_release_receipt_seal.add_argument("--operation-id", required=True)
    assert_release_receipt_seal.add_argument("--intent-marker-sha256", required=True)
    assert_release_receipt_seal.add_argument("--receipt-record-sha256", required=True)

    status = commands.add_parser("status")
    _add_store_arguments(status)
    status.add_argument("--allow-absent", action="store_true")

    acknowledge = commands.add_parser("acknowledge")
    _add_store_arguments(acknowledge)
    acknowledge.add_argument("--operation-id", required=True)
    acknowledge.add_argument("--verification-sha256", required=True)
    acknowledge.add_argument("--confirm", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        handlers = {
            "begin": _command_begin,
            "transition": _command_transition,
            "failure": _command_failure,
            "seal-release-receipt": _command_seal_release_receipt,
            "assert-release-receipt-seal": _command_assert_release_receipt_seal,
            "status": _command_status,
            "acknowledge": _command_acknowledge,
        }
        return handlers[args.command](args)
    except ForensicsError as exc:
        print(f"M05 hotswap forensic state failed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
