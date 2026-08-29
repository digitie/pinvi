"""M05 live attestation이 실제 UI marker와 loopback runtime을 결속하는지 검증한다."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _attestation_module():
    script = Path(__file__).resolve().parents[4] / "scripts/m05_activation_attestation.py"
    spec = importlib.util.spec_from_file_location("m05_activation_attestation", script)
    if spec is None or spec.loader is None:
        raise AssertionError("attestation module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def linux_tmp_path() -> Iterator[Path]:
    with TemporaryDirectory(prefix="pinvi-m05-attestation-", dir="/tmp") as temp_dir:
        yield Path(temp_dir)


def _marker() -> dict[str, object]:
    return {
        "assertions": ["status", "action", "old_feature", "replacement_feature", "impact_count"],
        "event_id": "11111111-1111-4111-8111-111111111111",
        "impact_count": 0,
        "old_feature_id": "feature-old",
        "pinvi_api_endpoint": "http://127.0.0.1:12801",
        "pinvi_detail_sha256": "d" * 64,
        "replacement_feature_id": "feature-new",
        "source_revision": "f" * 40,
        "status": "passed",
        "verification_id": "22222222-2222-4222-8222-222222222222",
        "playwright_runner_image_id": "sha256:" + "1" * 64,
        "playwright_runner_image_ref": (
            "mcr.microsoft.com/playwright:v1.60.0-noble@sha256:" + "2" * 64
        ),
    }


def _detail() -> dict[str, object]:
    return {
        "receipt": {
            "old_feature_id": "feature-old",
            "replacement_feature_id": "feature-new",
            "impact_count": 0,
        }
    }


def test_write_json_syncs_the_evidence_file_and_parent_directory(
    monkeypatch: pytest.MonkeyPatch, linux_tmp_path: Path
) -> None:
    module = _attestation_module()
    calls: list[int] = []
    real_fsync = module.os.fsync

    def recording_fsync(descriptor: int) -> None:
        calls.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(module.os, "fsync", recording_fsync)

    output = linux_tmp_path / "attestation.json"
    module._write_json(output, {"status": "passed"})

    assert output.is_file()
    assert len(calls) == 2


def test_isolated_runtime_provenance_binds_exact_source_openapi_and_images(
    linux_tmp_path: Path,
) -> None:
    module = _attestation_module()
    pair = module._load_pair()
    provenance = {
        "kind": "m05-isolated-runtime-provenance-v1",
        "execution_identity_sha256": "d" * 64,
        "manager_source_revision": "a" * 40,
        "map": {
            "admin_image_id": "sha256:" + "1" * 64,
            "api_image_id": "sha256:" + "2" * 64,
            "frontend_image_id": "sha256:" + "3" * 64,
            "full_openapi_sha256": pair["full"]["openapi_sha256"],
            "source_revision": pair["full"]["source_revision"],
        },
        "pinset_sha256": "e" * 64,
        "pinvi": {
            "api_image_id": "sha256:" + "5" * 64,
            "dagster_image_id": "sha256:" + "6" * 64,
            "source_revision": "f" * 40,
            "web_image_id": "sha256:" + "7" * 64,
        },
        "transaction_id": "8" * 32,
        "version": 1,
    }
    path = linux_tmp_path / "isolated-runtime-provenance.json"
    path.write_text(json.dumps(provenance), encoding="utf-8")
    path.chmod(0o600)

    loaded = module._load_isolated_runtime_provenance(
        path,
        pair=pair,
        pinvi_source_revision="f" * 40,
        expected_manager_source_revision="a" * 40,
        expected_pinset_sha256="e" * 64,
        expected_execution_identity_sha256="d" * 64,
        require_root_owned=False,
    )

    assert loaded["map_images"] == {
        "admin": "sha256:" + "1" * 64,
        "api": "sha256:" + "2" * 64,
        "frontend": "sha256:" + "3" * 64,
    }
    assert loaded["pinvi_images"] == {
        "api": "sha256:" + "5" * 64,
        "dagster": "sha256:" + "6" * 64,
        "web": "sha256:" + "7" * 64,
    }
    assert loaded["execution_identity_sha256"] == "d" * 64
    assert loaded["manager_source_revision"] == "a" * 40
    assert loaded["pinset_sha256"] == "e" * 64

    with pytest.raises(module.AttestationError, match="pinset differs"):
        module._load_isolated_runtime_provenance(
            path,
            pair=pair,
            pinvi_source_revision="f" * 40,
            expected_manager_source_revision="a" * 40,
            expected_pinset_sha256="4" * 64,
            expected_execution_identity_sha256="d" * 64,
            require_root_owned=False,
        )

    with pytest.raises(module.AttestationError, match="execution identity differs"):
        module._load_isolated_runtime_provenance(
            path,
            pair=pair,
            pinvi_source_revision="f" * 40,
            expected_manager_source_revision="a" * 40,
            expected_pinset_sha256="e" * 64,
            expected_execution_identity_sha256="0" * 64,
            require_root_owned=False,
        )

    provenance["map"]["full_openapi_sha256"] = "0" * 64
    path.write_text(json.dumps(provenance), encoding="utf-8")
    with pytest.raises(module.AttestationError, match="differs from the pair"):
        module._load_isolated_runtime_provenance(
            path,
            pair=pair,
            pinvi_source_revision="f" * 40,
            expected_manager_source_revision="a" * 40,
            expected_pinset_sha256="e" * 64,
            expected_execution_identity_sha256="d" * 64,
            require_root_owned=False,
        )


def test_m05_impact_evidence_recomputes_rows_and_receipts() -> None:
    module = _attestation_module()
    event_id = "11111111-1111-4111-8111-111111111111"
    event_sha = "a" * 64
    old_feature = {
        "feature_id": "feature-old",
        "feature_uuid": "55555555-5555-4555-8555-555555555555",
        "row_revision": 2,
    }
    replacement_feature = {
        "feature_id": "feature-new",
        "feature_uuid": "66666666-6666-4666-8666-666666666666",
        "row_revision": 3,
    }
    canonical_impact = {
        "target_relation": "trip_day_pois",
        "target_id": "77777777-7777-4777-8777-777777777777",
        "old_feature": old_feature,
        "replacement_feature": replacement_feature,
        "outcome": "rebind",
    }
    impact_root = module._sha256(module._canonical_json([canonical_impact]))
    receipt_material = {
        "version": "pinvi-feature-reference-reconciliation-receipt-v1",
        "event_id": event_id,
        "event_sequence": 7,
        "event_sha256": event_sha,
        "action": "rebind",
        "old_feature": old_feature,
        "replacement_feature": replacement_feature,
        "impact_root_sha256": impact_root,
        "impact_count": 1,
    }
    receipt_sha = module._sha256(module._canonical_json(receipt_material))
    observation_root = module._sha256(
        module._canonical_json(
            {
                "version": "pinvi-feature-reference-reconciliation-observation-v1",
                "event_id": event_id,
                "event_sequence": 7,
                "event_sha256": event_sha,
                "blocks": [],
                "impacts": [canonical_impact],
            }
        )
    )
    map_case = {
        "event": {
            "event_id": event_id,
            "event_sequence": 7,
            "event_sha256": event_sha,
            "action": "rebind",
            "old_feature": old_feature,
            "replacement_feature": replacement_feature,
        }
    }
    map_ack = {"event_id": event_id, "event_sha256": event_sha}
    detail = {
        "status": "applied",
        "receipt": {
            "event_id": event_id,
            "event_sequence": 7,
            "event_sha256": event_sha,
            "action": "rebind",
            "old_feature_id": old_feature["feature_id"],
            "old_feature_uuid": old_feature["feature_uuid"],
            "replacement_feature_id": replacement_feature["feature_id"],
            "replacement_feature_uuid": replacement_feature["feature_uuid"],
            "impact_root_sha256": impact_root,
            "impact_count": 1,
            "receipt_sha256": receipt_sha,
        },
        "impacts": [
            {
                "event_id": event_id,
                "impact_index": 0,
                "target_relation": "trip_day_pois",
                "target_id": canonical_impact["target_id"],
                "old_feature_id": old_feature["feature_id"],
                "old_feature_uuid": old_feature["feature_uuid"],
                "replacement_feature_id": replacement_feature["feature_id"],
                "replacement_feature_uuid": replacement_feature["feature_uuid"],
                "outcome": "rebind",
                "recorded_at": "2026-08-26T00:00:00Z",
            }
        ],
        "attempts": [
            {
                "event_id": event_id,
                "attempt_sequence": 1,
                "event_sequence": 7,
                "event_sha256": event_sha,
                "status": "applied",
                "block_fingerprint_sha256": None,
                "observation_root_sha256": observation_root,
            }
        ],
    }
    module._validate_pinvi_impact_evidence(
        detail,
        map_case=map_case,
        map_ack=map_ack,
    )

    tampered = json.loads(json.dumps(detail))
    tampered["impacts"][0]["old_feature_id"] = "feature-tampered"
    with pytest.raises(module.AttestationError, match="old feature pair"):
        module._validate_pinvi_impact_evidence(
            tampered,
            map_case=map_case,
            map_ack=map_ack,
        )


def _m04_marker() -> dict[str, object]:
    return {
        "assertions": [
            "pinvi_approved",
            "pinvi_approval_binding",
            "map_request_id",
            "map_pending_receipt",
            "map_pending_receipt_fingerprint",
            "same_origin",
        ],
        "feature_request_id": "33333333-3333-4333-8333-333333333333",
        "map_action": "submit",
        "map_pending_receipt_sha256": "b" * 64,
        "map_request_id": "33333333-3333-4333-8333-333333333333",
        "map_review_mode": "feature_request_queue",
        "map_state": "pending",
        "pinvi_api_endpoint": "http://127.0.0.1:12801",
        "pinvi_approval_sha256": "a" * 64,
        "playwright_runner_image_id": "sha256:" + "1" * 64,
        "playwright_runner_image_ref": (
            "mcr.microsoft.com/playwright:v1.60.0-noble@sha256:" + "2" * 64
        ),
        "source_revision": "f" * 40,
        "status": "passed",
        "verification_id": "22222222-2222-4222-8222-222222222222",
    }


def test_m05_marker_is_bound_to_nonce_runner_and_after_snapshot() -> None:
    module = _attestation_module()
    module._validate_ui_marker(
        _marker(),
        event_id="11111111-1111-4111-8111-111111111111",
        source_revision="f" * 40,
        verification_id="22222222-2222-4222-8222-222222222222",
        runner_image={
            "image_id": "sha256:" + "1" * 64,
            "image_ref": "mcr.microsoft.com/playwright:v1.60.0-noble@sha256:" + "2" * 64,
        },
        pinvi_detail=_detail(),
        pinvi_detail_sha256="d" * 64,
        expected_pinvi_api_endpoint="http://127.0.0.1:12801",
        expected_old_feature_id="feature-old",
        expected_replacement_feature_id="feature-new",
        expected_impact_count=0,
    )

    broken = _marker()
    broken["impact_count"] = 1
    with pytest.raises(module.AttestationError, match="live input"):
        module._validate_ui_marker(
            broken,
            event_id="11111111-1111-4111-8111-111111111111",
            source_revision="f" * 40,
            verification_id="22222222-2222-4222-8222-222222222222",
            runner_image={
                "image_id": "sha256:" + "1" * 64,
                "image_ref": "mcr.microsoft.com/playwright:v1.60.0-noble@sha256:" + "2" * 64,
            },
            pinvi_detail=_detail(),
            pinvi_detail_sha256="d" * 64,
            expected_pinvi_api_endpoint="http://127.0.0.1:12801",
            expected_old_feature_id="feature-old",
            expected_replacement_feature_id="feature-new",
            expected_impact_count=0,
        )

    broken = _m04_marker()
    broken["pinvi_approval_sha256"] = "c" * 64
    with pytest.raises(module.AttestationError, match="persisted approval receipt"):
        module._validate_m04_ui_marker(
            broken,
            feature_request_id="33333333-3333-4333-8333-333333333333",
            source_revision="f" * 40,
            verification_id="22222222-2222-4222-8222-222222222222",
            runner_image={
                "image_id": "sha256:" + "1" * 64,
                "image_ref": "mcr.microsoft.com/playwright:v1.60.0-noble@sha256:" + "2" * 64,
            },
            expected_pinvi_api_endpoint="http://127.0.0.1:12801",
            expected_pinvi_approval_sha256="a" * 64,
            expected_map_pending_receipt_sha256="b" * 64,
        )


def test_m04_marker_is_bound_to_pending_map_receipt_and_runner() -> None:
    module = _attestation_module()
    marker = module._validate_m04_ui_marker(
        _m04_marker(),
        feature_request_id="33333333-3333-4333-8333-333333333333",
        source_revision="f" * 40,
        verification_id="22222222-2222-4222-8222-222222222222",
        runner_image={
            "image_id": "sha256:" + "1" * 64,
            "image_ref": "mcr.microsoft.com/playwright:v1.60.0-noble@sha256:" + "2" * 64,
        },
        expected_pinvi_api_endpoint="http://127.0.0.1:12801",
        expected_pinvi_approval_sha256="a" * 64,
        expected_map_pending_receipt_sha256="b" * 64,
    )

    assert marker["map_state"] == "pending"
    broken = _m04_marker()
    broken["map_state"] = "approved"
    with pytest.raises(module.AttestationError, match="pending receipt"):
        module._validate_m04_ui_marker(
            broken,
            feature_request_id="33333333-3333-4333-8333-333333333333",
            source_revision="f" * 40,
            verification_id="22222222-2222-4222-8222-222222222222",
            runner_image={
                "image_id": "sha256:" + "1" * 64,
                "image_ref": "mcr.microsoft.com/playwright:v1.60.0-noble@sha256:" + "2" * 64,
            },
            expected_pinvi_api_endpoint="http://127.0.0.1:12801",
            expected_pinvi_approval_sha256="a" * 64,
            expected_map_pending_receipt_sha256="b" * 64,
        )


def test_m05_endpoint_rejects_wildcard_host_binding() -> None:
    module = _attestation_module()
    with pytest.raises(module.AttestationError, match="bound"):
        module._assert_docker_endpoint(
            {
                "NetworkSettings": {
                    "Ports": {"8000/tcp": [{"HostIp": "0.0.0" + ".0", "HostPort": "12801"}]}
                }
            },
            container="pinvi-api",
            endpoint_url="http://127.0.0.1:12801",
            container_port=8000,
        )


def test_m05_map_checkout_allowlist_uses_only_source_revisions() -> None:
    module = _attestation_module()
    pair = module._load_pair()

    allowed = {pair[name]["source_revision"] for name in ("admin", "full", "service", "user")}

    assert "runtime_image_digests" not in allowed
    assert pair["full"]["source_revision"] in allowed


def test_playwright_image_reference_accepts_digest_only_or_tagged_digest() -> None:
    module = _attestation_module()
    for image_ref in (
        "mcr.microsoft.com/playwright@sha256:" + "2" * 64,
        "mcr.microsoft.com/playwright:v1.60.0-noble@sha256:" + "2" * 64,
    ):
        assert module._PLAYWRIGHT_IMAGE_RE.fullmatch(image_ref) is not None


def test_m05_map_case_binds_missing_event_hash_to_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _attestation_module()
    monkeypatch.setenv("M05_MAP_ADMIN_PROXY_SECRET", "s" * 32)
    event_id = "11111111-1111-4111-8111-111111111111"
    ack_hash = "a" * 64
    response = {
        "data": {
            "status": "terminal",
            "event": {"event_id": event_id, "event_sequence": 1},
            "subscriptions": [
                {
                    "principal_id": "service:feature-reference-reconciliation",
                    "acked_through_sequence": 1,
                    "ack": {
                        "event_id": event_id,
                        "event_sha256": ack_hash,
                        "local_receipt_sha256": "b" * 64,
                    },
                }
            ],
        }
    }
    monkeypatch.setattr(module, "_http_json", lambda *args, **kwargs: (response, b"{}"))

    _data, ack, _map_hash, _ack_hash = module._map_case_snapshot(
        map_admin_url="http://127.0.0.1:14701",
        case_id="22222222-2222-4222-8222-222222222222",
        event_id=event_id,
    )

    assert ack["event_sha256"] == ack_hash
    assert module._map_case_event_hash(_data, ack) == ack_hash


def test_m04_server_side_chain_binds_approved_request_to_m05_old_feature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _attestation_module()
    monkeypatch.setenv("M05_MAP_ADMIN_PROXY_SECRET", "s" * 32)
    feature_id = "feature-m04-approved"
    feature_uuid = "44444444-4444-4444-8444-444444444444"
    responses = iter(
        (
            (
                {
                    "data": {
                        "request_id": "33333333-3333-4333-8333-333333333333",
                        "status": "approved",
                        "feature_id": feature_id,
                    }
                },
                b"{}",
            ),
            (
                {
                    "data": {
                        "feature_id": feature_id,
                        "feature_uuid": feature_uuid,
                        "origin": {"origin_kind": "manual_request"},
                    }
                },
                b"{}",
            ),
        )
    )
    monkeypatch.setattr(module, "_http_json", lambda *args, **kwargs: next(responses))
    chain = module._m04_server_side_chain(
        map_admin_url="http://127.0.0.1:14701",
        m04={"feature_request_id": "33333333-3333-4333-8333-333333333333"},
        map_case={
            "manual_feature": {"feature_id": feature_id, "feature_uuid": feature_uuid},
            "event": {"old_feature": {"feature_id": feature_id, "feature_uuid": feature_uuid}},
        },
    )

    assert chain["map_feature_id"] == feature_id
    assert chain["map_feature_uuid"] == feature_uuid


@pytest.mark.parametrize(
    ("provenance_feature_id", "provenance_feature_uuid", "error"),
    (
        (
            "feature-other-approved",
            "44444444-4444-4444-8444-444444444444",
            "Map M04 provenance does not match the approved feature",
        ),
        (
            "feature-m04-approved",
            "55555555-5555-4555-8555-555555555555",
            "M04 approved feature does not match the M05 old feature",
        ),
    ),
)
def test_m04_server_side_chain_rejects_provenance_identity_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    provenance_feature_id: str,
    provenance_feature_uuid: str,
    error: str,
) -> None:
    module = _attestation_module()
    monkeypatch.setenv("M05_MAP_ADMIN_PROXY_SECRET", "s" * 32)
    feature_id = "feature-m04-approved"
    feature_uuid = "44444444-4444-4444-8444-444444444444"
    responses = iter(
        (
            (
                {
                    "data": {
                        "request_id": "33333333-3333-4333-8333-333333333333",
                        "status": "approved",
                        "feature_id": feature_id,
                    }
                },
                b"{}",
            ),
            (
                {
                    "data": {
                        "feature_id": provenance_feature_id,
                        "feature_uuid": provenance_feature_uuid,
                        "origin": {"origin_kind": "manual_request"},
                    }
                },
                b"{}",
            ),
        )
    )
    monkeypatch.setattr(module, "_http_json", lambda *args, **kwargs: next(responses))

    with pytest.raises(module.AttestationError, match=error):
        module._m04_server_side_chain(
            map_admin_url="http://127.0.0.1:14701",
            m04={"feature_request_id": "33333333-3333-4333-8333-333333333333"},
            map_case={
                "manual_feature": {"feature_id": feature_id, "feature_uuid": feature_uuid},
                "event": {"old_feature": {"feature_id": feature_id, "feature_uuid": feature_uuid}},
            },
        )


def test_m04_approval_snapshot_recomputes_the_persisted_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _attestation_module()
    request_id = "33333333-3333-4333-8333-333333333333"
    map_receipt = {
        "action": "submit",
        "request_id": request_id,
        "review_mode": "feature_request_queue",
        "state": "pending",
    }
    item = {
        "kor_travel_map_ref": map_receipt,
        "request_id": request_id,
        "resolved_at": "2026-08-25T00:00:00Z",
        "reviewed_by_admin_id": "44444444-4444-4444-8444-444444444444",
        "status": "approved",
    }
    responses = iter(
        (
            ({"data": {"roles": ["admin"]}}, b"{}"),
            ({"data": {"items": [item]}}, b"{}"),
        )
    )
    monkeypatch.setattr(module, "_http_json", lambda *args, **kwargs: next(responses))

    snapshot = module._pinvi_m04_approval_snapshot(
        pinvi_api_url="http://127.0.0.1:12801",
        request_id=request_id,
        email="admin@example.com",
        password="test-password",
    )

    assert snapshot == {
        "map_pending_receipt_sha256": hashlib.sha256(
            module._canonical_json(map_receipt)
        ).hexdigest(),
        "pinvi_approval_sha256": hashlib.sha256(
            module._canonical_json(
                {
                    "kor_travel_map_ref": map_receipt,
                    "request_id": request_id,
                    "resolved_at": item["resolved_at"],
                    "reviewed_by_admin_id": item["reviewed_by_admin_id"],
                    "status": "approved",
                }
            )
        ).hexdigest(),
    }


def test_m04_signed_evidence_is_bound_to_the_same_pinvi_runtime(linux_tmp_path: Path) -> None:
    module = _attestation_module()
    evidence_dir = linux_tmp_path / "m04-evidence"
    evidence_dir.mkdir(mode=0o700)
    live = {
        "feature_request_id": "33333333-3333-4333-8333-333333333333",
        "map_action": "submit",
        "map_pending_receipt_sha256": "c" * 64,
        "map_request_id": "33333333-3333-4333-8333-333333333333",
        "map_review_mode": "feature_request_queue",
        "map_state": "pending",
        "m04_created_at": 1,
        "pinvi_api_container_id": "3" * 64,
        "pinvi_api_endpoint": "http://127.0.0.1:12801",
        "pinvi_approval_sha256": "a" * 64,
        "pinvi_source_revision": "f" * 40,
        "pinvi_web_container_id": "4" * 64,
        "pinvi_web_endpoint": "http://127.0.0.1:12805",
        "playwright_runner_image_id": "sha256:" + "1" * 64,
        "playwright_runner_image_ref": "mcr.microsoft.com/playwright:v1.60.0-noble@sha256:"
        + "2" * 64,
        "runner_exit_code": 0,
        "runtime_identity_verified": True,
        "status": "passed",
        "ui_evidence_sha256": "b" * 64,
        "verification_id": "22222222-2222-4222-8222-222222222222",
    }
    live_path = evidence_dir / "m04-live-ui.json"
    live_raw = json.dumps(live, sort_keys=True).encode()
    live_path.write_bytes(live_raw)
    live_path.chmod(0o600)
    key = Ed25519PrivateKey.generate()
    payload = {
        "created_at": 1,
        "feature_request_id": live["feature_request_id"],
        "map_pending_receipt_sha256": live["map_pending_receipt_sha256"],
        "m04_live_ui_sha256": hashlib.sha256(live_raw).hexdigest(),
        "pinvi_api_endpoint": live["pinvi_api_endpoint"],
        "pinvi_approval_sha256": live["pinvi_approval_sha256"],
        "pinvi_source_revision": live["pinvi_source_revision"],
        "pinvi_web_endpoint": live["pinvi_web_endpoint"],
        "playwright_runner_image_id": live["playwright_runner_image_id"],
        "playwright_runner_image_ref": live["playwright_runner_image_ref"],
        "scope": "smoke",
        "status": "passed",
        "verification_id": live["verification_id"],
        "version": 2,
    }
    attestation = {
        "payload": payload,
        "signature": base64.urlsafe_b64encode(key.sign(module._canonical_json(payload)))
        .decode()
        .rstrip("="),
    }
    attestation_path = evidence_dir / "m04-attestation.json"
    attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
    attestation_path.chmod(0o600)

    evidence = module._read_m04_evidence(
        evidence_dir,
        require_root_owned=False,
        public_key_bytes=key.public_key().public_bytes_raw(),
        source_revision="f" * 40,
        scope="smoke",
        expected_pinvi_api_endpoint="http://127.0.0.1:12801",
        expected_pinvi_api_container_id="3" * 64,
        expected_pinvi_web_endpoint="http://127.0.0.1:12805",
        expected_pinvi_web_container_id="4" * 64,
    )

    assert evidence["feature_request_id"] == live["feature_request_id"]
    assert evidence["m04_created_at"] == "1"
    with pytest.raises(module.AttestationError, match="API runtime"):
        module._read_m04_evidence(
            evidence_dir,
            require_root_owned=False,
            public_key_bytes=key.public_key().public_bytes_raw(),
            source_revision="f" * 40,
            scope="smoke",
            expected_pinvi_api_endpoint="http://127.0.0.1:12801",
            expected_pinvi_api_container_id="5" * 64,
            expected_pinvi_web_endpoint="http://127.0.0.1:12805",
            expected_pinvi_web_container_id="4" * 64,
        )


def test_host_openssl_fallback_signs_and_verifies_ed25519(
    linux_tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _attestation_module()
    key = Ed25519PrivateKey.generate()
    key_path = linux_tmp_path / "m05-private-key.pem"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    monkeypatch.setattr(module, "_CRYPTOGRAPHY_AVAILABLE", False)

    loaded = module._load_private_key(key_path, require_root_owned=False)
    payload = module._canonical_json({"scope": "isolated", "status": "passed"})
    signature = module._sign(loaded, payload)
    public_key = module._public_key_bytes(loaded)

    assert public_key == key.public_key().public_bytes_raw()
    assert len(signature) == 64
    key.public_key().verify(signature, payload)
    module._verify_ed25519_signature(public_key, signature, payload)
    with pytest.raises(module.AttestationError, match="signature is invalid"):
        module._verify_ed25519_signature(public_key, signature, payload + b"!")
