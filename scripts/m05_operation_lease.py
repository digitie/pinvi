"""M05 root-only mutation 경로의 대상별 상호배제 lease.

PostgreSQL advisory lock은 database-scoped라 maintenance database에서 disposable
target을 재생성하는 경로와 target database에서 schema swap을 수행하는 경로를 서로
막지 못한다. 이 모듈은 같은 root-owned forensic state 아래의 target별 flock으로 두
경로를 하나의 N150 execution boundary에서 직렬화한다.
"""

from __future__ import annotations

import fcntl
import hashlib
import ipaddress
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Self
from urllib.parse import parse_qsl, urlsplit

DEFAULT_STATE_DIRECTORY = Path("/var/lib/pinvi/restore-forensics")
_LEASE_DIRECTORY_NAME = "operation-leases"
_DATABASE_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TOKEN_PREFIX = "m05-v1-"


class M05OperationLeaseError(RuntimeError):
    """root-only M05 operation lease를 안전하게 만들거나 잡을 수 없다."""


def _raise(message: str) -> None:
    raise M05OperationLeaseError(message)


def _root_owned_parent_chain(path: Path) -> None:
    if not path.is_absolute():
        _raise("M05 operation lease path is invalid")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except OSError:
            _raise("M05 operation lease parent is unavailable")
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            _raise("M05 operation lease parent permissions are invalid")


def _root_owned_directory(path: Path, *, create: bool = False) -> int:
    if create and not path.exists():
        try:
            path.mkdir(mode=0o700)
        except OSError:
            _raise("M05 operation lease directory is unavailable")
    try:
        metadata = path.lstat()
    except OSError:
        _raise("M05 operation lease directory is unavailable")
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        _raise("M05 operation lease directory permissions are invalid")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
    except OSError:
        _raise("M05 operation lease directory is unavailable")
    return descriptor


def _target_identity(database_url: str) -> tuple[str, str, str]:
    try:
        parsed = urlsplit(database_url)
        port = parsed.port or 5432
    except ValueError as exc:
        raise M05OperationLeaseError(
            "M05 operation lease database URL is invalid"
        ) from exc
    database = parsed.path.removeprefix("/")
    query = parse_qsl(parsed.query, keep_blank_values=True)
    values = {name: value for name, value in query}
    hostaddr = values.get("hostaddr", "")
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or not parsed.netloc
        or len(values) != len(query)
        or _DATABASE_NAME_RE.fullmatch(database) is None
        or not hostaddr
        or not 1 <= port <= 65535
    ):
        _raise("M05 operation lease database URL is invalid")
    try:
        canonical_hostaddr = str(ipaddress.ip_address(hostaddr))
    except ValueError as exc:
        raise M05OperationLeaseError("M05 operation lease hostaddr is invalid") from exc
    return canonical_hostaddr, str(port), database


def operation_lease_token(database_url: str) -> str:
    """pinned endpoint+database만으로 안정적인 target lease token을 만든다."""

    hostaddr, port, database = _target_identity(database_url)
    payload = json.dumps(
        {
            "database": database,
            "hostaddr": hostaddr,
            "port": port,
            "version": "pinvi-m05-operation-lease/v1",
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _TOKEN_PREFIX + hashlib.sha256(payload).hexdigest()


@dataclass
class M05OperationLease:
    """exec까지 유지할 수 있는 root-owned advisory-file descriptor."""

    descriptor: int
    path: Path
    token: str

    def fileno(self) -> int:
        if self.descriptor < 0:
            _raise("M05 operation lease is no longer active")
        return self.descriptor

    def close(self) -> None:
        if self.descriptor < 0:
            return
        descriptor = self.descriptor
        self.descriptor = -1
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(descriptor)
        except OSError:
            pass

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def acquire_root_operation_lease(database_url: str) -> M05OperationLease:
    """strict root mutation 전에 canonical target lease를 non-blocking으로 잡는다."""

    if os.geteuid() != 0:
        _raise("M05 operation lease requires root execution")
    _root_owned_parent_chain(DEFAULT_STATE_DIRECTORY.parent)
    state_descriptor = _root_owned_directory(DEFAULT_STATE_DIRECTORY)
    try:
        lease_directory = DEFAULT_STATE_DIRECTORY / _LEASE_DIRECTORY_NAME
        try:
            os.mkdir(_LEASE_DIRECTORY_NAME, 0o700, dir_fd=state_descriptor)
        except FileExistsError:
            pass
        except OSError:
            _raise("M05 operation lease directory is unavailable")
    finally:
        os.close(state_descriptor)
    lease_directory_descriptor = _root_owned_directory(lease_directory)
    os.close(lease_directory_descriptor)
    token = operation_lease_token(database_url)
    path = lease_directory / f"{token.removeprefix(_TOKEN_PREFIX)}.lock"
    try:
        descriptor = os.open(
            path,
            os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
    except OSError:
        _raise("M05 operation lease is unavailable")
    try:
        os.fchmod(descriptor, 0o600)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            _raise("M05 operation lease permissions are invalid")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise M05OperationLeaseError(
                "another M05 target mutation is already running"
            ) from exc
        return M05OperationLease(descriptor=descriptor, path=path, token=token)
    except Exception:
        os.close(descriptor)
        raise
