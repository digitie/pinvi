"""cache target network gate와 역할별 principal 설정 불변식."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import (
    CACHE_TARGET_SERVICE_ARTIFACT_OWNER_REVISION,
    CACHE_TARGET_SERVICE_CONTRACT_GENERATION,
    CACHE_TARGET_SERVICE_OPENAPI_SHA256,
    Settings,
)

COMMAND = "c" * 32
CONSUMER = "u" * 32
RESTORE = "r" * 32
RECOVERY = "v" * 32


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, pinvi_environment="test", **overrides)  # type: ignore[arg-type]


def test_cache_target_network_is_default_off_without_credentials() -> None:
    loaded = _settings()

    assert loaded.pinvi_kor_travel_map_cache_target_sync_enabled is False
    assert loaded.pinvi_kor_travel_map_cache_target_command_token is None
    assert loaded.pinvi_kor_travel_map_cache_target_consumer_token is None


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
            CACHE_TARGET_SERVICE_ARTIFACT_OWNER_REVISION
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
                CACHE_TARGET_SERVICE_ARTIFACT_OWNER_REVISION
            ),
            pinvi_kor_travel_map_cache_target_expected_contract_generation=(
                CACHE_TARGET_SERVICE_CONTRACT_GENERATION
            ),
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
