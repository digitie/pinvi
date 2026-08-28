#!/usr/bin/env python3
"""M05 isolated Compose 변이의 Manager admission 검증기."""

from __future__ import annotations

import json
import os
import re
import stat
import sys
from pathlib import Path

_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_PINSET = re.compile(r"[0-9a-f]{64}\Z")
_TRANSACTION = re.compile(r"[0-9a-f]{32}\Z")
_KIND = "pinvi-m05-isolated-manager-admission-v1"
_MAX_BYTES = 16_384


class AdmissionError(Exception):
    """Admission 파일이 trusted Manager 경계가 아님을 나타낸다."""


def _required_hex(value: object, *, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise AdmissionError
    return value


def _read_root_owned_file(path: str, *, expected_uid: int) -> bytes:
    candidate = Path(path)
    if not candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise AdmissionError
    directory_fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in candidate.parts[1:-1]:
            next_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd
        directory = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(directory.st_mode)
            or directory.st_uid != expected_uid
            or stat.S_IMODE(directory.st_mode) != 0o700
        ):
            raise AdmissionError
        file_fd = os.open(
            candidate.name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=directory_fd,
        )
    finally:
        os.close(directory_fd)
    try:
        metadata = os.fstat(file_fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != expected_uid
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise AdmissionError
        value = os.read(file_fd, _MAX_BYTES + 1)
    finally:
        os.close(file_fd)
    if len(value) > _MAX_BYTES:
        raise AdmissionError
    return value


def validate_admission(
    *, path: str, project: str, pinvi_source_revision: str, pinset_sha256: str, expected_uid: int = 0
) -> None:
    transaction_prefix = "m05i-pinvi-"
    if not project.startswith(transaction_prefix):
        raise AdmissionError
    transaction = project.removeprefix(transaction_prefix)
    _required_hex(transaction, pattern=_TRANSACTION)
    _required_hex(pinvi_source_revision, pattern=_COMMIT)
    _required_hex(pinset_sha256, pattern=_PINSET)
    try:
        value = json.loads(_read_root_owned_file(path, expected_uid=expected_uid))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdmissionError from error
    if not isinstance(value, dict) or set(value) != {
        "kind",
        "manager_source_revision",
        "map_source_revision",
        "pinset_sha256",
        "pinvi_source_revision",
        "transaction_id",
        "version",
    }:
        raise AdmissionError
    if value["kind"] != _KIND or value["version"] != 1:
        raise AdmissionError
    _required_hex(value["manager_source_revision"], pattern=_COMMIT)
    _required_hex(value["map_source_revision"], pattern=_COMMIT)
    if _required_hex(value["pinvi_source_revision"], pattern=_COMMIT) != pinvi_source_revision:
        raise AdmissionError
    if _required_hex(value["pinset_sha256"], pattern=_PINSET) != pinset_sha256:
        raise AdmissionError
    if _required_hex(value["transaction_id"], pattern=_TRANSACTION) != transaction:
        raise AdmissionError


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        return 2
    try:
        validate_admission(
            path=argv[1],
            project=argv[2],
            pinvi_source_revision=argv[3],
            pinset_sha256=argv[4],
        )
    except AdmissionError:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
