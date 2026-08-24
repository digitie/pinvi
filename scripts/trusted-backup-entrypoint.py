#!/usr/bin/env python3
"""운영 root-only backup producer의 DB endpoint를 한 번만 고정한다.

compose의 ``app-backup``만 이 entrypoint를 사용한다.  ordinary API는 raw dump
mount나 producer credential을 받지 않으며, strict backup runner에는 DNS 결과가
``hostaddr``로 결박된 URL만 전달한다.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_STRICT_ENVIRONMENTS = frozenset({"staging", "production"})
_POSTGRES_SCHEMES = frozenset({"postgres", "postgresql", "postgresql+asyncpg"})
_ENDPOINT_QUERY_KEYS = frozenset({"host", "hostaddr", "port", "service", "servicefile"})


class TrustedBackupEndpointError(ValueError):
    """strict backup producer가 endpoint를 단일하게 고정할 수 없다."""


def _resolved_hostaddr(hostname: str, port: int) -> str:
    try:
        records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise TrustedBackupEndpointError("backup database host could not be resolved") from exc

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
        raise TrustedBackupEndpointError("backup database host must resolve to exactly one address")
    return addresses.pop()


def pin_backup_database_url(value: str) -> str:
    """hostname-only PostgreSQL URL에 단일 DNS 결과를 ``hostaddr``로 추가한다."""

    if not value or any(character.isspace() for character in value):
        raise TrustedBackupEndpointError("backup database URL is missing or malformed")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port or 5432
    except ValueError as exc:
        raise TrustedBackupEndpointError("backup database URL is invalid") from exc
    if (
        parsed.scheme not in _POSTGRES_SCHEMES
        or not parsed.netloc
        or hostname is None
        or not parsed.path.startswith("/")
        or parsed.path == "/"
        or parsed.fragment
    ):
        raise TrustedBackupEndpointError("backup database URL is not a canonical PostgreSQL URL")

    query = parse_qsl(parsed.query, keep_blank_values=True)
    names = [name for name, _ in query]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise TrustedBackupEndpointError("backup database URL query is ambiguous")
    if _ENDPOINT_QUERY_KEYS.intersection(names):
        raise TrustedBackupEndpointError("backup database URL must not preconfigure an endpoint override")

    query.append(("hostaddr", _resolved_hostaddr(hostname, port)))
    return urlunsplit(parsed._replace(query=urlencode(query, safe=":")))


def _strict_producer_environment() -> None:
    if os.geteuid() != 0:
        raise TrustedBackupEndpointError("trusted backup producer requires root execution")
    if os.environ.get("PINVI_ENVIRONMENT", "") not in _STRICT_ENVIRONMENTS:
        raise TrustedBackupEndpointError("trusted backup producer requires staging or production")
    if os.environ.get("PINVI_BACKUP_TRUSTED", "") != "1":
        raise TrustedBackupEndpointError("trusted backup producer marker is missing")


def main() -> int:
    try:
        _strict_producer_environment()
        database_url = pin_backup_database_url(os.environ.get("PINVI_BACKUP_DATABASE_URL", ""))
    except TrustedBackupEndpointError as exc:
        print(f"trusted backup endpoint preparation failed: {exc}", file=sys.stderr)
        return 3

    runner = Path(__file__).with_name("backup-db.sh")
    if runner.is_symlink() or not runner.is_file():
        print("trusted backup endpoint preparation failed: canonical backup runner is unavailable", file=sys.stderr)
        return 3
    environment = os.environ.copy()
    environment["PINVI_BACKUP_DATABASE_URL"] = database_url
    environment["PINVI_BACKUP_ENDPOINT_PINNED_BY_PRODUCER"] = "1"
    os.execve(str(runner), [str(runner)], environment)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
