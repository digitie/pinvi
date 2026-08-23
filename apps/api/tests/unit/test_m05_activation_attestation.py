"""M05 live attestation이 실제 UI marker와 loopback runtime을 결속하는지 검증한다."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _attestation_module():
    script = Path(__file__).resolve().parents[4] / "scripts/m05_activation_attestation.py"
    spec = importlib.util.spec_from_file_location("m05_activation_attestation", script)
    if spec is None or spec.loader is None:
        raise AssertionError("attestation module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    )

    broken = _marker()
    broken["impact_count"] = 1
    with pytest.raises(module.AttestationError, match="receipt field"):
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
