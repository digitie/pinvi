"""trusted hotswap root entrypoint의 endpoint pinning 회귀."""

from __future__ import annotations

import importlib.util
import json
import shlex
import socket
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

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


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://runtime@postgres:5432/pinvi?user=other",
        "postgresql://runtime@postgres:5432/pinvi?dbname=evil",
        "postgresql://runtime@postgres:5432/pinvi?options=-c%20default_transaction_read_only%3Doff",
        "postgresql://runtime@postgres:5432/pinvi?op%74ions=-c%20role%3Dpinvi_app",
        "postgresql://runtime@postgres:5432/pinvi?options=-c%20role%3Dpinvi_app",
        "postgresql://runtime@postgres:5432/pinvi?application_name=untrusted",
    ],
)
def test_hotswap_endpoint_rejects_all_non_tls_query_overrides_before_dns(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    monkeypatch.setattr(
        hotswap.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("rejected URL reached DNS resolution")
        ),
    )

    with pytest.raises(hotswap.TrustedHotswapError, match="query is not allowed"):
        hotswap.pin_database_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://runtime@postgres:5432/pinvi?sslmode=",
        "postgresql://runtime@postgres:5432/pinvi?sslmode=invalid",
    ],
)
def test_hotswap_endpoint_rejects_invalid_tls_query_values_before_dns(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    monkeypatch.setattr(
        hotswap.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("rejected URL reached DNS resolution")
        ),
    )

    with pytest.raises(hotswap.TrustedHotswapError, match="sslmode is invalid"):
        hotswap.pin_database_url(url)


def test_hotswap_strict_entrypoint_requires_root_and_strict_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    monkeypatch.setattr(hotswap.os, "geteuid", lambda: 1000)
    with pytest.raises(hotswap.TrustedHotswapError, match="root"):
        hotswap._strict_environment()

    monkeypatch.setattr(hotswap.os, "geteuid", lambda: 0)
    monkeypatch.setenv("PINVI_ENVIRONMENT", "staging")
    with pytest.raises(hotswap.TrustedHotswapError, match="sanitized root wrapper"):
        hotswap._strict_environment()


def _trusted_configuration(hotswap):
    return hotswap.TrustedHotswapConfiguration(
        app_role="pinvi_app",
        environment="staging",
        fence_database_url="postgresql://fence@target/pinvi",
        restore_database_url="postgresql://owner@target/pinvi",
        source_database_name="pinvi_source",
        source_database_oid="100",
        source_hostaddr="192.0.2.10",
        source_port="5432",
        source_schema="app",
        source_system_identifier="200",
        trusted_backup_dir="/srv/pinvi/restore-trust",
    )


def _trusted_configuration_payload() -> dict[str, object]:
    return {
        "app_role": "pinvi_app",
        "environment": "staging",
        "fence_database_url": "postgresql://fence@target/pinvi",
        "restore_database_url": "postgresql://owner@target/pinvi",
        "source_identity": {
            "database_name": "pinvi_source",
            "database_oid": "100",
            "hostaddr": "192.0.2.10",
            "port": "5432",
            "system_identifier": "200",
        },
        "source_schema": "app",
        "trusted_backup_dir": "/srv/pinvi/restore-trust",
    }


def _sanitize_root_wrapper_environment(monkeypatch: pytest.MonkeyPatch, hotswap) -> None:
    for name in tuple(hotswap.os.environ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PATH", hotswap._SAFE_ENVIRONMENT["PATH"])


def test_root_configuration_accepts_only_exact_root_owned_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    monkeypatch.setattr(hotswap, "_safe_parent_chain", lambda _: None)
    monkeypatch.setattr(
        hotswap,
        "_safe_root_only_file",
        lambda _path, *, mode: json.dumps(_trusted_configuration_payload()).encode(),
    )

    assert hotswap._load_trusted_configuration() == _trusted_configuration(hotswap)


@pytest.mark.parametrize(
    "payload",
    [
        b'{"environment":"staging","environment":"production"}',
        json.dumps({**_trusted_configuration_payload(), "unexpected": True}).encode(),
        json.dumps(
            {
                **_trusted_configuration_payload(),
                "source_identity": {"database_name": "pinvi_source"},
            }
        ).encode(),
        json.dumps({**_trusted_configuration_payload(), "trusted_backup_dir": "relative"}).encode(),
    ],
)
def test_root_configuration_rejects_malformed_or_ambiguous_input_before_runner(
    monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    monkeypatch.setattr(hotswap, "_safe_parent_chain", lambda _: None)
    monkeypatch.setattr(hotswap, "_safe_root_only_file", lambda _path, *, mode: payload)

    with pytest.raises(hotswap.TrustedHotswapError, match="configuration"):
        hotswap._load_trusted_configuration()


def test_prepare_drain_receipt_uses_only_static_config_and_a_quiescent_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    _sanitize_root_wrapper_environment(monkeypatch, hotswap)
    monkeypatch.setattr(hotswap.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        hotswap, "_load_trusted_configuration", lambda: _trusted_configuration(hotswap)
    )
    monkeypatch.setattr(
        hotswap,
        "_canonical_runner_paths",
        lambda: (
            Path("/trusted/restore-hotswap.sh"),
            Path("/trusted/m05_hotswap_forensics.py"),
            Path("/trusted/m05_hotswap_topology.sql"),
        ),
    )
    monkeypatch.setattr(hotswap, "_assert_no_active_marker", lambda _: None)
    monkeypatch.setattr(hotswap, "pin_database_url", lambda value: f"pinned:{value}")
    monkeypatch.setattr(
        hotswap,
        "_safe_root_only_directory",
        lambda _path, *, mode: Path("/srv/pinvi/restore-trust"),
    )
    monkeypatch.setattr(hotswap, "_trusted_snapshot_sha256", lambda *_: "b" * 64)
    monkeypatch.setattr(hotswap, "_target_identity_environment", lambda _: ({}, "a" * 64))
    quiescent_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        hotswap,
        "_assert_drain_quiescent",
        lambda database_url, app_role: quiescent_calls.append((database_url, app_role)),
    )
    written: dict[str, object] = {}
    monkeypatch.setattr(hotswap, "_write_trusted_drain_receipt", written.update)

    assert (
        hotswap._prepare_drain_receipt(
            Namespace(
                confirm=True,
                operation_id="123e4567-e89b-42d3-a456-426614174000",
                snapshot="/srv/pinvi/restore-trust/pinvi.dump",
            )
        )
        == 0
    )

    assert quiescent_calls == [("pinned:postgresql://owner@target/pinvi", "pinvi_app")]
    assert written["app_role"] == "pinvi_app"
    assert written["operation_id"] == "123e4567-e89b-42d3-a456-426614174000"
    assert written["snapshot_sha256"] == "b" * 64
    assert written["source_schema"] == "app"
    assert written["target_identity_sha256"] == "a" * 64
    assert written["quiescent"] is True
    assert written["version"] == 1


def test_prepare_drain_receipt_requires_confirmation_before_any_trusted_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    _sanitize_root_wrapper_environment(monkeypatch, hotswap)
    monkeypatch.setattr(hotswap.os, "geteuid", lambda: 0)

    def must_not_run(*_args, **_kwargs):
        raise AssertionError("unconfirmed drain receipt reached trusted I/O")

    monkeypatch.setattr(hotswap, "_load_trusted_configuration", must_not_run)
    with pytest.raises(hotswap.TrustedHotswapError, match="requires --confirm"):
        hotswap._prepare_drain_receipt(
            Namespace(
                confirm=False,
                operation_id="123e4567-e89b-42d3-a456-426614174000",
                snapshot="/srv/pinvi/restore-trust/pinvi.dump",
            )
        )


def test_drain_receipt_writer_refuses_pending_or_symlinked_replacement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    state_directory = tmp_path / "restore-forensics"
    state_directory.mkdir(mode=0o700)
    receipt_path = state_directory / "drain-receipt.json"
    monkeypatch.setattr(hotswap, "_DRAIN_RECEIPT_PATH", receipt_path)
    monkeypatch.setattr(hotswap, "_safe_root_only_directory", lambda path, *, mode: Path(path))
    original_fstat = hotswap.os.fstat

    def root_owned_fstat(descriptor: int):
        metadata = original_fstat(descriptor)
        return SimpleNamespace(
            st_mode=(metadata.st_mode & ~0o777) | 0o600,
            st_size=metadata.st_size,
            st_uid=0,
        )

    monkeypatch.setattr(hotswap.os, "fstat", root_owned_fstat)
    receipt = {
        "operation_id": "123e4567-e89b-42d3-a456-426614174000",
        "version": 1,
    }
    hotswap._write_trusted_drain_receipt(receipt)
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == receipt
    with pytest.raises(hotswap.TrustedHotswapError, match="already pending"):
        hotswap._write_trusted_drain_receipt(receipt)

    receipt_path.unlink()
    target = tmp_path / "outside-receipt.json"
    target.write_text("outside", encoding="utf-8")
    receipt_path.symlink_to(target)
    with pytest.raises(hotswap.TrustedHotswapError, match="already pending"):
        hotswap._write_trusted_drain_receipt(receipt)
    assert target.read_text(encoding="utf-8") == "outside"


def test_drain_receipt_consumption_archives_then_unlinks_the_pending_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    state_directory = tmp_path / "restore-forensics"
    state_directory.mkdir(mode=0o700)
    receipt_path = state_directory / "drain-receipt.json"
    payload = b'{"operation_id":"123e4567-e89b-42d3-a456-426614174000"}\n'
    receipt_path.write_bytes(payload)
    monkeypatch.setattr(hotswap, "_DRAIN_RECEIPT_PATH", receipt_path)
    monkeypatch.setattr(hotswap, "_safe_root_only_directory", lambda path, *, mode: Path(path))
    monkeypatch.setattr(hotswap, "_safe_root_only_file", lambda _path, *, mode: payload)

    hotswap._consume_trusted_drain_receipt(
        "123e4567-e89b-42d3-a456-426614174000", hotswap.hashlib.sha256(payload).hexdigest()
    )

    archived = (
        state_directory / "consumed-drain-receipts" / "123e4567-e89b-42d3-a456-426614174000.json"
    )
    assert archived.read_bytes() == payload
    assert not receipt_path.exists()


def test_drain_receipt_consumption_latches_archive_if_unlink_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    state_directory = tmp_path / "restore-forensics"
    state_directory.mkdir(mode=0o700)
    receipt_path = state_directory / "drain-receipt.json"
    payload = b'{"operation_id":"123e4567-e89b-42d3-a456-426614174000"}\n'
    receipt_path.write_bytes(payload)
    monkeypatch.setattr(hotswap, "_DRAIN_RECEIPT_PATH", receipt_path)
    monkeypatch.setattr(hotswap, "_safe_root_only_directory", lambda path, *, mode: Path(path))
    monkeypatch.setattr(hotswap, "_safe_root_only_file", lambda _path, *, mode: payload)
    monkeypatch.setattr(hotswap.os, "unlink", lambda _path: (_ for _ in ()).throw(OSError()))

    with pytest.raises(hotswap.TrustedHotswapError, match="could not be consumed"):
        hotswap._consume_trusted_drain_receipt(
            "123e4567-e89b-42d3-a456-426614174000",
            hotswap.hashlib.sha256(payload).hexdigest(),
        )

    archived = (
        state_directory / "consumed-drain-receipts" / "123e4567-e89b-42d3-a456-426614174000.json"
    )
    assert archived.read_bytes() == payload
    assert receipt_path.read_bytes() == payload


def _recovery_marker(
    *,
    state: str = "fence_release_intent",
    terminal_schema_mode: str = "switched",
    recovery_required: bool = False,
) -> dict[str, object]:
    marker: dict[str, object] = {
        "acl_topology_sha256": "b" * 64,
        "app_role": "pinvi_app",
        "connect_restore_grants": [{"grant_option": False, "role": "pinvi_app"}],
        "drain_receipt_sha256": "d" * 64,
        "fence_executor_role": "pinvi_fence",
        "operation_id": "123e4567-e89b-42d3-a456-426614174000",
        "pg_restore_list_sha256": "e" * 64,
        "previous_schema": "app_previous_1",
        "public_connect_was_granted": True,
        "recovery_required": recovery_required,
        "restore_executor_connect_restore_grants": [],
        "restore_executor_role": "pinvi_owner",
        "restore_schema": "app_restore_1",
        "source_schema": "app",
        "source_identity_sha256": "f" * 64,
        "source_schema_oid_before": 100,
        "state": state,
        "script_sha256": "1" * 64,
        "snapshot_sha256": "2" * 64,
        "target_identity_sha256": "a" * 64,
    }
    if state == "prepared":
        marker["connect_restore_grants"] = []
        marker["public_connect_was_granted"] = False
        return marker
    marker["terminal_schema_mode"] = terminal_schema_mode
    if terminal_schema_mode == "switched":
        marker.update(
            {
                "app_schema_oid_after_switch": 200,
                "previous_schema_oid_after_switch": 100,
                "restore_schema_oid": 200,
            }
        )
    return marker


def _terminal_receipt() -> dict[str, object]:
    return {
        "post_release_acl_topology_sha256": "c" * 64,
        "record_sha256": "8" * 64,
    }


def _safe_observation(
    *,
    app_oid: str,
    previous_oid: str,
    restore_oid: str,
    connect_grants: list[dict[str, object]] | None = None,
    restore_executor_grants: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "advisory_lock_absent": True,
        "app_connect": True,
        "app_database_create_absent": True,
        "app_oid": app_oid,
        "app_role_safe": True,
        "app_public_create_absent": True,
        "app_usage": True,
        "connect_restore_grants": connect_grants
        if connect_grants is not None
        else [{"grant_option": False, "role": "pinvi_app"}],
        "fence_role_safe": True,
        "previous_oid": previous_oid,
        "public_connect_granted": True,
        "restore_executor_role": "pinvi_owner",
        "restore_executor_connect_restore_grants": restore_executor_grants
        if restore_executor_grants is not None
        else [],
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
    monkeypatch.setattr(
        hotswap,
        "_release_receipt_topology_sha256",
        lambda _database_url, _fields: (topology_sha256, "a" * 64),
    )


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
        marker_sha256="7" * 64,
        receipt=_terminal_receipt(),
        fence_database_url="postgresql://fence",
    )

    assert hotswap._SHA256_RE.fullmatch(result)


def test_recovery_proof_accepts_prepared_only_at_exact_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
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
            marker_sha256="7" * 64,
            receipt=None,
            fence_database_url=None,
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
            marker_sha256="7" * 64,
            receipt=_terminal_receipt(),
            fence_database_url="postgresql://fence",
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
            marker_sha256="7" * 64,
            receipt=_terminal_receipt(),
            fence_database_url="postgresql://fence",
        )


def test_recovery_proof_rejects_restore_executor_connect_grant_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    marker = _recovery_marker()
    marker["restore_executor_connect_restore_grants"] = [
        {"grant_option": False, "role": "pinvi_owner"}
    ]
    _patch_recovery_reads(
        monkeypatch,
        hotswap,
        _safe_observation(
            app_oid="200",
            previous_oid="100",
            restore_oid="",
            restore_executor_grants=[],
        ),
        "c" * 64,
    )

    with pytest.raises(hotswap.TrustedHotswapError, match="CONNECT"):
        hotswap._safe_recovery_observation(
            marker,
            "postgresql://unused",
            Path("/trusted/m05_hotswap_topology.sql"),
            marker_sha256="7" * 64,
            receipt=_terminal_receipt(),
            fence_database_url="postgresql://fence",
        )


def test_root_recovery_reads_release_receipt_before_acknowledgement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """release window 직후 marker는 DB receipt 검증 없이는 종료 처리할 수 없다."""

    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    marker = _recovery_marker(state="fence_release_intent")
    marker_sha256 = hotswap.hashlib.sha256(hotswap._canonical_json(marker)).hexdigest()
    forensics = Path("/trusted/forensics")
    topology = Path("/trusted/m05_hotswap_topology.sql")
    receipt = {"record_sha256": "8" * 64}
    receipt_calls: list[tuple[dict[str, object], str, str]] = []
    acknowledgement: list[tuple[Path, str, str, str, str | None]] = []

    monkeypatch.setattr(hotswap, "_strict_environment", lambda: None)
    monkeypatch.setattr(
        hotswap, "_load_trusted_configuration", lambda: _trusted_configuration(hotswap)
    )
    monkeypatch.setattr(
        hotswap,
        "_canonical_runner_paths",
        lambda: (Path("/trusted/restore-hotswap.sh"), forensics, topology),
    )
    monkeypatch.setattr(hotswap, "_read_marker", lambda _forensics: marker)

    def assert_current_history(observed_forensics: Path, *, operation_id: str) -> dict[str, object]:
        assert observed_forensics == forensics
        assert operation_id == marker["operation_id"]
        return {
            "intent_state_sequence": 6,
            "marker_sha256": marker_sha256,
            "recovery_acknowledgement_verification_sha256": None,
            "release_receipt_record_sha256": "8" * 64,
            "root_unsealed_release_receipt_verification_sha256": None,
        }

    monkeypatch.setattr(
        hotswap, "_assert_current_history_consistent_for_recovery", assert_current_history
    )
    monkeypatch.setattr(hotswap, "pin_database_url", lambda value: f"pinned:{value}")

    def read_receipt(
        observed_marker: dict[str, object], *, marker_sha256: str, fence_database_url: str
    ) -> dict[str, object]:
        receipt_calls.append((observed_marker, marker_sha256, fence_database_url))
        return receipt

    monkeypatch.setattr(hotswap, "_read_release_receipt", read_receipt)
    monkeypatch.setattr(
        hotswap,
        "_safe_recovery_observation",
        lambda observed_marker, database_url, observed_topology, **kwargs: (
            "6" * 64
            if (
                observed_marker is marker
                and database_url == "pinned:postgresql://owner@target/pinvi"
                and observed_topology == topology
                and kwargs
                == {
                    "marker_sha256": marker_sha256,
                    "receipt": receipt,
                    "fence_database_url": "pinned:postgresql://fence@target/pinvi",
                }
            )
            else (_ for _ in ()).throw(AssertionError("unexpected recovery proof inputs"))
        ),
    )
    monkeypatch.setattr(
        hotswap,
        "_acknowledge_after_verified_recovery",
        lambda observed_forensics, *, operation_id, verification_sha256, expected_marker_sha256, expected_release_receipt_record_sha256: (
            acknowledgement.append(
                (
                    observed_forensics,
                    operation_id,
                    verification_sha256,
                    expected_marker_sha256,
                    expected_release_receipt_record_sha256,
                )
            )
        ),
    )

    assert (
        hotswap._recover(
            Namespace(confirm=True, operation_id="123e4567-e89b-42d3-a456-426614174000"),
            _lease_held=True,
        )
        == 0
    )
    assert receipt_calls == [(marker, marker_sha256, "pinned:postgresql://fence@target/pinvi")]
    assert acknowledgement == [
        (
            forensics,
            "123e4567-e89b-42d3-a456-426614174000",
            "6" * 64,
            marker_sha256,
            "8" * 64,
        )
    ]


def test_root_recovery_unsealed_receipt_requires_explicit_cas_escalation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DB commit 뒤 seal 전 SIGKILL은 default recover가 아닌 root escalation만 닫는다."""

    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    marker = _recovery_marker(state="fence_release_intent")
    marker_sha256 = hotswap.hashlib.sha256(hotswap._canonical_json(marker)).hexdigest()
    forensics = Path("/trusted/forensics")
    topology = Path("/trusted/m05_hotswap_topology.sql")
    receipt = {"record_sha256": "8" * 64}
    acknowledgement: list[tuple[Path, str, str, str, str]] = []

    monkeypatch.setattr(hotswap, "_strict_environment", lambda: None)
    monkeypatch.setattr(
        hotswap, "_load_trusted_configuration", lambda: _trusted_configuration(hotswap)
    )
    monkeypatch.setattr(
        hotswap,
        "_canonical_runner_paths",
        lambda: (Path("/trusted/restore-hotswap.sh"), forensics, topology),
    )
    monkeypatch.setattr(hotswap, "_read_marker", lambda _forensics: marker)
    monkeypatch.setattr(
        hotswap,
        "_assert_current_history_consistent_for_recovery",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("normal recovery must not accept an unsealed receipt")
        ),
    )
    monkeypatch.setattr(
        hotswap,
        "_assert_unsealed_release_receipt_escalation_history",
        lambda observed_forensics, *, operation_id: (
            {
                "intent_state_sequence": 6,
                "marker_sha256": marker_sha256,
                "recovery_acknowledgement_verification_sha256": None,
                "release_receipt_record_sha256": None,
                "root_unsealed_release_receipt_verification_sha256": None,
            }
            if observed_forensics == forensics and operation_id == marker["operation_id"]
            else (_ for _ in ()).throw(AssertionError("unexpected escalation history"))
        ),
    )
    monkeypatch.setattr(hotswap, "pin_database_url", lambda value: f"pinned:{value}")

    def read_receipt(
        observed_marker: dict[str, object],
        *,
        marker_sha256: str,
        fence_database_url: str,
    ) -> dict[str, object]:
        assert observed_marker is marker
        assert marker_sha256 == marker_sha256_value
        assert fence_database_url == "pinned:postgresql://fence@target/pinvi"
        return receipt

    marker_sha256_value = marker_sha256
    monkeypatch.setattr(hotswap, "_read_release_receipt", read_receipt)
    monkeypatch.setattr(
        hotswap,
        "_safe_recovery_observation",
        lambda observed_marker, database_url, observed_topology, **kwargs: (
            "6" * 64
            if (
                observed_marker is marker
                and database_url == "pinned:postgresql://owner@target/pinvi"
                and observed_topology == topology
                and kwargs
                == {
                    "marker_sha256": marker_sha256,
                    "receipt": receipt,
                    "fence_database_url": "pinned:postgresql://fence@target/pinvi",
                }
            )
            else (_ for _ in ()).throw(AssertionError("unexpected escalation proof"))
        ),
    )
    monkeypatch.setattr(
        hotswap,
        "_acknowledge_unsealed_release_receipt_after_verified_recovery",
        lambda observed_forensics, *, operation_id, verification_sha256, expected_marker_sha256, expected_release_receipt_record_sha256: (
            acknowledgement.append(
                (
                    observed_forensics,
                    operation_id,
                    verification_sha256,
                    expected_marker_sha256,
                    expected_release_receipt_record_sha256,
                )
            )
        ),
    )

    assert (
        hotswap._recover(
            Namespace(
                confirm=True,
                operation_id="123e4567-e89b-42d3-a456-426614174000",
                escalate_unsealed_release_receipt=True,
                expected_marker_sha256=marker_sha256,
            ),
            _lease_held=True,
        )
        == 0
    )
    assert acknowledgement == [
        (
            forensics,
            "123e4567-e89b-42d3-a456-426614174000",
            "6" * 64,
            marker_sha256,
            "8" * 64,
        )
    ]


def test_root_recovery_unsealed_escalation_requires_an_explicit_marker_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    monkeypatch.setattr(hotswap, "_strict_environment", lambda: None)

    with pytest.raises(hotswap.TrustedHotswapError, match="expected-marker-sha256"):
        hotswap._recover(
            Namespace(
                confirm=True,
                operation_id="123e4567-e89b-42d3-a456-426614174000",
                escalate_unsealed_release_receipt=True,
                expected_marker_sha256=None,
            )
        )


def test_recovery_psql_sets_server_side_read_only_before_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """trusted recovery query는 SQL 모양과 무관하게 server-side read-only여야 한다."""

    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    monkeypatch.setattr(hotswap, "_trusted_psql_path", lambda: Path("/trusted/psql"))
    captured: dict[str, object] = {}

    def run(arguments, **kwargs):  # type: ignore[no-untyped-def]
        captured["arguments"] = arguments
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="1\n")

    monkeypatch.setattr(hotswap.subprocess, "run", run)
    assert (
        hotswap._run_psql(
            "postgresql://fence@target/pinvi",
            command="SELECT 1",
            failure="read-only test query failed",
        )
        == "1\n"
    )
    assert captured["env"] == {
        **hotswap._SAFE_ENVIRONMENT,
        "PGOPTIONS": "-c default_transaction_read_only=on",
    }


def test_root_run_execve_receives_only_the_explicit_trusted_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    _sanitize_root_wrapper_environment(monkeypatch, hotswap)
    monkeypatch.setattr(hotswap.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        hotswap, "_load_trusted_configuration", lambda: _trusted_configuration(hotswap)
    )
    monkeypatch.setattr(
        hotswap,
        "_canonical_runner_paths",
        lambda: (
            Path("/trusted/restore-hotswap.sh"),
            Path("/trusted/m05_hotswap_forensics.py"),
            Path("/trusted/m05_hotswap_topology.sql"),
        ),
    )
    monkeypatch.setattr(hotswap, "_assert_no_active_marker", lambda _: None)
    monkeypatch.setattr(hotswap, "pin_database_url", lambda value: f"pinned:{value}")
    lease_closed = False

    class Lease:
        token = "m05-v1-" + "e" * 64

        def fileno(self) -> int:
            return 73

        def close(self) -> None:
            nonlocal lease_closed
            lease_closed = True

    monkeypatch.setattr(
        hotswap,
        "_canonical_operation_lease_path",
        lambda _forensics: Path("/trusted/m05_operation_lease.py"),
    )
    monkeypatch.setattr(hotswap, "_acquire_operation_lease", lambda *_: Lease())
    monkeypatch.setattr(hotswap.os, "set_inheritable", lambda *_: None)
    monkeypatch.setattr(
        hotswap,
        "_safe_root_only_directory",
        lambda path, *, mode: Path("/srv/pinvi/restore-trust"),
    )
    monkeypatch.setattr(
        hotswap,
        "_prepare_trusted_drain_receipt",
        lambda **_: ({"target_identity_sha256": "a" * 64}, "d" * 64),
    )
    monkeypatch.setattr(hotswap, "_consume_trusted_drain_receipt", lambda *_: None)
    monkeypatch.setattr(
        hotswap,
        "_identity_sha256_from_psql",
        lambda _: (
            "a" * 64,
            {
                "database": "pinvi",
                "database_oid": "101",
                "hostaddr": "192.0.2.20",
                "port": "5432",
                "system_identifier": "201",
            },
        ),
    )
    monkeypatch.setattr(hotswap, "_trusted_bash_path", lambda: Path("/trusted/bash"))
    monkeypatch.setattr(hotswap, "_trusted_pg_restore_path", lambda: Path("/trusted/pg_restore"))
    monkeypatch.setattr(hotswap, "_trusted_psql_path", lambda: Path("/trusted/psql"))
    monkeypatch.setattr(hotswap, "_trusted_file_sha256", lambda path: f"{path.name:0<64}"[:64])
    captured: dict[str, object] = {}

    class ExecveCalled(RuntimeError):
        pass

    def execve(path: str, arguments: list[str], environment: dict[str, str]) -> None:
        captured.update({"arguments": arguments, "environment": environment, "path": path})
        raise ExecveCalled

    monkeypatch.setattr(hotswap.os, "execve", execve)
    with pytest.raises(ExecveCalled):
        hotswap._run(
            Namespace(
                snapshot="/srv/pinvi/restore-trust/pinvi.dump",
                restore_schema="app_restore_1",
                previous_schema="app_previous_1",
                operation_id="123e4567-e89b-42d3-a456-426614174000",
            )
        )

    assert captured["path"] == "/trusted/bash"
    assert captured["arguments"] == [
        "/trusted/bash",
        "/trusted/restore-hotswap.sh",
        "run",
        "/srv/pinvi/restore-trust/pinvi.dump",
        "app_restore_1",
        "app_previous_1",
    ]
    environment = captured["environment"]
    assert isinstance(environment, dict)
    assert environment == {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "PINVI_BACKUP_SCHEMA": "app",
        "PINVI_ENVIRONMENT": "staging",
        "PINVI_M05_FORENSICS_DRAIN_RECEIPT_SHA256": "d" * 64,
        "PINVI_M05_FORENSICS_OPERATION_ID": "123e4567-e89b-42d3-a456-426614174000",
        "PINVI_M05_FORENSICS_STATE_DIR": "/var/lib/pinvi/restore-forensics",
        "PINVI_M05_OPERATION_LEASE_FD": "73",
        "PINVI_M05_OPERATION_LEASE_TOKEN": "m05-v1-" + "e" * 64,
        "PINVI_RESTORE_ALLOW_NO_DRAIN": "1",
        "PINVI_RESTORE_API_TRIGGER": "1",
        "PINVI_RESTORE_APP_ROLE": "pinvi_app",
        "PINVI_RESTORE_BASH_BIN": "/trusted/bash",
        "PINVI_RESTORE_BASH_SHA256": f"bash{'0' * 60}",
        "PINVI_RESTORE_DATABASE_URL": "pinned:postgresql://owner@target/pinvi",
        "PINVI_RESTORE_DRAIN_VERIFIED": "1",
        "PINVI_RESTORE_EXPECTED_DATABASE_NAME": "pinvi",
        "PINVI_RESTORE_EXPECTED_DATABASE_OID": "101",
        "PINVI_RESTORE_EXPECTED_HOSTADDR": "192.0.2.20",
        "PINVI_RESTORE_EXPECTED_PORT": "5432",
        "PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_NAME": "pinvi_source",
        "PINVI_RESTORE_EXPECTED_SOURCE_DATABASE_OID": "100",
        "PINVI_RESTORE_EXPECTED_SOURCE_HOSTADDR": "192.0.2.10",
        "PINVI_RESTORE_EXPECTED_SOURCE_PORT": "5432",
        "PINVI_RESTORE_EXPECTED_SOURCE_SYSTEM_IDENTIFIER": "200",
        "PINVI_RESTORE_EXPECTED_SYSTEM_IDENTIFIER": "201",
        "PINVI_RESTORE_FENCE_DATABASE_URL": "pinned:postgresql://fence@target/pinvi",
        "PINVI_RESTORE_HOTSWAP_EXECUTE": "1",
        "PINVI_RESTORE_PG_RESTORE_BIN": "/trusted/pg_restore",
        "PINVI_RESTORE_PG_RESTORE_SHA256": f"pg_restore{'0' * 54}",
        "PINVI_RESTORE_PSQL_BIN": "/trusted/psql",
        "PINVI_RESTORE_PSQL_SHA256": f"psql{'0' * 60}",
        "PINVI_RESTORE_TRUSTED_BACKUP_DIR": "/srv/pinvi/restore-trust",
    }
    assert lease_closed is True


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PATH", "/caller-controlled/bin"),
        ("PYTHONPATH", "/caller-controlled/python"),
        ("PGOPTIONS", "-c role=pinvi_owner"),
        ("PINVI_RESTORE_DATABASE_URL", "postgresql://caller@target/pinvi"),
        ("PINVI_RESTORE_FENCE_DATABASE_URL", "postgresql://caller@target/pinvi"),
        ("PINVI_RESTORE_APP_ROLE", "caller_role"),
        ("PINVI_BACKUP_SCHEMA", "caller_schema"),
        ("PINVI_RESTORE_TRUSTED_BACKUP_DIR", "/caller-controlled/backups"),
        ("PINVI_M05_OPERATION_LEASE_FD", "3"),
        ("PINVI_M05_OPERATION_LEASE_TOKEN", "m05-v1-" + "a" * 64),
    ],
)
def test_root_run_rejects_every_caller_override_before_config_or_runner(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    _sanitize_root_wrapper_environment(monkeypatch, hotswap)
    monkeypatch.setattr(hotswap.os, "geteuid", lambda: 0)
    monkeypatch.setenv(name, value)

    def must_not_run(*_args, **_kwargs):
        raise AssertionError("caller override reached a trusted operation")

    monkeypatch.setattr(hotswap, "_load_trusted_configuration", must_not_run)
    monkeypatch.setattr(hotswap, "_canonical_runner_paths", must_not_run)

    with pytest.raises(hotswap.TrustedHotswapError, match="sanitized root wrapper"):
        hotswap._run(
            Namespace(
                snapshot="/srv/pinvi/restore-trust/pinvi.dump",
                restore_schema="app_restore_1",
                previous_schema="app_previous_1",
                operation_id="123e4567-e89b-42d3-a456-426614174000",
            )
        )


def test_root_wrapper_uses_only_the_fixed_isolated_launcher() -> None:
    wrapper = (
        Path(__file__).resolve().parents[4] / "scripts" / "trusted-hotswap-root.sh"
    ).read_text(encoding="utf-8")

    assert wrapper.startswith("#!/bin/sh\n")
    assert "PATH=/usr/bin:/bin" in wrapper
    assert "$(/usr/bin/id -u)" in wrapper
    assert "$(id -u)" not in wrapper
    assert "exec /usr/bin/env -i" in wrapper
    assert "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" in wrapper
    assert "/usr/bin/python3 -I" in wrapper
    assert "/usr/local/libexec/pinvi/trusted-hotswap-entrypoint.py" in wrapper
    assert "sudo -E" not in wrapper
    assert "source " not in wrapper
    assert "eval " not in wrapper
    assert "unset BASH_ENV CDPATH ENV IFS" in wrapper


def test_root_wrapper_does_not_resolve_id_from_the_caller_path(tmp_path: Path) -> None:
    wrapper = Path(__file__).resolve().parents[4] / "scripts" / "trusted-hotswap-root.sh"
    caller_id = tmp_path / "id"
    invoked = tmp_path / "caller-id-was-invoked"
    caller_id.write_text(
        f"#!/bin/sh\nprintf invoked > {shlex.quote(str(invoked))}\nexit 0\n",
        encoding="utf-8",
    )
    caller_id.chmod(0o755)

    result = subprocess.run(  # noqa: S603
        ["/bin/sh", str(wrapper), "status"],
        check=False,
        capture_output=True,
        env={"PATH": str(tmp_path)},
        text=True,
    )

    assert result.returncode != 0
    assert not invoked.exists()


@pytest.mark.parametrize(
    "name",
    [
        "PINVI_M05_RESTORE_TEST_MODE",
        "PINVI_RESTORE_ALLOW_NO_DRAIN",
        "PINVI_RESTORE_DRAIN_COMMAND",
        "PINVI_RESTORE_DRAIN_VERIFIED",
        "PINVI_RESTORE_EXTERNAL_LOCK_HOLDER_BACKEND_PID",
        "PINVI_RESTORE_EXTERNAL_LOCK_HOLDER_PID",
        "PINVI_RESTORE_PG_RESTORE_BIN",
        "PINVI_RESTORE_PRIVATE_TOOL_COPY",
        "PINVI_RESTORE_PSQL_BIN",
        "PINVI_RESTORE_TEST_FAIL_AFTER_RELEASE_RECEIPT_SEAL_ONCE",
        "PINVI_RESTORE_TEST_FAIL_RELEASE_SQL_ONCE",
        "PINVI_RESTORE_TEST_FAIL_RESTORE_ONCE",
        "PINVI_RESTORE_TEST_REQUIRE_RELEASE_RECEIPT",
        "PINVI_RESTORE_TEST_SIGKILL_AFTER_RELEASE_RECEIPT_COMMIT_ONCE",
        "PINVI_RESTORE_TEST_SIGKILL_AFTER_RELEASE_RECEIPT_SEAL_ONCE",
        "PINVI_M05_RESTORE_DRILL",
    ],
)
def test_root_runner_rejects_inherited_tool_test_and_command_overrides(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    hotswap = _script_module("trusted-hotswap-entrypoint.py", "trusted_hotswap_entrypoint")
    _sanitize_root_wrapper_environment(monkeypatch, hotswap)
    monkeypatch.setenv(name, "unsafe")

    with pytest.raises(hotswap.TrustedHotswapError, match="inherited runner overrides"):
        hotswap._runner_environment(
            _trusted_configuration(hotswap),
            "postgresql://target",
            "postgresql://fence",
            snapshot="/srv/pinvi/restore-trust/pinvi.dump",
            operation_id="123e4567-e89b-42d3-a456-426614174000",
        )
