"""root-only compose backup endpoint pinning contract."""

from __future__ import annotations

import importlib.util
import socket
from pathlib import Path

import pytest


def _entrypoint_module() -> object:
    script = Path(__file__).resolve().parents[4] / "scripts" / "trusted-backup-entrypoint.py"
    spec = importlib.util.spec_from_file_location("trusted_backup_entrypoint", script)
    if spec is None or spec.loader is None:
        raise AssertionError("trusted backup entrypoint could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _single_address(monkeypatch: pytest.MonkeyPatch, module: object, address: str) -> None:
    def getaddrinfo(host: str, port: int, *, type: int) -> list[tuple[object, ...]]:
        assert host == "app-postgres"
        assert port == 5432
        assert type == socket.SOCK_STREAM
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    monkeypatch.setattr(module.socket, "getaddrinfo", getaddrinfo)  # type: ignore[attr-defined]


def test_trusted_backup_entrypoint_pins_hostname_only_url(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _entrypoint_module()
    _single_address(monkeypatch, module, "172.30.0.9")

    resolved = module.pin_backup_database_url(  # type: ignore[attr-defined]
        "postgresql+asyncpg://pinvi:fixture@app-postgres:5432/pinvi?sslmode=require"
    )

    assert resolved == (
        "postgresql+asyncpg://pinvi:fixture@app-postgres:5432/pinvi?"
        "sslmode=require&hostaddr=172.30.0.9"
    )


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://pinvi:fixture@app-postgres:5432/pinvi?hostaddr=172.30.0.9",
        "postgresql://pinvi:fixture@app-postgres:5432/pinvi?host=other-postgres",
        "postgresql://pinvi:fixture@app-postgres:5432/pinvi?service=pinvi",
    ],
)
def test_trusted_backup_entrypoint_rejects_preconfigured_endpoint(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    module = _entrypoint_module()
    _single_address(monkeypatch, module, "172.30.0.9")

    with pytest.raises(module.TrustedBackupEndpointError, match="endpoint override"):  # type: ignore[attr-defined]
        module.pin_backup_database_url(url)  # type: ignore[attr-defined]


def test_trusted_backup_entrypoint_rejects_ambiguous_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _entrypoint_module()

    def getaddrinfo(host: str, port: int, *, type: int) -> list[tuple[object, ...]]:
        assert host == "app-postgres"
        assert port == 5432
        assert type == socket.SOCK_STREAM
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.30.0.9", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.30.0.10", port)),
        ]

    monkeypatch.setattr(module.socket, "getaddrinfo", getaddrinfo)  # type: ignore[attr-defined]
    with pytest.raises(module.TrustedBackupEndpointError, match="exactly one address"):  # type: ignore[attr-defined]
        module.pin_backup_database_url("postgresql://pinvi:fixture@app-postgres:5432/pinvi")  # type: ignore[attr-defined]


def test_compose_uses_root_endpoint_pinning_entrypoint() -> None:
    root = Path(__file__).resolve().parents[4]
    compose = (root / "infra" / "docker-compose.app.yml").read_text(encoding="utf-8")
    dockerfile = (root / "apps" / "api" / "Dockerfile").read_text(encoding="utf-8")

    assert 'user: "0:0"' in compose
    assert "exec python /app/scripts/trusted-backup-entrypoint.py" in compose
    assert (
        "COPY scripts/trusted-backup-entrypoint.py ./scripts/trusted-backup-entrypoint.py"
        in dockerfile
    )
