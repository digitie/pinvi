"""M05 paired consumer의 default-off credential/pin config gate."""

from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

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
PUBLIC_KEY_PRIVATE = Ed25519PrivateKey.from_private_bytes(b"m05-ed25519-private-key-32bytes!")
PUBLIC_KEY = (
    base64.urlsafe_b64encode(PUBLIC_KEY_PRIVATE.public_key().public_bytes_raw())
    .decode("ascii")
    .rstrip("=")
)
TEST_TRUST_ANCHOR_SHA256 = hashlib.sha256(
    PUBLIC_KEY_PRIVATE.public_key().public_bytes_raw()
).hexdigest()
IMAGE_DIGESTS = {
    "pinvi_api_image_digest": "sha256:" + "1" * 64,
    "pinvi_web_image_digest": "sha256:" + "2" * 64,
    "pinvi_dagster_image_digest": "sha256:" + "3" * 64,
}


@pytest.fixture(autouse=True)
def _use_test_activation_trust_anchor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        config_module,
        "PINVI_M05_ACTIVATION_RECEIPT_PUBLIC_KEY_SHA256",
        TEST_TRUST_ANCHOR_SHA256,
    )


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, pinvi_environment="test", **overrides)  # type: ignore[arg-type]


def _production_settings(**overrides: object) -> Settings:
    receipt = overrides.get(
        "pinvi_kor_travel_map_feature_reference_reconciliation_activation_receipt"
    )
    if isinstance(receipt, str) and receipt.startswith("{"):
        try:
            payload = json.loads(receipt)["payload"]
        except (KeyError, TypeError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict):
            ledger_dir = tempfile.TemporaryDirectory(prefix="pinvi-m05-ledger-", dir="/tmp")
            ledger_path = Path(ledger_dir.name) / "activation-ledger.jsonl"
            ledger_path.write_text(
                json.dumps(
                    {
                        "activation_expires_at": payload["activation_expires_at"],
                        "activation_generation": payload["activation_generation"],
                        "activation_issued_at": payload["activation_issued_at"],
                        "activation_nonce": payload["activation_nonce"],
                        "receipt_sha256": hashlib.sha256(receipt.encode()).hexdigest(),
                        "scope": payload["scope"],
                        "source_revision": payload["pinvi_source_revision"],
                    },
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            ledger_path.chmod(0o600)
            overrides["pinvi_m05_activation_ledger_path"] = str(ledger_path)
            loaded = Settings(_env_file=None, pinvi_environment="production", **overrides)  # type: ignore[arg-type]
            ledger_dir.cleanup()
            return loaded
    return Settings(_env_file=None, pinvi_environment="production", **overrides)  # type: ignore[arg-type]


def _receipt_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "activation_expires_at": int(time.time()) + 3600,
        "activation_generation": 1,
        "activation_issued_at": int(time.time()) - 60,
        "activation_nonce": "22222222-2222-4222-8222-222222222222",
        "adversarial_reviews": [
            {"commit": "1" * 40, "p0_p1": 0, "review_id": "review-1", "reviewer_id": "darwin"},
            {"commit": "2" * 40, "p0_p1": 0, "review_id": "review-2", "reviewer_id": "feynman"},
        ],
        "live_ui_e2e": "passed",
        "live_ui_event_id": "11111111-1111-4111-8111-111111111111",
        "live_ui_evidence_sha256": "a" * 64,
        "live_ui_map_ack_sha256": "b" * 64,
        "map_admin_openapi_sha256": KOR_TRAVEL_MAP_M05_ADMIN_OPENAPI_SHA256,
        "map_admin_source_revision": KOR_TRAVEL_MAP_M05_ADMIN_SOURCE_REVISION,
        "map_admin_image_digest": "sha256:" + "4" * 64,
        "map_api_image_digest": "sha256:" + "5" * 64,
        "map_frontend_image_digest": "sha256:" + "6" * 64,
        "map_full_openapi_sha256": KOR_TRAVEL_MAP_M05_FULL_OPENAPI_SHA256,
        "map_full_source_revision": KOR_TRAVEL_MAP_M05_FULL_SOURCE_REVISION,
        "map_pair_evidence_sha256": "c" * 64,
        "map_service_openapi_sha256": KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256,
        "map_service_source_revision": KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
        "map_user_openapi_sha256": KOR_TRAVEL_MAP_M05_USER_OPENAPI_SHA256,
        "map_user_source_revision": KOR_TRAVEL_MAP_M05_USER_SOURCE_REVISION,
        "pinvi_api_image_digest": IMAGE_DIGESTS["pinvi_api_image_digest"],
        "pinvi_dagster_image_digest": IMAGE_DIGESTS["pinvi_dagster_image_digest"],
        "pinvi_image_evidence_sha256": "d" * 64,
        "pinvi_source_revision": PINVI_REVISION,
        "pinvi_web_image_digest": IMAGE_DIGESTS["pinvi_web_image_digest"],
        "restore_drill": "passed",
        "restore_evidence_sha256": "e" * 64,
        "review_evidence_sha256": "f" * 64,
        "scope": "production",
        "version": 1,
    }
    payload.update(overrides)
    return payload


def _signed_receipt(payload: dict[str, object]) -> str:
    material = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    signature = base64.urlsafe_b64encode(PUBLIC_KEY_PRIVATE.sign(material.encode("utf-8")))
    return json.dumps(
        {"payload": payload, "signature": signature.decode("ascii").rstrip("=")},
        separators=(",", ":"),
    )


def _production_activation_values(receipt: str) -> dict[str, object]:
    return {
        "pinvi_kor_travel_map_feature_reference_reconciliation_activation_receipt": receipt,
        "pinvi_kor_travel_map_feature_reference_reconciliation_activation_receipt_public_key": PUBLIC_KEY,
        **IMAGE_DIGESTS,
    }


def _enabled_values() -> dict[str, object]:
    return {
        "pinvi_kor_travel_map_feature_reference_reconciliation_enabled": True,
        "pinvi_kor_travel_map_feature_reference_reconciliation_read_token": READ,
        "pinvi_kor_travel_map_feature_reference_reconciliation_ack_token": ACK,
        "pinvi_kor_travel_map_feature_reference_reconciliation_expected_openapi_sha256": (
            KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256
        ),
        "pinvi_kor_travel_map_feature_reference_reconciliation_expected_source_revision": (
            KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION
        ),
    }


def test_reconciliation_network_is_default_off_and_empty_tokens_are_unset() -> None:
    loaded = _settings(
        pinvi_kor_travel_map_feature_reference_reconciliation_read_token="",
        pinvi_kor_travel_map_feature_reference_reconciliation_ack_token="",
    )
    assert loaded.pinvi_kor_travel_map_feature_reference_reconciliation_enabled is False
    assert loaded.pinvi_kor_travel_map_feature_reference_reconciliation_read_token is None
    assert loaded.pinvi_kor_travel_map_feature_reference_reconciliation_ack_token is None
    assert (
        loaded.pinvi_kor_travel_map_feature_reference_reconciliation_blocked_recheck_seconds == 30
    )


@pytest.mark.parametrize("value", (0, 0.9, 3600.1, float("inf"), float("nan")))
def test_reconciliation_blocked_recheck_is_finite_bounded(value: float) -> None:
    with pytest.raises(ValidationError):
        _settings(
            pinvi_kor_travel_map_feature_reference_reconciliation_blocked_recheck_seconds=value
        )


def test_enabled_reconciliation_requires_distinct_credentials_and_exact_vendor_pin() -> None:
    with pytest.raises(ValidationError, match="READ_TOKEN"):
        _settings(pinvi_kor_travel_map_feature_reference_reconciliation_enabled=True)
    with pytest.raises(ValidationError, match="scoped Map service tokens must differ"):
        _settings(
            **{
                **_enabled_values(),
                "pinvi_kor_travel_map_feature_reference_reconciliation_ack_token": READ,
            },
        )
    with pytest.raises(ValidationError, match="must match the vendored service contract"):
        _settings(
            **{
                **_enabled_values(),
                "pinvi_kor_travel_map_feature_reference_reconciliation_expected_openapi_sha256": "b"
                * 64,
            },
        )
    assert _settings(
        **_enabled_values()
    ).pinvi_kor_travel_map_feature_reference_reconciliation_enabled


@pytest.mark.parametrize(
    "overrides",
    (
        {"kor_travel_map_feature_request_token": READ},
        {"pinvi_kor_travel_map_cache_target_consumer_token": READ},
        {"pinvi_kor_travel_map_service_token": READ},
    ),
)
def test_reconciliation_tokens_cannot_reuse_other_map_boundary(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match=r"must differ|must not reuse"):
        _settings(**{**_enabled_values(), **overrides})


def test_production_reconciliation_enable_requires_activation_receipt() -> None:
    with pytest.raises(ValueError, match=r"ACTIVATION_RECEIPT.*required"):
        _production_settings(
            pinvi_kor_travel_map_api_base_url="http://127.0.0.1:12701",
            pinvi_kor_travel_map_admin_base_url="http://127.0.0.1:12701",
            pinvi_kor_travel_map_ops_read_token="o" * 32,
            pinvi_kor_travel_map_ops_cancel_token="c" * 32,
            **_enabled_values(),
        )


def test_production_reconciliation_accepts_current_paired_activation_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PINVI_SOURCE_REVISION", PINVI_REVISION)
    loaded = _production_settings(
        pinvi_kor_travel_map_api_base_url="http://127.0.0.1:12701",
        pinvi_kor_travel_map_admin_base_url="http://127.0.0.1:12701",
        pinvi_kor_travel_map_ops_read_token="o" * 32,
        pinvi_kor_travel_map_ops_cancel_token="c" * 32,
        **_production_activation_values(_signed_receipt(_receipt_payload())),
        **_enabled_values(),
    )
    assert loaded.pinvi_kor_travel_map_feature_reference_reconciliation_enabled is True


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("live_ui_e2e", "skipped", "live UI E2E"),
        ("map_service_source_revision", "0" * 40, "Map pair"),
        ("pinvi_source_revision", "0" * 40, "Pinvi source revision"),
        ("pinvi_api_image_digest", "sha256:" + "0" * 64, "image digest"),
    ),
)
def test_production_reconciliation_rejects_stale_activation_receipt(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
    message: str,
) -> None:
    monkeypatch.setenv("PINVI_SOURCE_REVISION", PINVI_REVISION)
    receipt = _receipt_payload(**{field: value})
    with pytest.raises(ValueError, match=message):
        _production_settings(
            pinvi_kor_travel_map_api_base_url="http://127.0.0.1:12701",
            pinvi_kor_travel_map_admin_base_url="http://127.0.0.1:12701",
            pinvi_kor_travel_map_ops_read_token="o" * 32,
            pinvi_kor_travel_map_ops_cancel_token="c" * 32,
            **_production_activation_values(_signed_receipt(receipt)),
            **_enabled_values(),
        )


def test_production_reconciliation_rejects_receipt_secret_leaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "UNIQUE-M05-ACTIVATION-RECEIPT-SECRET"
    with pytest.raises(ValidationError) as captured:
        _production_settings(
            pinvi_kor_travel_map_api_base_url="http://127.0.0.1:12701",
            pinvi_kor_travel_map_admin_base_url="http://127.0.0.1:12701",
            pinvi_kor_travel_map_ops_read_token="o" * 32,
            pinvi_kor_travel_map_ops_cancel_token="c" * 32,
            **_production_activation_values(secret),
            **_enabled_values(),
        )
    assert secret not in repr(captured.value.errors())
    assert secret not in str(captured.value)


def test_scoped_token_validation_errors_redact_secret_input() -> None:
    secret = "UNIQUE-SCOPED-TOKEN-TO-REDACT"
    with pytest.raises(ValidationError) as captured:
        _settings(
            **{
                **_enabled_values(),
                "pinvi_kor_travel_map_feature_reference_reconciliation_read_token": secret,
            }
        )
    assert secret not in repr(captured.value.errors())
    assert secret not in str(captured.value)


@pytest.mark.parametrize(
    "field",
    ("version", "scope"),
)
def test_production_reconciliation_rejects_boolean_numeric_receipt_fields(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    monkeypatch.setenv("PINVI_SOURCE_REVISION", PINVI_REVISION)
    receipt = _receipt_payload(**{field: True})
    with pytest.raises(ValueError, match=r"M05 activation|production v1"):
        _production_settings(
            pinvi_kor_travel_map_api_base_url="http://127.0.0.1:12701",
            pinvi_kor_travel_map_admin_base_url="http://127.0.0.1:12701",
            pinvi_kor_travel_map_ops_read_token="o" * 32,
            pinvi_kor_travel_map_ops_cancel_token="c" * 32,
            **_production_activation_values(_signed_receipt(receipt)),
            **_enabled_values(),
        )


def test_production_reconciliation_rejects_duplicate_receipt_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PINVI_SOURCE_REVISION", PINVI_REVISION)
    receipt = _signed_receipt(_receipt_payload()).replace('"version":1', '"version":1,"version":1')
    with pytest.raises(ValueError, match="duplicate keys"):
        _production_settings(
            pinvi_kor_travel_map_api_base_url="http://127.0.0.1:12701",
            pinvi_kor_travel_map_admin_base_url="http://127.0.0.1:12701",
            pinvi_kor_travel_map_ops_read_token="o" * 32,
            pinvi_kor_travel_map_ops_cancel_token="c" * 32,
            **_production_activation_values(receipt),
            **_enabled_values(),
        )


def test_production_reconciliation_rejects_invalid_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PINVI_SOURCE_REVISION", PINVI_REVISION)
    receipt = _receipt_payload()
    broken = json.loads(_signed_receipt(receipt))
    broken["signature"] = "A" * 86
    with pytest.raises(ValueError, match="signature is invalid"):
        _production_settings(
            pinvi_kor_travel_map_api_base_url="http://127.0.0.1:12701",
            pinvi_kor_travel_map_admin_base_url="http://127.0.0.1:12701",
            pinvi_kor_travel_map_ops_read_token="o" * 32,
            pinvi_kor_travel_map_ops_cancel_token="c" * 32,
            **_production_activation_values(json.dumps(broken, separators=(",", ":"))),
            **_enabled_values(),
        )


def test_compose_and_examples_keep_m05_credentials_api_only_and_default_off() -> None:
    root = Path(__file__).resolve().parents[4]
    compose = (root / "infra/docker-compose.app.yml").read_text(encoding="utf-8")
    prod = (root / "infra/.env.prod.example").read_text(encoding="utf-8")
    example = (root / ".env.example").read_text(encoding="utf-8")
    for variable in (
        "PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_READ_TOKEN",
        "PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ACK_TOKEN",
        "PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_BLOCKED_RECHECK_SECONDS",
        "PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ACTIVATION_RECEIPT",
        "PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ACTIVATION_RECEIPT_PUBLIC_KEY",
        "PINVI_API_IMAGE_DIGEST",
        "PINVI_WEB_IMAGE_DIGEST",
        "PINVI_DAGSTER_IMAGE_DIGEST",
    ):
        assert variable in compose
        assert f"{variable}=" in prod
        assert f"{variable}=" in example
    assert "PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ENABLED=false" in prod
    assert "PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ENABLED=false" in example

    api_block = compose.split("  app-api:", maxsplit=1)[1].split("  app-migrator:", maxsplit=1)[0]
    for service_start, service_end in (
        ("  app-migrator:", "  app-web:"),
        ("  app-web:", "  app-dagster:"),
        ("  app-dagster:", "  cadvisor:"),
    ):
        service_block = compose.split(service_start, maxsplit=1)[1].split(service_end, maxsplit=1)[
            0
        ]
        for variable in (
            "PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ACTIVATION_RECEIPT",
            "PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ACTIVATION_RECEIPT_PUBLIC_KEY",
            "PINVI_API_IMAGE_DIGEST",
            "PINVI_WEB_IMAGE_DIGEST",
            "PINVI_DAGSTER_IMAGE_DIGEST",
        ):
            assert variable not in service_block
    assert "PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ACTIVATION_RECEIPT" in api_block
    assert "kor-travel-map-m05-pair-provenance-v1.json" in (root / "apps/api/Dockerfile").read_text(
        encoding="utf-8"
    )


def test_m05_evidence_runtime_uses_non_owner_database_login() -> None:
    root = Path(__file__).resolve().parents[4]
    compose = (root / "infra/docker-compose.app.yml").read_text(encoding="utf-8")
    bootstrap = (root / "infra/postgres/bootstrap-pinvi-runtime-role.sh").read_text(
        encoding="utf-8"
    )
    docker_app = (root / "scripts/docker-app.sh").read_text(encoding="utf-8")
    deploy = (root / "scripts/deploy-node.sh").read_text(encoding="utf-8")
    api_block, _ = compose.split("  app-migrator:", maxsplit=1)

    assert "app-db-runtime-role:" in compose
    assert "PINVI_DATABASE_URL: ${PINVI_DATABASE_URL:-postgresql+asyncpg://pinvi_app:" in api_block
    assert "PINVI_MIGRATOR_DATABASE_URL" in compose
    assert "app-migrator pinvi-admin-bootstrap" in docker_app
    assert "app-migrator pinvi-admin-bootstrap" in deploy
    assert "compose run --rm app-db-runtime-role" in docker_app
    assert "compose run --rm app-db-runtime-role" in deploy
    assert "NOSUPERUSER" in bootstrap
    assert "NOINHERIT" in bootstrap
    assert "ALTER DEFAULT PRIVILEGES" in bootstrap
    assert "until psql --no-password --tuples-only --no-align --host=app-postgres" in bootstrap
    assert "--command='SELECT 1'" in bootstrap
    assert '[ "$attempt" -ge 15 ]' in bootstrap
    assert "FROM pg_auth_members m" in bootstrap
    assert "WHERE m.member = r.oid" in bootstrap
    assert "CREATE SCHEMA IF NOT EXISTS x_extension AUTHORIZATION" in bootstrap
    assert "ALTER SCHEMA x_extension OWNER TO" in bootstrap
    assert "REVOKE ALL ON SCHEMA x_extension FROM PUBLIC;" in bootstrap
    assert 'GRANT USAGE ON SCHEMA x_extension TO :"app_role";' in bootstrap
    assert "n.nspname IN ('app', 'x_extension')" in bootstrap
    assert "has_schema_privilege(r.oid, n.oid, 'CREATE')" in bootstrap
    assert "FROM pg_proc p" in bootstrap
    assert "FROM pg_type t" in bootstrap
    assert "FROM pg_extension e" in bootstrap
    assert "e.extowner = r.oid" in bootstrap
    assert "c.relowner = r.oid" in bootstrap
    assert "n.nspowner = r.oid" in bootstrap
    assert "pg_has_role(r.oid, n.nspowner, 'member')" in bootstrap
