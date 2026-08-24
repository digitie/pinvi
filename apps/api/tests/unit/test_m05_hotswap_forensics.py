"""M05 hotswap forensic state helper regression tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _module():
    script = Path(__file__).resolve().parents[4] / "scripts/m05_hotswap_forensics.py"
    spec = importlib.util.spec_from_file_location("m05_hotswap_forensics", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _begin_arguments(state_directory: Path) -> list[str]:
    digest = "a" * 64
    return [
        "begin",
        "--state-dir",
        str(state_directory),
        "--test-mode",
        "--script-sha256",
        digest,
        "--snapshot-sha256",
        "b" * 64,
        "--pg-restore-list-sha256",
        "c" * 64,
        "--source-identity-sha256",
        "d" * 64,
        "--target-identity-sha256",
        "e" * 64,
        "--acl-topology-sha256",
        "f" * 64,
        "--holder-backend-pid",
        "1234",
        "--source-schema",
        "app",
        "--restore-schema",
        "app_restore_1",
        "--previous-schema",
        "app_previous_1",
        "--app-role",
        "pinvi_app",
        "--fence-executor-role",
        "pinvi_fence",
        "--source-schema-oid-before",
        "100",
        "--write-roles",
        "pinvi_app",
    ]


def _transition_arguments(state_directory: Path, operation_id: str, state: str) -> list[str]:
    arguments = [
        "transition",
        "--state-dir",
        str(state_directory),
        "--test-mode",
        "--operation-id",
        operation_id,
        "--state",
        state,
    ]
    if state == "fence_intent":
        arguments.extend(
            [
                "--acl-topology-sha256",
                "f" * 64,
                "--connect-restore-grants",
                "pinvi_app:0",
                "--fenced-connect-roles",
                "pinvi_app",
                "--public-connect-was-granted",
                "1",
                "--source-schema-oid-before",
                "100",
                "--write-roles",
                "pinvi_app",
            ]
        )
    elif state == "restore_ready":
        arguments.extend(["--restore-schema-oid", "200"])
    elif state == "switched":
        arguments.extend(
            [
                "--app-schema-oid-after-switch",
                "200",
                "--previous-schema-oid-after-switch",
                "100",
            ]
        )
    return arguments


def test_forensic_state_is_append_only_and_requires_recovery_ack(tmp_path: Path, capsys) -> None:
    module = _module()
    state_directory = tmp_path / "forensics"
    state_directory.mkdir(mode=0o700)

    assert module.main(_begin_arguments(state_directory)) == 0
    operation_id = capsys.readouterr().out.strip()
    assert module._UUID_RE.fullmatch(operation_id)
    assert module.main(_begin_arguments(state_directory)) == 3
    assert "already exists" in capsys.readouterr().err

    for state in (
        "fence_intent",
        "fence_applied",
        "restore_ready",
        "switched",
        "fence_released",
    ):
        assert module.main(_transition_arguments(state_directory, operation_id, state)) == 0

    current = json.loads((state_directory / "current.json").read_text(encoding="utf-8"))
    assert current["state"] == "fence_released"
    assert current["app_schema_oid_after_switch"] == 200
    assert current["previous_schema_oid_after_switch"] == 100
    assert (
        module.main(
            [
                "acknowledge",
                "--state-dir",
                str(state_directory),
                "--test-mode",
                "--operation-id",
                operation_id,
                "--verification-sha256",
                "9" * 64,
            ]
        )
        == 3
    )
    assert "requires --confirm" in capsys.readouterr().err
    assert (state_directory / "current.json").exists()

    assert (
        module.main(
            [
                "acknowledge",
                "--state-dir",
                str(state_directory),
                "--test-mode",
                "--operation-id",
                operation_id,
                "--verification-sha256",
                "9" * 64,
                "--confirm",
            ]
        )
        == 0
    )
    assert not (state_directory / "current.json").exists()
    recovery = json.loads(
        (state_directory / "recovery" / f"{operation_id}.json").read_text(encoding="utf-8")
    )
    assert recovery["outcome"] == "recovery_acknowledged"
    history = (state_directory / "operations" / f"{operation_id}.jsonl").read_text(encoding="utf-8")
    assert history.count('"type":"state"') == 6
    assert '"type":"recovery_acknowledged"' in history
    assert "postgresql://" not in history
    assert "password" not in history
    assert "token" not in history


def test_forensic_state_rejects_bad_directory_and_invalid_transition(
    tmp_path: Path, capsys
) -> None:
    module = _module()
    state_directory = tmp_path / "forensics"
    state_directory.mkdir(mode=0o700)
    assert module.main(_begin_arguments(state_directory)) == 0
    operation_id = capsys.readouterr().out.strip()
    assert module.main(_transition_arguments(state_directory, operation_id, "switched")) == 3
    assert "transition is invalid" in capsys.readouterr().err

    symlink = tmp_path / "forensics-link"
    symlink.symlink_to(state_directory, target_is_directory=True)
    assert module.main(_begin_arguments(symlink)) == 3
    assert "unavailable" in capsys.readouterr().err
