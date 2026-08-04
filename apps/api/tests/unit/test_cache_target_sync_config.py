"""cache target network gate와 역할별 principal 설정 불변식."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import (
    CACHE_TARGET_SERVICE_CONTRACT_GENERATION,
    CACHE_TARGET_SERVICE_FUNCTIONAL_OWNER_REVISION,
    CACHE_TARGET_SERVICE_OPENAPI_SHA256,
    Settings,
)

COMMAND = "c" * 32
CONSUMER = "u" * 32
RESTORE = "r" * 32
RECOVERY = "v" * 32
ROLE_FIELDS = (
    "pinvi_kor_travel_map_cache_target_command_token",
    "pinvi_kor_travel_map_cache_target_consumer_token",
    "pinvi_kor_travel_map_cache_target_restore_fence_token",
    "pinvi_kor_travel_map_cache_target_recovery_token",
)


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, pinvi_environment="test", **overrides)  # type: ignore[arg-type]


def test_cache_target_network_is_default_off_without_credentials() -> None:
    loaded = _settings()

    assert loaded.pinvi_kor_travel_map_cache_target_sync_enabled is False
    assert loaded.pinvi_kor_travel_map_cache_target_command_token is None
    assert loaded.pinvi_kor_travel_map_cache_target_consumer_token is None


@pytest.mark.parametrize("value", (float("nan"), float("inf"), float("-inf"), 0.0, -1.0))
@pytest.mark.parametrize(
    "field",
    (
        "pinvi_kor_travel_map_timeout_seconds",
        "pinvi_kor_travel_map_cache_target_poll_seconds",
    ),
)
def test_cache_target_timeout_config_rejects_non_finite_or_non_positive_values(
    field: str,
    value: float,
) -> None:
    with pytest.raises(ValidationError):
        _settings(**{field: value})


def test_enabled_cache_target_sync_requires_runtime_pair_and_contract_pins() -> None:
    with pytest.raises(ValidationError, match="COMMAND_TOKEN"):
        _settings(pinvi_kor_travel_map_cache_target_sync_enabled=True)

    with pytest.raises(ValidationError, match="EXPECTED_OPENAPI_SHA256"):
        _settings(
            pinvi_kor_travel_map_cache_target_sync_enabled=True,
            pinvi_kor_travel_map_cache_target_command_token=COMMAND,
            pinvi_kor_travel_map_cache_target_consumer_token=CONSUMER,
        )


def test_enabled_cache_target_sync_accepts_only_exact_vendored_service_pin() -> None:
    loaded = _settings(
        pinvi_kor_travel_map_cache_target_sync_enabled=True,
        pinvi_kor_travel_map_cache_target_command_token=COMMAND,
        pinvi_kor_travel_map_cache_target_consumer_token=CONSUMER,
        pinvi_kor_travel_map_cache_target_expected_openapi_sha256=(
            CACHE_TARGET_SERVICE_OPENAPI_SHA256
        ),
        pinvi_kor_travel_map_cache_target_expected_source_revision=(
            CACHE_TARGET_SERVICE_FUNCTIONAL_OWNER_REVISION
        ),
        pinvi_kor_travel_map_cache_target_expected_contract_generation=(
            CACHE_TARGET_SERVICE_CONTRACT_GENERATION
        ),
    )

    assert loaded.pinvi_kor_travel_map_cache_target_sync_enabled is True

    with pytest.raises(ValidationError, match="must match the vendored service contract"):
        _settings(
            pinvi_kor_travel_map_cache_target_sync_enabled=True,
            pinvi_kor_travel_map_cache_target_command_token=COMMAND,
            pinvi_kor_travel_map_cache_target_consumer_token=CONSUMER,
            pinvi_kor_travel_map_cache_target_expected_openapi_sha256="a" * 64,
            pinvi_kor_travel_map_cache_target_expected_source_revision=(
                CACHE_TARGET_SERVICE_FUNCTIONAL_OWNER_REVISION
            ),
            pinvi_kor_travel_map_cache_target_expected_contract_generation=(
                CACHE_TARGET_SERVICE_CONTRACT_GENERATION
            ),
        )


def test_generation6_manifest_is_not_a_compatible_fallback() -> None:
    with pytest.raises(ValidationError, match="EXPECTED_CONTRACT_GENERATION"):
        _settings(
            pinvi_kor_travel_map_cache_target_sync_enabled=True,
            pinvi_kor_travel_map_cache_target_command_token=COMMAND,
            pinvi_kor_travel_map_cache_target_consumer_token=CONSUMER,
            pinvi_kor_travel_map_cache_target_expected_openapi_sha256=(
                CACHE_TARGET_SERVICE_OPENAPI_SHA256
            ),
            pinvi_kor_travel_map_cache_target_expected_source_revision=(
                CACHE_TARGET_SERVICE_FUNCTIONAL_OWNER_REVISION
            ),
            pinvi_kor_travel_map_cache_target_expected_contract_generation=6,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "pinvi_kor_travel_map_cache_target_command_token": COMMAND,
            "pinvi_kor_travel_map_cache_target_consumer_token": COMMAND,
        },
        {
            "pinvi_kor_travel_map_cache_target_command_token": COMMAND,
            "pinvi_kor_travel_map_cache_target_consumer_token": CONSUMER,
            "pinvi_kor_travel_map_cache_target_restore_fence_token": CONSUMER,
        },
        {
            "pinvi_kor_travel_map_cache_target_command_token": COMMAND,
            "pinvi_kor_travel_map_cache_target_consumer_token": CONSUMER,
            "pinvi_kor_travel_map_cache_target_recovery_token": "weak",
        },
        {
            "pinvi_kor_travel_map_service_token": COMMAND,
            "pinvi_kor_travel_map_cache_target_command_token": COMMAND,
        },
    ],
)
def test_cache_target_roles_reject_weak_reused_or_legacy_credentials(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _settings(**overrides)


def test_cache_target_role_credentials_are_distinct_and_restore_recovery_optional() -> None:
    loaded = _settings(
        pinvi_kor_travel_map_cache_target_command_token=COMMAND,
        pinvi_kor_travel_map_cache_target_consumer_token=CONSUMER,
        pinvi_kor_travel_map_cache_target_restore_fence_token=RESTORE,
        pinvi_kor_travel_map_cache_target_recovery_token=RECOVERY,
    )

    assert loaded.pinvi_kor_travel_map_cache_target_restore_fence_token is not None
    assert loaded.pinvi_kor_travel_map_cache_target_recovery_token is not None


@pytest.mark.parametrize("role_field", ROLE_FIELDS)
@pytest.mark.parametrize(
    "protected_credentials",
    [
        {"pinvi_kor_travel_map_public_api_key": COMMAND},
        {"pinvi_vworld_api_key": COMMAND},
        {
            "pinvi_kor_travel_map_public_api_key": "p" * 32,
            "pinvi_vworld_api_key": COMMAND,
        },
        {"pinvi_kor_travel_map_admin_proxy_secret": COMMAND},
        {"pinvi_kor_travel_map_service_token": COMMAND},
        {"pinvi_kor_travel_map_admin_service_token": COMMAND},
        {
            "pinvi_kor_travel_map_ops_read_token": COMMAND,
            "pinvi_kor_travel_map_ops_cancel_token": "z" * 32,
        },
        {
            "pinvi_kor_travel_map_ops_read_token": "o" * 32,
            "pinvi_kor_travel_map_ops_cancel_token": COMMAND,
        },
    ],
    ids=(
        "explicit-public",
        "vworld-fallback",
        "vworld-exposed",
        "admin-proxy",
        "service",
        "admin-service",
        "ops-read",
        "ops-cancel",
    ),
)
def test_each_cache_target_role_rejects_protected_map_credential_reuse(
    role_field: str,
    protected_credentials: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="trust-boundary credential"):
        _settings(**{role_field: COMMAND}, **protected_credentials)


def test_all_cache_target_roles_accept_distinct_map_boundary_credentials() -> None:
    loaded = _settings(
        pinvi_kor_travel_map_cache_target_command_token=COMMAND,
        pinvi_kor_travel_map_cache_target_consumer_token=CONSUMER,
        pinvi_kor_travel_map_cache_target_restore_fence_token=RESTORE,
        pinvi_kor_travel_map_cache_target_recovery_token=RECOVERY,
        pinvi_kor_travel_map_service_token="s" * 32,
        pinvi_kor_travel_map_admin_service_token="a" * 32,
        pinvi_kor_travel_map_admin_proxy_secret="x" * 32,
        pinvi_kor_travel_map_public_api_key="p" * 32,
        pinvi_vworld_api_key="w" * 32,
        pinvi_kor_travel_map_ops_read_token="o" * 32,
        pinvi_kor_travel_map_ops_cancel_token="z" * 32,
    )

    assert loaded.pinvi_kor_travel_map_cache_target_command_token is not None


def test_ordinary_api_manifest_passes_only_command_and_consumer_roles() -> None:
    root = Path(__file__).resolve().parents[4]
    compose = (root / "infra/docker-compose.app.yml").read_text(encoding="utf-8")
    api_block, web_block = compose.split("  app-web:", maxsplit=1)

    for env_name in (
        "PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_COMMAND_TOKEN",
        "PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_CONSUMER_TOKEN",
    ):
        assert env_name in api_block
        assert env_name not in web_block
    for env_name in (
        "PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_RESTORE_FENCE_TOKEN",
        "PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_RECOVERY_TOKEN",
    ):
        assert env_name not in compose
