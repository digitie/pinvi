"""0101 legacy profile이 root-only rebaseline 인수증을 정확히 결박한다."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


def _migration_module():
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260824_0101_m05_activation_contract.py"
    )
    spec = importlib.util.spec_from_file_location("m05_legacy_rebaseline_receipt", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _rebaseline_module():
    path = Path(__file__).resolve().parents[4] / "scripts" / "alembic_rebaseline.py"
    spec = importlib.util.spec_from_file_location("m05_rebaseline_profile", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _receipt(identity: dict[str, object]) -> dict[str, object]:
    return {
        "action": "0061_to_0100_rebaseline",
        "backup_manifest_sha256": "a" * 64,
        "backup_sha256": "b" * 64,
        "completed_at": "2026-08-24T00:00:00Z",
        "preflight": {
            "app_data_content_sha256": "c" * 64,
            "app_data_rows": 1,
            "app_data_table_lines": 1,
            "catalog_lines": 1590,
            "catalog_sha256": "4f2d69decc34300c597320e8a0dc78d154bd2eb4b6dbc96f0b51ba5b05c75d94",
            "current_user": "legacy_owner",
            "database_name": identity["database_name"],
            "database_oid": identity["database_oid"],
            "expected_catalog_lines": 1590,
            "expected_catalog_sha256": "4f2d69decc34300c597320e8a0dc78d154bd2eb4b6dbc96f0b51ba5b05c75d94",
            "role_security_sha256": "f" * 64,
            "server_addr": identity["server_addr"],
            "server_port": identity["server_port"],
            "server_version_num": 160000,
            "session_user": "legacy_owner",
            "system_identifier": identity["system_identifier"],
            "version_rows": ["20260821_0061"],
        },
        "state": "applied",
        "target_manifest_sha256": "e" * 64,
        "target_host": "test",
        "target_profile": "fresh-postgresql-16",
        "version": 1,
    }


class _BoundIdentity:
    def __init__(
        self,
        identity: dict[str, object],
        version_rows: list[str],
        marker: str = "pinvi-0100-legacy/v1",
    ) -> None:
        self.identity = identity
        self.version_rows = version_rows
        self.marker = marker

    def scalar(self, statement: object) -> str:
        sql = str(statement)
        if "json_build_object" in sql:
            return json.dumps(self.identity)
        if "json_agg(version_num" in sql:
            return json.dumps(self.version_rows)
        if "obj_description('app'::regnamespace" in sql:
            return self.marker
        raise AssertionError(f"unexpected legacy handoff statement: {sql}")

    def execute(self, statement: object) -> None:
        assert "pg_advisory_xact_lock" in str(statement) or "SET LOCAL lock_timeout = '5s'" in str(
            statement
        )


def _root_owned_fstat(module):  # type: ignore[no-untyped-def]
    actual_fstat = module.os.fstat

    def root_owned(descriptor: int) -> os.stat_result:
        metadata = actual_fstat(descriptor)
        values = list(metadata)
        values[0] = (metadata.st_mode & ~0o777) | 0o600
        values[4] = 0
        return os.stat_result(values)

    return root_owned


def test_0101_legacy_handoff_requires_root_owned_applied_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _migration_module()
    identity = {
        "database_name": "pinvi_legacy",
        "database_oid": 4242,
        "system_identifier": "987654321",
        "server_addr": "127.0.0.1",
        "server_port": 5432,
    }
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(_receipt(identity)), encoding="utf-8")
    receipt_path.chmod(0o600)
    monkeypatch.setenv("PINVI_M05_LEGACY_REBASELINE", "1")
    monkeypatch.setenv("PINVI_M05_LEGACY_REBASELINE_TARGET_PROFILE", "fresh-postgresql-16")
    monkeypatch.setenv("PINVI_M05_LEGACY_REBASELINE_RECEIPT_PATH", str(receipt_path))
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module, "_assert_legacy_rebaseline_fingerprint", lambda *_args: None)
    monkeypatch.setattr(
        module, "_acquire_legacy_rebaseline_database_connection_fence", lambda *_args: None
    )

    with pytest.raises(RuntimeError, match="root-owned mode 0600"):
        module._assert_legacy_rebaseline_handoff(_BoundIdentity(identity, ["20260824_0100"]))

    monkeypatch.setattr(module.os, "fstat", _root_owned_fstat(module))
    module._assert_legacy_rebaseline_handoff(_BoundIdentity(identity, ["20260824_0100"]))


def test_0101_legacy_handoff_rejects_receipt_for_another_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _migration_module()
    identity = {
        "database_name": "pinvi_legacy",
        "database_oid": 4242,
        "system_identifier": "987654321",
        "server_addr": "127.0.0.1",
        "server_port": 5432,
    }
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(_receipt(identity)), encoding="utf-8")
    receipt_path.chmod(0o600)
    monkeypatch.setenv("PINVI_M05_LEGACY_REBASELINE", "1")
    monkeypatch.setenv("PINVI_M05_LEGACY_REBASELINE_TARGET_PROFILE", "fresh-postgresql-16")
    monkeypatch.setenv("PINVI_M05_LEGACY_REBASELINE_RECEIPT_PATH", str(receipt_path))
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.os, "fstat", _root_owned_fstat(module))
    monkeypatch.setattr(module, "_assert_legacy_rebaseline_fingerprint", lambda *_args: None)

    other_identity = dict(identity)
    other_identity["database_oid"] = 4243
    with pytest.raises(RuntimeError, match="does not match this database"):
        module._assert_legacy_rebaseline_handoff(_BoundIdentity(other_identity, ["20260824_0100"]))


def test_rebaseline_target_profiles_bind_catalog_and_target_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """N150 profile은 canonical catalog와 재생성되지 않는 DB identity를 함께 요구한다."""

    module = _rebaseline_module()
    identity = {
        "database_name": "pinvi",
        "system_identifier": "987654321",
        "server_addr": "127.0.0.1",
        "server_port": 12800,
    }
    identity_sha256 = hashlib.sha256(
        "|".join(str(identity[field]) for field in identity).encode("utf-8")
    ).hexdigest()
    monkeypatch.setitem(
        module._TARGET_PROFILE_SPECS[module._TARGET_PROFILE_N150],
        "target_identity_sha256",
        identity_sha256,
    )
    n150_preflight = {
        **identity,
        "catalog_lines": module._EXPECTED_CATALOG_LINES,
        "expected_catalog_lines": module._EXPECTED_CATALOG_LINES,
        "catalog_sha256": module._N150_LEGACY_CATALOG_SHA256,
        "expected_catalog_sha256": module._N150_LEGACY_CATALOG_SHA256,
    }
    module._assert_target_profile_preflight(module._TARGET_PROFILE_N150, n150_preflight)

    forged_identity = dict(n150_preflight)
    forged_identity["database_name"] = "pinvi_m05_probe"
    with pytest.raises(module.RebaselineError, match="canonical"):
        module._assert_target_profile_preflight(module._TARGET_PROFILE_N150, forged_identity)


def test_0101_legacy_handoff_rejects_receipt_profile_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _migration_module()
    identity = {
        "database_name": "pinvi_legacy",
        "database_oid": 4242,
        "system_identifier": "987654321",
        "server_addr": "127.0.0.1",
        "server_port": 5432,
    }
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(_receipt(identity)), encoding="utf-8")
    receipt_path.chmod(0o600)
    monkeypatch.setenv("PINVI_M05_LEGACY_REBASELINE", "1")
    monkeypatch.setenv("PINVI_M05_LEGACY_REBASELINE_TARGET_PROFILE", "n150-production")
    monkeypatch.setenv("PINVI_M05_LEGACY_REBASELINE_RECEIPT_PATH", str(receipt_path))
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.os, "fstat", _root_owned_fstat(module))

    with pytest.raises(RuntimeError, match="profile does not match configuration"):
        module._assert_legacy_rebaseline_handoff(_BoundIdentity(identity, ["20260824_0100"]))


def test_0101_legacy_handoff_rejects_fresh_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _migration_module()
    identity = {
        "database_name": "pinvi_legacy",
        "database_oid": 4242,
        "system_identifier": "987654321",
        "server_addr": "127.0.0.1",
        "server_port": 5432,
    }
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(_receipt(identity)), encoding="utf-8")
    receipt_path.chmod(0o600)
    monkeypatch.setenv("PINVI_M05_LEGACY_REBASELINE", "1")
    monkeypatch.setenv("PINVI_M05_LEGACY_REBASELINE_TARGET_PROFILE", "fresh-postgresql-16")
    monkeypatch.setenv("PINVI_M05_LEGACY_REBASELINE_RECEIPT_PATH", str(receipt_path))
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.os, "fstat", _root_owned_fstat(module))

    with pytest.raises(RuntimeError, match="canonical legacy 0100 marker"):
        module._assert_legacy_rebaseline_handoff(
            _BoundIdentity(identity, ["20260824_0100"], marker="pinvi-0100-fresh/v1")
        )
