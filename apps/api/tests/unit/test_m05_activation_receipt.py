"""M05 evidence signer와 production Settings 서명 검증의 왕복 계약."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core import config as config_module
from app.core.config import (
    KOR_TRAVEL_MAP_M05_ADMIN_IMAGE_DIGEST,
    KOR_TRAVEL_MAP_M05_ADMIN_OPENAPI_SHA256,
    KOR_TRAVEL_MAP_M05_ADMIN_SOURCE_REVISION,
    KOR_TRAVEL_MAP_M05_API_IMAGE_DIGEST,
    KOR_TRAVEL_MAP_M05_FRONTEND_IMAGE_DIGEST,
    KOR_TRAVEL_MAP_M05_FULL_OPENAPI_SHA256,
    KOR_TRAVEL_MAP_M05_FULL_SOURCE_REVISION,
    KOR_TRAVEL_MAP_M05_USER_OPENAPI_SHA256,
    KOR_TRAVEL_MAP_M05_USER_SOURCE_REVISION,
    KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256,
    KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
    Settings,
)

READ = "r" * 32
ACK = "a" * 32
PINVI_REVISION = "f" * 40
PINVI_DIGESTS = {
    "api": "sha256:" + "1" * 64,
    "web": "sha256:" + "2" * 64,
    "dagster": "sha256:" + "3" * 64,
}


def _test_trust_anchor_sha256(private_key: Ed25519PrivateKey) -> str:
    return hashlib.sha256(private_key.public_key().public_bytes_raw()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    path.chmod(0o600)


@pytest.fixture
def linux_tmp_path() -> Iterator[Path]:
    with TemporaryDirectory(prefix="pinvi-m05-receipt-", dir="/tmp") as temp_dir:
        yield Path(temp_dir)


def test_m05_signer_seals_checked_evidence_and_settings_accepts_it(
    linux_tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    tmp_path = linux_tmp_path
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(mode=0o700)
    _write_json(
        evidence_dir / "reviews.json",
        [
            {
                "agent_id": "44444444-4444-4444-8444-444444444444",
                "commit": PINVI_REVISION,
                "p0_p1": 0,
                "pr_url": "https://github.com/digitie/pinvi/pull/466",
                "review_id": "review-1",
                "reviewer_id": "darwin",
                "summary": "GO: no P0/P1 findings",
                "summary_sha256": hashlib.sha256(b"GO: no P0/P1 findings").hexdigest(),
                "verdict": "GO",
            },
            {
                "agent_id": "55555555-5555-4555-8555-555555555555",
                "commit": PINVI_REVISION,
                "p0_p1": 0,
                "pr_url": "https://github.com/digitie/pinvi/pull/466",
                "review_id": "review-2",
                "reviewer_id": "feynman",
                "summary": "GO: no P0/P1 findings",
                "summary_sha256": hashlib.sha256(b"GO: no P0/P1 findings").hexdigest(),
                "verdict": "GO",
            },
        ],
    )
    _write_json(
        evidence_dir / "live-ui.json",
        {
            "event_id": "11111111-1111-4111-8111-111111111111",
            "event_sha256": "a" * 64,
            "map_admin_endpoint": "http://127.0.0.1:12701",
            "map_ack_sha256": "b" * 64,
            "map_local_receipt_sha256": "1" * 64,
            "map_snapshot_after_sha256": "c" * 64,
            "map_snapshot_before_sha256": "c" * 64,
            "pinvi_source_revision": PINVI_REVISION,
            "pinvi_api_endpoint": "http://127.0.0.1:12801",
            "pinvi_web_endpoint": "http://127.0.0.1:12805",
            "pinvi_receipt_sha256": "1" * 64,
            "pinvi_snapshot_after_sha256": "d" * 64,
            "pinvi_snapshot_before_sha256": "d" * 64,
            "runner_exit_code": 0,
            "server_side_ack_verified": True,
            "status": "passed",
            "ui_evidence_sha256": "e" * 64,
            "verification_id": "22222222-2222-4222-8222-222222222222",
            "playwright_runner_image_id": "sha256:" + "9" * 64,
            "playwright_runner_image_ref": "mcr.microsoft.com/playwright:v1.60.0-noble@sha256:" + "8" * 64,
        },
    )
    _write_json(
        evidence_dir / "restore.json",
        {
            "backup_runner_sha256": "1" * 64,
            "dump_sha256": "c" * 64,
            "execution_id": "33333333-3333-4333-8333-333333333333",
            "no_owner_restore": True,
            "restore_command": "pg_restore --no-owner --no-privileges",
            "restore_output_sha256": "2" * 64,
            "restore_runner_sha256": "3" * 64,
            "runtime_db_identity": {
                "database": "target",
                "database_oid": "200",
                "schema_exists": True,
                "server_version_num": "160000",
                "system_identifier": "1",
                "user": "pinvi_app",
            },
            "runtime_role": "pinvi_app",
            "runtime_role_verified": True,
            "source_db_identity": {
                "database": "source",
                "database_oid": "100",
                "schema_exists": True,
                "server_version_num": "160000",
                "system_identifier": "1",
                "user": "pinvi_owner",
            },
            "source_db_identity_after_backup": {
                "database": "source",
                "database_oid": "100",
                "schema_exists": True,
                "server_version_num": "160000",
                "system_identifier": "1",
                "user": "pinvi_owner",
            },
            "source_db_identity_after_backup_sha256": "a" * 64,
            "source_db_identity_sha256": "d" * 64,
            "source_revision": PINVI_REVISION,
            "staging_role": "pinvi_owner",
            "staging_role_verified": True,
            "status": "passed",
            "target_db_identity": {
                "database": "target",
                "database_oid": "200",
                "schema_exists": True,
                "server_version_num": "160000",
                "system_identifier": "1",
                "user": "pinvi_owner",
            },
            "target_db_identity_before_restore": {
                "database": "target",
                "database_oid": "200",
                "schema_exists": True,
                "server_version_num": "160000",
                "system_identifier": "1",
                "user": "pinvi_owner",
            },
            "target_db_identity_before_restore_sha256": "b" * 64,
            "target_db_identity_sha256": "e" * 64,
            "trigger_guard_verified": True,
            "runtime_db_identity_sha256": "f" * 64,
        },
    )
    _write_json(
        evidence_dir / "map-pair.json",
        {
            "admin_image_digest": KOR_TRAVEL_MAP_M05_ADMIN_IMAGE_DIGEST,
            "api_image_digest": KOR_TRAVEL_MAP_M05_API_IMAGE_DIGEST,
            "frontend_image_digest": KOR_TRAVEL_MAP_M05_FRONTEND_IMAGE_DIGEST,
            "admin": {
                "openapi_sha256": KOR_TRAVEL_MAP_M05_ADMIN_OPENAPI_SHA256,
                "source_revision": KOR_TRAVEL_MAP_M05_ADMIN_SOURCE_REVISION,
            },
            "full": {
                "openapi_sha256": KOR_TRAVEL_MAP_M05_FULL_OPENAPI_SHA256,
                "source_revision": KOR_TRAVEL_MAP_M05_FULL_SOURCE_REVISION,
            },
            "service": {
                "openapi_sha256": KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256,
                "source_revision": KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
            },
            "user": {
                "openapi_sha256": KOR_TRAVEL_MAP_M05_USER_OPENAPI_SHA256,
                "source_revision": KOR_TRAVEL_MAP_M05_USER_SOURCE_REVISION,
            },
            "runtime": {
                "admin_openapi": {
                    "canonical_sha256": "9" * 64,
                    "source_canonical_sha256": "9" * 64,
                    "source_revision": KOR_TRAVEL_MAP_M05_ADMIN_SOURCE_REVISION,
                    "source_sha256": KOR_TRAVEL_MAP_M05_ADMIN_OPENAPI_SHA256,
                    "surface_coverage_sha256": "e" * 64,
                    "transport": "http",
                    "transport_sha256": "a" * 64,
                },
                "api": {
                    "container_id": "b" * 64,
                    "digest": KOR_TRAVEL_MAP_M05_API_IMAGE_DIGEST,
                    "environment": "production",
                    "image_id": KOR_TRAVEL_MAP_M05_API_IMAGE_DIGEST,
                    "revision_label": KOR_TRAVEL_MAP_M05_ADMIN_SOURCE_REVISION,
                    "source_revision": KOR_TRAVEL_MAP_M05_ADMIN_SOURCE_REVISION,
                    "started_at": "2026-08-23T00:00:00.000000000Z",
                },
                "admin": {
                    "container_id": "a" * 64,
                    "digest": KOR_TRAVEL_MAP_M05_ADMIN_IMAGE_DIGEST,
                    "environment": "production",
                    "image_id": KOR_TRAVEL_MAP_M05_ADMIN_IMAGE_DIGEST,
                    "revision_label": KOR_TRAVEL_MAP_M05_ADMIN_SOURCE_REVISION,
                    "source_revision": KOR_TRAVEL_MAP_M05_ADMIN_SOURCE_REVISION,
                    "started_at": "2026-08-23T00:00:00.000000000Z",
                },
                "frontend": {
                    "container_id": "c" * 64,
                    "digest": KOR_TRAVEL_MAP_M05_FRONTEND_IMAGE_DIGEST,
                    "environment": "production",
                    "image_id": KOR_TRAVEL_MAP_M05_FRONTEND_IMAGE_DIGEST,
                    "revision_label": KOR_TRAVEL_MAP_M05_ADMIN_SOURCE_REVISION,
                    "source_revision": KOR_TRAVEL_MAP_M05_ADMIN_SOURCE_REVISION,
                    "started_at": "2026-08-23T00:00:00.000000000Z",
                },
                "full_openapi_sha256": KOR_TRAVEL_MAP_M05_FULL_OPENAPI_SHA256,
                "full_openapi": {
                    "canonical_sha256": "9" * 64,
                    "source_canonical_sha256": "8" * 64,
                    "source_revision": KOR_TRAVEL_MAP_M05_FULL_SOURCE_REVISION,
                    "source_sha256": KOR_TRAVEL_MAP_M05_FULL_OPENAPI_SHA256,
                    "surface_coverage_sha256": "f" * 64,
                    "transport": "http",
                    "transport_sha256": "a" * 64,
                },
                "service_openapi": {
                    "canonical_sha256": "a" * 64,
                    "source_canonical_sha256": "a" * 64,
                    "source_revision": KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
                    "source_sha256": KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256,
                    "surface_coverage_sha256": "1" * 64,
                    "transport": "source-artifact",
                    "transport_sha256": "b" * 64,
                },
                "user_openapi": {
                    "canonical_sha256": "c" * 64,
                    "source_canonical_sha256": "c" * 64,
                    "source_revision": KOR_TRAVEL_MAP_M05_USER_SOURCE_REVISION,
                    "source_sha256": KOR_TRAVEL_MAP_M05_USER_OPENAPI_SHA256,
                    "surface_coverage_sha256": "2" * 64,
                    "transport": "source-artifact",
                    "transport_sha256": "d" * 64,
                },
            },
        },
    )
    _write_json(
        evidence_dir / "pinvi-images.json",
        {
            name: {
                "container_id": "d" * 64,
                "digest": digest,
                "environment": "production",
                "image_id": digest,
                "revision_label": PINVI_REVISION,
                "source_revision": PINVI_REVISION,
                "started_at": "2026-08-23T00:00:00.000000000Z",
            }
            for name, digest in PINVI_DIGESTS.items()
        },
    )

    private_key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(
        config_module,
        "PINVI_M05_ACTIVATION_RECEIPT_PUBLIC_KEY_SHA256",
        _test_trust_anchor_sha256(private_key),
    )
    private_key_path = tmp_path / "activation-key.pem"
    private_key_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    private_key_path.chmod(0o600)

    evidence_hashes = {
        name: hashlib.sha256((evidence_dir / f"{name}.json").read_bytes()).hexdigest()
        for name in ("live-ui", "map-pair", "pinvi-images", "restore", "reviews")
    }
    attestation_payload = {
        "created_at": int(time.time()),
        "event_id": "11111111-1111-4111-8111-111111111111",
        "evidence_sha256": evidence_hashes,
        "map_ack_sha256": "b" * 64,
        "local_receipt_sha256": "1" * 64,
        "map_admin_endpoint": "http://127.0.0.1:12701",
        "map_snapshot_sha256": "c" * 64,
        "pinvi_snapshot_sha256": "d" * 64,
        "pinvi_api_endpoint": "http://127.0.0.1:12801",
        "pinvi_web_endpoint": "http://127.0.0.1:12805",
        "pinvi_source_revision": PINVI_REVISION,
        "playwright_runner_image_id": "sha256:" + "9" * 64,
        "playwright_runner_image_ref": "mcr.microsoft.com/playwright:v1.60.0-noble@sha256:" + "8" * 64,
        "scope": "production",
        "status": "passed",
        "verification_id": "22222222-2222-4222-8222-222222222222",
        "version": 1,
    }
    attestation_bytes = json.dumps(
        attestation_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    _write_json(
        evidence_dir / "attestation.json",
        {
            "payload": attestation_payload,
            "signature": base64.urlsafe_b64encode(private_key.sign(attestation_bytes))
            .decode("ascii")
            .rstrip("="),
        },
    )
    receipt_path = tmp_path / "activation-receipt.json"
    script = Path(__file__).resolve().parents[4] / "scripts/m05_activation_receipt.py"
    completed = subprocess.run(  # noqa: S603 - invokes the repository-pinned Python test helper
        [
            sys.executable,
            str(script),
            "create",
            "--evidence-dir",
            str(evidence_dir),
            "--private-key",
            str(private_key_path),
            "--output",
            str(receipt_path),
            "--pinvi-source-revision",
            PINVI_REVISION,
            "--activation-generation",
            "2",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    public_key = next(
        line.removeprefix("public_key=")
        for line in completed.stdout.splitlines()
        if line.startswith("public_key=")
    )
    receipt = receipt_path.read_text(encoding="utf-8")
    ledger_path = tmp_path / "activation-ledger.jsonl"
    subprocess.run(  # noqa: S603 - invokes the repository-pinned Python test helper
        [
            sys.executable,
            str(script),
            "ledger",
            "--receipt",
            str(receipt_path),
            "--ledger",
            str(ledger_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    monkeypatch.setenv("PINVI_SOURCE_REVISION", PINVI_REVISION)
    loaded = Settings(
        _env_file=None,
        pinvi_environment="production",
        pinvi_kor_travel_map_api_base_url="http://127.0.0.1:12701",
        pinvi_kor_travel_map_admin_base_url="http://127.0.0.1:12701",
        pinvi_kor_travel_map_ops_read_token="o" * 32,
        pinvi_kor_travel_map_ops_cancel_token="p" * 32,
        pinvi_kor_travel_map_feature_reference_reconciliation_enabled=True,
        pinvi_kor_travel_map_feature_reference_reconciliation_read_token=READ,
        pinvi_kor_travel_map_feature_reference_reconciliation_ack_token=ACK,
        pinvi_kor_travel_map_feature_reference_reconciliation_expected_openapi_sha256=(
            KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256
        ),
        pinvi_kor_travel_map_feature_reference_reconciliation_expected_source_revision=(
            KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION
        ),
        pinvi_kor_travel_map_feature_reference_reconciliation_activation_receipt=receipt,
        pinvi_kor_travel_map_feature_reference_reconciliation_activation_receipt_public_key=public_key,
        pinvi_m05_activation_ledger_path=str(ledger_path),
        pinvi_api_image_digest=PINVI_DIGESTS["api"],
        pinvi_web_image_digest=PINVI_DIGESTS["web"],
        pinvi_dagster_image_digest=PINVI_DIGESTS["dagster"],
    )
    assert loaded.pinvi_kor_travel_map_feature_reference_reconciliation_enabled is True
