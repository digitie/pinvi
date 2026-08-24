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
_STATE_ORDER: Final = (
    "prepared",
    "fence_intent",
    "fence_applied",
    "restore_ready",
    "switched",
    "fence_release_intent",
    "fence_released",
)
_STATES: Final = frozenset(_STATE_ORDER)
_NEXT_STATES: Final = {
    "prepared": frozenset({"fence_intent"}),
    "fence_intent": frozenset({"fence_applied"}),
    "fence_applied": frozenset({"restore_ready"}),
    "restore_ready": frozenset({"switched"}),
    "switched": frozenset({"fence_release_intent"}),
    "fence_release_intent": frozenset({"fence_released"}),
}
MarkerState = Literal[
    "prepared",
    "fence_intent",
    "fence_applied",
    "restore_ready",
    "switched",
    "fence_release_intent",
    "fence_released",
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
    if type(value) is not int or cast(int, value) < 1:
        _raise(f"forensic marker {field} is invalid")
    return cast(int, value)


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


def _validate_state_history(
    value: object, *, state: str, recovery_required: bool
) -> list[dict[str, object]]:
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
            or cast(int, sequence) != previous_sequence + 1
            or not isinstance(at_utc, str)
            or not at_utc.endswith("Z")
        ):
            _raise("forensic marker state_history is invalid")
        if previous_state is not None:
            normal_transition = item_state in _NEXT_STATES.get(
                previous_state, frozenset()
            )
            cleanup_transition = (
                recovery_required
                and item_state == "fence_release_intent"
                and previous_state
                in {"fence_intent", "fence_applied", "restore_ready", "switched"}
            )
            if not normal_transition and not cleanup_transition:
                _raise("forensic marker state_history transition is invalid")
        history.append(
            {"at_utc": at_utc, "sequence": cast(int, sequence), "state": item_state}
        )
        previous_sequence = cast(int, sequence)
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
        "post_release_acl_topology_sha256",
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
            value.get("state_history"), state=state, recovery_required=recovery_required
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
    if marker["write_roles"] != [marker["app_role"]]:
        _raise("forensic marker writer inventory is not the strict M05 app role")
    for name in optional:
        if name in {"terminal_schema_mode", "post_release_acl_topology_sha256"}:
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
        marker["fenced_connect_roles"] or marker["connect_restore_grants"]
    ):
        _raise("forensic marker pre-fence inventory is not empty")
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
    if state in {
        "fence_release_intent",
        "fence_released",
    } and terminal_schema_mode not in {
        "no_switch",
        "switched",
    }:
        _raise("forensic marker terminal schema mode is invalid")
    if (
        state not in {"fence_release_intent", "fence_released"}
        and terminal_schema_mode is not None
    ):
        _raise("forensic marker terminal schema mode is premature")
    if terminal_schema_mode is not None:
        marker["terminal_schema_mode"] = terminal_schema_mode
    post_release_acl_topology = value.get("post_release_acl_topology_sha256")
    if state == "fence_released" and post_release_acl_topology is None:
        _raise("forensic marker post-release acl topology is missing")
    if state != "fence_released" and post_release_acl_topology is not None:
        _raise("forensic marker post-release acl topology is premature")
    if post_release_acl_topology is not None:
        marker["post_release_acl_topology_sha256"] = _validate_sha256(
            post_release_acl_topology, "post-release acl topology"
        )
    if terminal_schema_mode == "switched" and (
        "app_schema_oid_after_switch" not in marker
        or "previous_schema_oid_after_switch" not in marker
    ):
        _raise("forensic marker switch oid matrix is missing")
    if terminal_schema_mode == "no_switch" and (
        "app_schema_oid_after_switch" in marker
        or "previous_schema_oid_after_switch" in marker
    ):
        _raise("forensic marker no-switch terminal state has a switch oid matrix")
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
    if terminal_schema_mode == "no_switch" and switched:
        _raise("forensic marker no-switch terminal mode follows a switch state")
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
        self, operation_id: str, state: MarkerState, updates: dict[str, object]
    ) -> None:
        with self._exclusive_lock():
            marker, _ = self._current_unlocked()
            if marker["operation_id"] != operation_id:
                _raise("forensic marker operation does not match")
            current_state = cast(str, marker["state"])
            if marker["recovery_required"]:
                historical_states = {
                    cast(str, item["state"])
                    for item in cast(list[dict[str, object]], marker["state_history"])
                }
                expected_mode = (
                    "switched" if "switched" in historical_states else "no_switch"
                )
                cleanup_transition = (
                    state == "fence_release_intent"
                    and current_state
                    in {"fence_intent", "fence_applied", "restore_ready", "switched"}
                    and updates == {"terminal_schema_mode": expected_mode}
                ) or (
                    state == "fence_released"
                    and current_state == "fence_release_intent"
                    and set(updates) == {"post_release_acl_topology_sha256"}
                    and isinstance(updates["post_release_acl_topology_sha256"], str)
                    and _SHA256_RE.fullmatch(
                        cast(str, updates["post_release_acl_topology_sha256"])
                    )
                    is not None
                )
                if not cleanup_transition:
                    _raise("forensic marker is recovery latched")
            elif state not in _NEXT_STATES.get(current_state, frozenset()):
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
        self, operation_id: str, *, verification_sha256: str
    ) -> None:
        verification_sha256 = _validate_sha256(
            verification_sha256, "recovery verification"
        )
        with self._exclusive_lock():
            marker, raw = self._current_unlocked()
            if marker["operation_id"] != operation_id:
                _raise("forensic marker operation does not match")
            if (
                marker["state"] not in {"prepared", "fence_released"}
                and not marker["recovery_required"]
            ):
                _raise("forensic marker is not safe for recovery acknowledgement")
            marker_sha256 = _sha256(raw)
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
                    _raise(
                        "forensic recovery acknowledgement does not match the marker"
                    )
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
                        "sequence": len(cast(list[object], marker["state_history"])),
                        "state": marker["state"],
                        "type": "recovery_acknowledged",
                        "verification_sha256": verification_sha256,
                    },
                )
            self._unlink_current()


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
            "source_schema_oid_before": args.source_schema_oid_before,
            "write_roles": _split_roles(args.write_roles, "writer roles"),
        }
    elif state == "fence_release_intent":
        updates = {"terminal_schema_mode": args.terminal_schema_mode}
    elif state == "fence_released":
        updates = {
            "post_release_acl_topology_sha256": args.post_release_acl_topology_sha256
        }
    elif state == "restore_ready":
        updates = {"restore_schema_oid": args.restore_schema_oid}
    elif state == "switched":
        updates = {
            "app_schema_oid_after_switch": args.app_schema_oid_after_switch,
            "previous_schema_oid_after_switch": args.previous_schema_oid_after_switch,
        }
    store.transition(args.operation_id, state, updates)
    return 0


def _command_failure(args: argparse.Namespace) -> int:
    store = _store_from_args(args)
    store.record_failure(args.operation_id, phase=args.phase, code=args.code)
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


def _command_acknowledge(args: argparse.Namespace) -> int:
    if not args.confirm:
        _raise("recovery acknowledgement requires --confirm")
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
    transition.add_argument("--fenced-connect-roles", default="")
    transition.add_argument(
        "--public-connect-was-granted", choices=("0", "1"), default="0"
    )
    transition.add_argument("--source-schema-oid-before", type=int, default=0)
    transition.add_argument("--write-roles", default="")
    transition.add_argument("--restore-schema-oid", type=int, default=0)
    transition.add_argument("--app-schema-oid-after-switch", type=int, default=0)
    transition.add_argument("--previous-schema-oid-after-switch", type=int, default=0)
    transition.add_argument("--post-release-acl-topology-sha256", default="")
    transition.add_argument(
        "--terminal-schema-mode", choices=("no_switch", "switched"), default=""
    )

    failure = commands.add_parser("failure")
    _add_store_arguments(failure)
    failure.add_argument("--operation-id", required=True)
    failure.add_argument("--phase", required=True)
    failure.add_argument("--code", required=True)

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
            "status": _command_status,
            "acknowledge": _command_acknowledge,
        }
        return handlers[args.command](args)
    except ForensicsError as exc:
        print(f"M05 hotswap forensic state failed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
