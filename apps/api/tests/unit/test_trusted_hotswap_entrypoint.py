"""trusted hotswap root entrypoint의 endpoint pinning 회귀."""

from __future__ import annotations

import importlib.util
import json
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


def _recovery_marker(
    *,
    state: str = "fence_released",
    terminal_schema_mode: str = "switched",
    recovery_required: bool = False,
) -> dict[str, object]:
    marker: dict[str, object] = {
        "acl_topology_sha256": "b" * 64,
        "app_role": "pinvi_app",
        "connect_restore_grants": [{"grant_option": False, "role": "pinvi_app"}],
        "fence_executor_role": "pinvi_fence",
        "operation_id": "123e4567-e89b-42d3-a456-426614174000",
        "previous_schema": "app_previous_1",
        "public_connect_was_granted": True,
        "recovery_required": recovery_required,
        "restore_schema": "app_restore_1",
        "source_schema": "app",
        "source_schema_oid_before": 100,
        "state": state,
        "target_identity_sha256": "a" * 64,
    }
    if state == "prepared":
        marker["connect_restore_grants"] = []
        marker["public_connect_was_granted"] = False
        return marker
    marker["post_release_acl_topology_sha256"] = "c" * 64
    marker["terminal_schema_mode"] = terminal_schema_mode
    if terminal_schema_mode == "switched":
        marker.update(
            {
                "app_schema_oid_after_switch": 200,
                "previous_schema_oid_after_switch": 100,
                "restore_schema_oid": 200,
            }
        )
    else:
        marker["restore_schema_oid"] = 200
    return marker


def _safe_observation(
    *,
    app_oid: str,
    previous_oid: str,
    restore_oid: str,
    connect_grants: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "advisory_lock_absent": True,
        "app_connect": True,
        "app_oid": app_oid,
        "app_role_safe": True,
        "app_usage": True,
        "connect_restore_grants": connect_grants
        if connect_grants is not None
        else [{"grant_option": False, "role": "pinvi_app"}],
        "fence_role_safe": True,
        "previous_oid": previous_oid,
        "public_connect_granted": True,
        "restore_executor_role": "pinvi_owner",
        "restore_executor_safe": True,
        "restore_oid": restore_oid,
    }


def _patch_recovery_reads(
    monkeypatch: pytest.MonkeyPatch,
    hotswap,
    observation: dict[str, object],
    topology_sha256: str,
) -> None:
    monkeypatch.setattr(
        hotswap,
        "_identity_sha256_from_psql",
        lambda _: ("a" * 64, {"database": "pinvi"}),
    )

    def run_psql(
        _: str,
        *,
        command: str | None = None,
        file: Path | None = None,
        variables: dict[str, str] | None = None,
        failure: str,
    ) -> str:
        assert variables is not None
        assert variables["app_role"] == "pinvi_app"
        if command is not None:
            return json.dumps(observation)
        assert file == Path("/trusted/m05_hotswap_topology.sql")
        return f"{topology_sha256}\n"

    monkeypatch.setattr(hotswap, "_run_psql", run_psql)


def test_recovery_proof_accepts_the_verified_switched_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    marker = _recovery_marker()
    _patch_recovery_reads(
        monkeypatch,
        hotswap,
        _safe_observation(app_oid="200", previous_oid="100", restore_oid=""),
        "c" * 64,
    )

    result = hotswap._safe_recovery_observation(
        marker,
        "postgresql://unused",
        Path("/trusted/m05_hotswap_topology.sql"),
    )

    assert hotswap._SHA256_RE.fullmatch(result)


def test_recovery_proof_accepts_no_switch_and_prepared_only_at_exact_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    no_switch_marker = _recovery_marker(terminal_schema_mode="no_switch", recovery_required=True)
    _patch_recovery_reads(
        monkeypatch,
        hotswap,
        _safe_observation(app_oid="100", previous_oid="", restore_oid="200"),
        "c" * 64,
    )
    assert hotswap._SHA256_RE.fullmatch(
        hotswap._safe_recovery_observation(
            no_switch_marker,
            "postgresql://unused",
            Path("/trusted/m05_hotswap_topology.sql"),
        )
    )

    prepared_marker = _recovery_marker(state="prepared")
    prepared_observation = _safe_observation(
        app_oid="100",
        previous_oid="",
        restore_oid="",
        connect_grants=[],
    )
    prepared_observation["public_connect_granted"] = True
    _patch_recovery_reads(monkeypatch, hotswap, prepared_observation, "b" * 64)
    assert hotswap._SHA256_RE.fullmatch(
        hotswap._safe_recovery_observation(
            prepared_marker,
            "postgresql://unused",
            Path("/trusted/m05_hotswap_topology.sql"),
        )
    )


def test_recovery_proof_rejects_connect_acl_or_topology_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    marker = _recovery_marker()
    _patch_recovery_reads(
        monkeypatch,
        hotswap,
        _safe_observation(
            app_oid="200",
            previous_oid="100",
            restore_oid="",
            connect_grants=[],
        ),
        "c" * 64,
    )
    with pytest.raises(hotswap.TrustedHotswapError, match="CONNECT"):
        hotswap._safe_recovery_observation(
            marker,
            "postgresql://unused",
            Path("/trusted/m05_hotswap_topology.sql"),
        )

    _patch_recovery_reads(
        monkeypatch,
        hotswap,
        _safe_observation(app_oid="200", previous_oid="100", restore_oid=""),
        "d" * 64,
    )
    with pytest.raises(hotswap.TrustedHotswapError, match="topology"):
        hotswap._safe_recovery_observation(
            marker,
            "postgresql://unused",
            Path("/trusted/m05_hotswap_topology.sql"),
        )
