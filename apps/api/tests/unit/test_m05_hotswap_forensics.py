"""M05 hotswap forensic state helper regression tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


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
        "--drain-receipt-sha256",
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
        "--restore-executor-role",
        "pinvi_restore",
        "--source-schema-oid-before",
        "100",
        "--write-roles",
        "pinvi_app",
    ]


def _transition_arguments(
    state_directory: Path,
    operation_id: str,
    state: str,
) -> list[str]:
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
                "--restore-executor-connect-restore-grants",
                "pinvi_restore:0",
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
    elif state == "fence_release_intent":
        arguments.extend(["--terminal-schema-mode", "switched"])
    return arguments


def _seal_arguments(
    state_directory: Path,
    operation_id: str,
    *,
    intent_marker_sha256: str,
    receipt_record_sha256: str = "1" * 64,
    test_fail_history_append_once: bool = False,
) -> list[str]:
    arguments = [
        "seal-release-receipt",
        "--state-dir",
        str(state_directory),
        "--test-mode",
        "--operation-id",
        operation_id,
        "--intent-marker-sha256",
        intent_marker_sha256,
        "--receipt-record-sha256",
        receipt_record_sha256,
    ]
    if test_fail_history_append_once:
        arguments.append("--test-fail-history-append-once")
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
        "fence_release_intent",
    ):
        assert module.main(_transition_arguments(state_directory, operation_id, state)) == 0

    intent_marker_sha256 = hashlib.sha256(
        (state_directory / "current.json").read_bytes()
    ).hexdigest()
    assert (
        module.main(
            _seal_arguments(
                state_directory,
                operation_id,
                intent_marker_sha256=intent_marker_sha256,
            )
        )
        == 0
    )

    current = json.loads((state_directory / "current.json").read_text(encoding="utf-8"))
    assert current["state"] == "fence_release_intent"
    assert current["app_schema_oid_after_switch"] == 200
    assert current["previous_schema_oid_after_switch"] == 100
    assert (state_directory / ".state.lock").stat().st_mode & 0o777 == 0o600
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

    store = module._StateDirectory.open(state_directory, strict=False, test_mode=True)
    store.acknowledge_and_archive(
        operation_id,
        verification_sha256="9" * 64,
        expected_marker_sha256=intent_marker_sha256,
        expected_release_receipt_record_sha256="1" * 64,
        trusted_release_intent=True,
    )
    assert not (state_directory / "current.json").exists()
    final_marker = json.loads(
        (state_directory / "operations" / f"{operation_id}.final.json").read_text(encoding="utf-8")
    )
    assert final_marker == current
    recovery = json.loads(
        (state_directory / "recovery" / f"{operation_id}.json").read_text(encoding="utf-8")
    )
    assert recovery["outcome"] == "recovery_acknowledged"
    history = (state_directory / "operations" / f"{operation_id}.jsonl").read_text(encoding="utf-8")
    assert history.count('"type":"state"') == 6
    assert '"type":"release_receipt_committed"' in history
    assert '"type":"recovery_acknowledged"' in history
    assert "postgresql://" not in history
    assert "password" not in history
    assert "token" not in history


def _advance_to_release_intent(module, state_directory: Path, operation_id: str) -> str:
    for state in (
        "fence_intent",
        "fence_applied",
        "restore_ready",
        "switched",
        "fence_release_intent",
    ):
        assert module.main(_transition_arguments(state_directory, operation_id, state)) == 0
    return hashlib.sha256((state_directory / "current.json").read_bytes()).hexdigest()


def test_verified_recovery_ledger_rejects_unsealed_or_ambiguous_release_receipts(
    tmp_path: Path, capsys
) -> None:
    """root recovery는 seal 없는/중복/다른 receipt binding 원장을 archive하지 않는다."""

    module = _module()

    partial_directory = tmp_path / "partial"
    partial_directory.mkdir(mode=0o700)
    assert module.main(_begin_arguments(partial_directory)) == 0
    partial_operation = capsys.readouterr().out.strip()
    intent_sha256 = _advance_to_release_intent(module, partial_directory, partial_operation)
    partial_store = module._StateDirectory.open(partial_directory, strict=False, test_mode=True)
    with pytest.raises(module.ForensicsError, match="history append failure"):
        partial_store.seal_release_receipt(
            partial_operation,
            intent_marker_sha256=intent_sha256,
            receipt_record_sha256="1" * 64,
            test_fail_history_append=True,
        )
    with pytest.raises(module.ForensicsError, match="seal is missing"):
        partial_store.assert_current_history_consistent_for_recovery(partial_operation)

    completed_directory = tmp_path / "completed"
    completed_directory.mkdir(mode=0o700)
    assert module.main(_begin_arguments(completed_directory)) == 0
    completed_operation = capsys.readouterr().out.strip()
    intent_sha256 = _advance_to_release_intent(module, completed_directory, completed_operation)
    assert (
        module.main(
            _seal_arguments(
                completed_directory,
                completed_operation,
                intent_marker_sha256=intent_sha256,
            )
        )
        == 0
    )
    completed_store = module._StateDirectory.open(completed_directory, strict=False, test_mode=True)
    proof = completed_store.assert_current_history_consistent_for_recovery(completed_operation)
    assert proof["marker_sha256"] == intent_sha256
    assert proof["release_receipt_record_sha256"] == "1" * 64
    completed_store.assert_exact_release_receipt_seal(
        completed_operation,
        intent_marker_sha256=intent_sha256,
        receipt_record_sha256="1" * 64,
    )

    history_path = completed_directory / "operations" / f"{completed_operation}.jsonl"
    history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
    history.append(history[-1])
    history_path.write_bytes(b"\n".join(module._canonical_json(event) for event in history) + b"\n")
    history_path.chmod(0o600)
    with pytest.raises(module.ForensicsError, match="seal is invalid"):
        completed_store.assert_current_history_consistent_for_recovery(completed_operation)


def test_release_receipt_seal_converges_after_durable_append_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """append/fsync error 뒤 exact seal이 이미 durable하면 release를 refence하지 않는다."""

    module = _module()
    state_directory = tmp_path / "forensics"
    state_directory.mkdir(mode=0o700)
    assert module.main(_begin_arguments(state_directory)) == 0
    operation_id = capsys.readouterr().out.strip()
    intent_marker_sha256 = _advance_to_release_intent(module, state_directory, operation_id)
    store = module._StateDirectory.open(state_directory, strict=False, test_mode=True)
    original_append = module._StateDirectory._append_history

    def append_then_report_error(
        observed_store, observed_operation: str, event: dict[str, object]
    ) -> None:
        original_append(observed_store, observed_operation, event)
        raise module.ForensicsError("test-only post-fsync append error")

    monkeypatch.setattr(module._StateDirectory, "_append_history", append_then_report_error)
    store.seal_release_receipt(
        operation_id,
        intent_marker_sha256=intent_marker_sha256,
        receipt_record_sha256="1" * 64,
    )

    proof = store.assert_current_history_consistent_for_recovery(operation_id)
    assert proof["marker_sha256"] == intent_marker_sha256
    assert proof["release_receipt_record_sha256"] == "1" * 64
    history = (state_directory / "operations" / f"{operation_id}.jsonl").read_text(encoding="utf-8")
    assert history.count('"type":"release_receipt_committed"') == 1


def test_unsealed_release_receipt_requires_explicit_root_escalation_and_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """DB commit 뒤 seal 전 crash는 normal archive가 아닌 root event로만 끝난다."""

    module = _module()
    state_directory = tmp_path / "forensics"
    state_directory.mkdir(mode=0o700)
    assert module.main(_begin_arguments(state_directory)) == 0
    operation_id = capsys.readouterr().out.strip()
    intent_marker_sha256 = _advance_to_release_intent(module, state_directory, operation_id)
    store = module._StateDirectory.open(state_directory, strict=False, test_mode=True)

    with pytest.raises(module.ForensicsError, match="seal is missing"):
        store.acknowledge_and_archive(
            operation_id,
            verification_sha256="9" * 64,
            expected_marker_sha256=intent_marker_sha256,
            expected_release_receipt_record_sha256="1" * 64,
            trusted_release_intent=True,
        )

    original_append = module._StateDirectory._append_history
    original_final_write = module._StateDirectory._write_new_or_match

    def append_root_event_then_report_error(
        observed_store, observed_operation: str, event: dict[str, object]
    ) -> None:
        original_append(observed_store, observed_operation, event)
        if event["type"] == module._ROOT_UNSEALED_RELEASE_RECEIPT_VERIFICATION_TYPE:
            raise module.ForensicsError("test-only root certification post-fsync error")

    monkeypatch.setattr(
        module._StateDirectory,
        "_append_history",
        append_root_event_then_report_error,
    )
    monkeypatch.setattr(
        module._StateDirectory,
        "_write_new_or_match",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            module.ForensicsError("test-only final artifact interruption")
        ),
    )
    with pytest.raises(module.ForensicsError, match="final artifact interruption"):
        store.acknowledge_unsealed_release_receipt_and_archive(
            operation_id,
            verification_sha256="9" * 64,
            expected_marker_sha256=intent_marker_sha256,
            expected_release_receipt_record_sha256="1" * 64,
        )

    assert (state_directory / "current.json").exists()
    with pytest.raises(module.ForensicsError, match="explicit root escalation"):
        store.assert_current_history_consistent_for_recovery(operation_id)
    root_proof = store._recovery_ledger_proof_unlocked(
        operation_id,
        require_release_receipt_seal=False,
        allow_root_unsealed_release_receipt_verification=True,
    )
    assert root_proof["release_receipt_record_sha256"] == "1" * 64
    assert root_proof["root_unsealed_release_receipt_verification_sha256"] == "9" * 64

    with pytest.raises(module.ForensicsError, match="verification changed after recovery proof"):
        store.acknowledge_unsealed_release_receipt_and_archive(
            operation_id,
            verification_sha256="9" * 64,
            expected_marker_sha256=intent_marker_sha256,
            expected_release_receipt_record_sha256="2" * 64,
        )

    monkeypatch.setattr(module._StateDirectory, "_append_history", original_append)
    monkeypatch.setattr(module._StateDirectory, "_write_new_or_match", original_final_write)
    store.acknowledge_unsealed_release_receipt_and_archive(
        operation_id,
        verification_sha256="9" * 64,
        expected_marker_sha256=intent_marker_sha256,
        expected_release_receipt_record_sha256="1" * 64,
    )
    assert not (state_directory / "current.json").exists()
    history = (state_directory / "operations" / f"{operation_id}.jsonl").read_text(encoding="utf-8")
    assert history.count('"type":"root_unsealed_release_receipt_verified"') == 1
    assert history.count('"type":"recovery_acknowledged"') == 1


def test_unsealed_root_escalation_retries_after_acknowledgement_before_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """ack history가 durable한 뒤 unlink가 실패해도 새 full proof retry만 archive한다."""

    module = _module()
    state_directory = tmp_path / "forensics"
    state_directory.mkdir(mode=0o700)
    assert module.main(_begin_arguments(state_directory)) == 0
    operation_id = capsys.readouterr().out.strip()
    intent_marker_sha256 = _advance_to_release_intent(module, state_directory, operation_id)
    store = module._StateDirectory.open(state_directory, strict=False, test_mode=True)
    original_unlink = module._StateDirectory._unlink_current
    monkeypatch.setattr(
        module._StateDirectory,
        "_unlink_current",
        lambda _store: (_ for _ in ()).throw(module.ForensicsError("test-only unlink failure")),
    )

    with pytest.raises(module.ForensicsError, match="unlink failure"):
        store.acknowledge_unsealed_release_receipt_and_archive(
            operation_id,
            verification_sha256="9" * 64,
            expected_marker_sha256=intent_marker_sha256,
            expected_release_receipt_record_sha256="1" * 64,
        )
    pending = store._recovery_ledger_proof_unlocked(
        operation_id,
        require_release_receipt_seal=False,
        allow_root_unsealed_release_receipt_verification=True,
    )
    assert pending["recovery_acknowledgement_verification_sha256"] == "9" * 64
    assert (state_directory / "operations" / f"{operation_id}.final.json").exists()
    assert (state_directory / "recovery" / f"{operation_id}.json").exists()

    monkeypatch.setattr(module._StateDirectory, "_unlink_current", original_unlink)
    store.acknowledge_unsealed_release_receipt_and_archive(
        operation_id,
        verification_sha256="9" * 64,
        expected_marker_sha256=intent_marker_sha256,
        expected_release_receipt_record_sha256="1" * 64,
    )
    assert not (state_directory / "current.json").exists()


def test_public_helper_cannot_archive_a_fence_release_intent(tmp_path: Path, capsys) -> None:
    """0101 receipt 예외는 root in-process primitive에만 있고 공개 CLI에는 없다."""

    module = _module()
    state_directory = tmp_path / "forensics"
    state_directory.mkdir(mode=0o700)
    assert module.main(_begin_arguments(state_directory)) == 0
    operation_id = capsys.readouterr().out.strip()
    intent_marker_sha256 = _advance_to_release_intent(module, state_directory, operation_id)
    assert (
        module.main(
            _seal_arguments(
                state_directory,
                operation_id,
                intent_marker_sha256=intent_marker_sha256,
            )
        )
        == 0
    )

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
        == 3
    )
    assert "not safe for recovery acknowledgement" in capsys.readouterr().err
    assert (state_directory / "current.json").exists()


def test_verified_recovery_acknowledgement_refuses_a_marker_changed_after_proof(
    tmp_path: Path, capsys
) -> None:
    """root DB proof의 raw marker는 archive lock 안에서 다시 CAS 확인해야 한다."""

    module = _module()
    state_directory = tmp_path / "forensics"
    state_directory.mkdir(mode=0o700)
    assert module.main(_begin_arguments(state_directory)) == 0
    operation_id = capsys.readouterr().out.strip()
    intent_sha256 = _advance_to_release_intent(module, state_directory, operation_id)
    proven_sha256 = hashlib.sha256((state_directory / "current.json").read_bytes()).hexdigest()
    store = module._StateDirectory.open(state_directory, strict=False, test_mode=True)
    assert (
        module.main(
            _seal_arguments(
                state_directory,
                operation_id,
                intent_marker_sha256=intent_sha256,
            )
        )
        == 0
    )
    marker = json.loads((state_directory / "current.json").read_text(encoding="utf-8"))
    marker["drain_receipt_sha256"] = "9" * 64
    store._replace_regular("current.json", module._canonical_json(marker))
    with pytest.raises(module.ForensicsError, match="changed after verified recovery"):
        store.acknowledge_and_archive(
            operation_id,
            verification_sha256="9" * 64,
            expected_marker_sha256=proven_sha256,
            expected_release_receipt_record_sha256="1" * 64,
            trusted_release_intent=True,
        )

    assert (state_directory / "current.json").exists()
    assert not (state_directory / "operations" / f"{operation_id}.final.json").exists()
    assert not (state_directory / "recovery" / f"{operation_id}.json").exists()


def test_public_acknowledge_requires_explicit_test_mode_without_mutation(
    tmp_path: Path, capsys
) -> None:
    """public acknowledgement는 noncanonical store에서도 test mode 전용이다."""

    module = _module()
    state_directory = tmp_path / "forensics"
    state_directory.mkdir(mode=0o700)
    assert module.main(_begin_arguments(state_directory)) == 0
    operation_id = capsys.readouterr().out.strip()

    assert (
        module.main(
            [
                "acknowledge",
                "--state-dir",
                str(state_directory),
                "--operation-id",
                operation_id,
                "--verification-sha256",
                "9" * 64,
                "--confirm",
            ]
        )
        == 3
    )
    assert "must use the trusted entrypoint" in capsys.readouterr().err
    assert (state_directory / "current.json").exists()
    assert not (state_directory / "operations" / f"{operation_id}.final.json").exists()


def test_forensic_state_rejects_forged_history_and_switch_oid_matrix(
    tmp_path: Path, capsys
) -> None:
    module = _module()
    state_directory = tmp_path / "forensics"
    state_directory.mkdir(mode=0o700)
    assert module.main(_begin_arguments(state_directory)) == 0
    operation_id = capsys.readouterr().out.strip()

    current = json.loads((state_directory / "current.json").read_text(encoding="utf-8"))
    current["state"] = "fence_intent"
    current["state_history"] = [
        {"at_utc": "2026-08-24T00:00:00.000000Z", "sequence": 1, "state": "fence_intent"}
    ]
    current["fenced_connect_roles"] = ["pinvi_app"]
    current["connect_restore_grants"] = [{"grant_option": False, "role": "pinvi_app"}]
    with pytest.raises(module.ForensicsError, match="start at prepared"):
        module._validate_marker(current)

    assert module.main(_transition_arguments(state_directory, operation_id, "fence_intent")) == 0
    assert module.main(_transition_arguments(state_directory, operation_id, "fence_applied")) == 0
    assert module.main(_transition_arguments(state_directory, operation_id, "restore_ready")) == 0
    invalid_switch = _transition_arguments(state_directory, operation_id, "switched")
    invalid_switch[invalid_switch.index("--app-schema-oid-after-switch") + 1] = "100"
    invalid_switch[invalid_switch.index("--previous-schema-oid-after-switch") + 1] = "200"
    assert module.main(invalid_switch) == 3
    assert "oid matrix is inconsistent" in capsys.readouterr().err


def test_failure_latch_blocks_all_automatic_transitions_and_acknowledgement(
    tmp_path: Path, capsys
) -> None:
    module = _module()
    state_directory = tmp_path / "forensics"
    state_directory.mkdir(mode=0o700)
    assert module.main(_begin_arguments(state_directory)) == 0
    operation_id = capsys.readouterr().out.strip()
    assert module.main(_transition_arguments(state_directory, operation_id, "fence_intent")) == 0
    assert (
        module.main(
            [
                "failure",
                "--state-dir",
                str(state_directory),
                "--test-mode",
                "--operation-id",
                operation_id,
                "--phase",
                "restore",
                "--code",
                "pg_restore_failed",
            ]
        )
        == 0
    )
    latched = json.loads((state_directory / "current.json").read_text(encoding="utf-8"))
    assert latched["recovery_required"] is True
    assert latched["failure"] == {"code": "pg_restore_failed", "phase": "restore"}
    assert module.main(_transition_arguments(state_directory, operation_id, "fence_applied")) == 3
    assert "recovery latched" in capsys.readouterr().err
    assert (
        module.main(_transition_arguments(state_directory, operation_id, "fence_release_intent"))
        == 3
    )
    assert "recovery latched" in capsys.readouterr().err

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
        == 3
    )
    assert "not safe for recovery acknowledgement" in capsys.readouterr().err
    assert json.loads((state_directory / "current.json").read_text(encoding="utf-8")) == latched
    assert not (state_directory / "operations" / f"{operation_id}.final.json").exists()


@pytest.mark.parametrize("alias_kind", ("dotdot", "double_slash"))
def test_public_acknowledge_rejects_every_canonical_store_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, alias_kind: str
) -> None:
    module = _module()
    canonical = tmp_path / "restore-forensics"
    canonical.mkdir(mode=0o700)
    monkeypatch.setattr(module, "DEFAULT_STATE_DIRECTORY", canonical)
    assert module.main(_begin_arguments(canonical)) == 0
    operation_id = capsys.readouterr().out.strip()
    for state in (
        "fence_intent",
        "fence_applied",
        "restore_ready",
        "switched",
        "fence_release_intent",
    ):
        assert module.main(_transition_arguments(canonical, operation_id, state)) == 0

    if alias_kind == "dotdot":
        (tmp_path / "alias-parent").mkdir()
        alias = f"{tmp_path}/alias-parent/../{canonical.name}"
    else:
        alias = f"/{canonical}"
    assert (
        module.main(
            [
                "acknowledge",
                "--state-dir",
                alias,
                "--test-mode",
                "--operation-id",
                operation_id,
                "--verification-sha256",
                "9" * 64,
                "--confirm",
            ]
        )
        == 3
    )
    assert "must use the trusted entrypoint" in capsys.readouterr().err
    assert (canonical / "current.json").exists()


def test_public_acknowledge_rejects_strict_flag_without_mutation(tmp_path: Path, capsys) -> None:
    module = _module()
    state_directory = tmp_path / "forensics"
    state_directory.mkdir(mode=0o700)
    assert module.main(_begin_arguments(state_directory)) == 0
    operation_id = capsys.readouterr().out.strip()

    assert (
        module.main(
            [
                "acknowledge",
                "--state-dir",
                str(state_directory),
                "--strict",
                "--operation-id",
                operation_id,
                "--verification-sha256",
                "9" * 64,
                "--confirm",
            ]
        )
        == 3
    )
    assert "must use the trusted entrypoint" in capsys.readouterr().err
    assert (state_directory / "current.json").exists()


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


def test_terminal_transition_rejects_no_switch_mode(tmp_path: Path, capsys) -> None:
    module = _module()
    state_directory = tmp_path / "forensics"
    state_directory.mkdir(mode=0o700)
    assert module.main(_begin_arguments(state_directory)) == 0
    operation_id = capsys.readouterr().out.strip()
    for state in ("fence_intent", "fence_applied", "restore_ready", "switched"):
        assert module.main(_transition_arguments(state_directory, operation_id, state)) == 0
    terminal_intent = _transition_arguments(state_directory, operation_id, "fence_release_intent")
    terminal_intent[-1] = "no_switch"
    with pytest.raises(SystemExit) as error:
        module.main(terminal_intent)
    assert error.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_status_allow_absent_only_reports_an_absent_current_pointer(tmp_path: Path, capsys) -> None:
    module = _module()
    state_directory = tmp_path / "forensics"
    state_directory.mkdir(mode=0o700)
    status = [
        "status",
        "--state-dir",
        str(state_directory),
        "--test-mode",
        "--allow-absent",
    ]
    assert module.main(status) == 0
    assert capsys.readouterr().out == '{"active":false}\n'

    assert module.main(_begin_arguments(state_directory)) == 0
    operation_id = capsys.readouterr().out.strip()
    assert module._UUID_RE.fullmatch(operation_id)
    assert module.main(status) == 0
    assert json.loads(capsys.readouterr().out)["operation_id"] == operation_id
