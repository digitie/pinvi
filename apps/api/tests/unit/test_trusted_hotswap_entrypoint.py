"""trusted hotswap root entrypoint의 endpoint pinning 회귀."""

from __future__ import annotations

import importlib.util
import socket
import sys
from pathlib import Path

import pytest


def _script_module(filename: str, name: str):
    script = Path(__file__).resolve().parents[4] / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_hotswap_endpoint_pinning_matches_trusted_backup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    backup = _script_module("trusted-backup-entrypoint.py", "trusted_backup_entrypoint")

    def getaddrinfo(host: str, port: int, *, type: int) -> list[tuple[object, ...]]:
        assert host == "postgres"
        assert port == 5432
        assert type == socket.SOCK_STREAM
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", port, 0, 0))]

    monkeypatch.setattr(hotswap.socket, "getaddrinfo", getaddrinfo)
    url = "postgresql+asyncpg://runtime@postgres:5432/pinvi?sslmode=require"
    expected = "postgresql+asyncpg://runtime@postgres:5432/pinvi?sslmode=require&hostaddr=::1"

    assert hotswap.pin_database_url(url) == expected
    assert backup.pin_backup_database_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://runtime@postgres:5432/pinvi?host=other",
        "postgresql://runtime@postgres:5432/pinvi?hostaddr=127.0.0.1",
        "postgresql://runtime@postgres:5432/pinvi?port=6543",
        "postgresql://runtime@postgres:5432/pinvi?service=pinvi",
        "postgresql://runtime@postgres:5432/pinvi?servicefile=/tmp/pg_service.conf",
        "postgresql://runtime@postgres:5432/pinvi?sslmode=require&sslmode=verify-full",
        "postgresql://runtime@postgres:5432/pinvi?=value",
        "postgresql://runtime@postgres:5432/",
        "mysql://runtime@postgres:5432/pinvi",
        "postgresql://runtime@postgres:5432/pinvi#fragment",
    ],
)
def test_hotswap_endpoint_rejects_the_same_ambiguous_vectors_as_backup(url: str) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    backup = _script_module("trusted-backup-entrypoint.py", "trusted_backup_entrypoint")

    with pytest.raises(hotswap.TrustedHotswapError):
        hotswap.pin_database_url(url)
    with pytest.raises(backup.TrustedBackupEndpointError):
        backup.pin_backup_database_url(url)


def test_hotswap_strict_entrypoint_requires_root_and_strict_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    monkeypatch.setattr(hotswap.os, "geteuid", lambda: 1000)
    monkeypatch.setenv("PINVI_ENVIRONMENT", "staging")
    with pytest.raises(hotswap.TrustedHotswapError, match="root"):
        hotswap._strict_environment()

    monkeypatch.setattr(hotswap.os, "geteuid", lambda: 0)
    monkeypatch.setenv("PINVI_ENVIRONMENT", "development")
    with pytest.raises(hotswap.TrustedHotswapError, match="staging or production"):
        hotswap._strict_environment()
