"""M05 evidence signer와 production Settings 서명 검증의 왕복 계약."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core import config as config_module
from app.core.config import (
    KOR_TRAVEL_MAP_M05_ADMIN_OPENAPI_SHA256,
    KOR_TRAVEL_MAP_M05_ADMIN_SOURCE_REVISION,
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
            {"commit": "1" * 40, "p0_p1": 0, "review_id": "review-1", "reviewer_id": "darwin"},
            {"commit": "2" * 40, "p0_p1": 0, "review_id": "review-2", "reviewer_id": "feynman"},
        ],
    )
    _write_json(
        evidence_dir / "live-ui.json",
        {
            "event_id": "11111111-1111-4111-8111-111111111111",
            "event_sha256": "a" * 64,
            "map_ack_sha256": "b" * 64,
            "pinvi_source_revision": PINVI_REVISION,
            "runner_exit_code": 0,
            "server_side_ack_verified": True,
            "status": "passed",
        },
    )
    _write_json(
        evidence_dir / "restore.json",
        {
            "dump_sha256": "c" * 64,
            "no_owner_restore": True,
            "restore_command": "pg_restore --no-owner --no-privileges",
            "runtime_role_verified": True,
            "source_db_identity_sha256": "d" * 64,
            "status": "passed",
            "target_db_identity_sha256": "e" * 64,
            "trigger_guard_verified": True,
        },
    )
    _write_json(
        evidence_dir / "map-pair.json",
        {
            "admin_image_digest": "sha256:" + "4" * 64,
            "api_image_digest": "sha256:" + "5" * 64,
            "frontend_image_digest": "sha256:" + "6" * 64,
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
        },
    )
    _write_json(
        evidence_dir / "pinvi-images.json",
        {
            name: {
                "digest": digest,
                "environment": "production",
                "source_revision": PINVI_REVISION,
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
            "1",
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
