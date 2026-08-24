"""0101 legacy profile이 root-only rebaseline 인수증을 정확히 결박한다."""

from __future__ import annotations

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
            "catalog_sha256": "d" * 64,
            "current_user": "legacy_owner",
            "database_name": identity["database_name"],
            "database_oid": identity["database_oid"],
            "expected_catalog_lines": 1590,
            "expected_catalog_sha256": "d" * 64,
            "server_addr": identity["server_addr"],
            "server_port": identity["server_port"],
            "server_version_num": 160000,
            "session_user": "legacy_owner",
            "system_identifier": identity["system_identifier"],
            "version_rows": ["20260821_0061"],
        },
        "state": "applied",
        "target_manifest_sha256": "e" * 64,
        "version": 1,
    }


class _BoundIdentity:
    def __init__(self, identity: dict[str, object], version_rows: list[str]) -> None:
        self.identity = identity
        self.version_rows = version_rows

    def scalar(self, statement: object) -> str:
        sql = str(statement)
        if "json_build_object" in sql:
            return json.dumps(self.identity)
        if "json_agg(version_num" in sql:
            return json.dumps(self.version_rows)
        raise AssertionError(f"unexpected legacy handoff statement: {sql}")


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
    monkeypatch.setenv("PINVI_M05_LEGACY_REBASELINE_RECEIPT_PATH", str(receipt_path))
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.os, "fstat", _root_owned_fstat(module))
    monkeypatch.setattr(module, "_assert_legacy_rebaseline_fingerprint", lambda *_args: None)

    other_identity = dict(identity)
    other_identity["database_oid"] = 4243
    with pytest.raises(RuntimeError, match="does not match this database"):
        module._assert_legacy_rebaseline_handoff(_BoundIdentity(other_identity, ["20260824_0100"]))
