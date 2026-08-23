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
        )


def test_m05_endpoint_rejects_wildcard_host_binding() -> None:
    module = _attestation_module()
    with pytest.raises(module.AttestationError, match="bound"):
        module._assert_docker_endpoint(
            {
                "NetworkSettings": {
                    "Ports": {
                        "8000/tcp": [
                            {"HostIp": "0.0.0" + ".0", "HostPort": "12801"}
                        ]
                    }
                }
            },
            container="pinvi-api",
            endpoint_url="http://127.0.0.1:12801",
            container_port=8000,
        )
