"""M05 paired consumer의 default-off credential/pin config gate."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import (
    KOR_TRAVEL_MAP_SERVICE_OPENAPI_SHA256,
    KOR_TRAVEL_MAP_SERVICE_RELEASE_REVISION,
    Settings,
)

READ = "r" * 32
ACK = "a" * 32


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, pinvi_environment="test", **overrides)  # type: ignore[arg-type]


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
        {"pinvi_kor_travel_map_feature_request_token": READ},
        {"pinvi_kor_travel_map_cache_target_consumer_token": READ},
        {"pinvi_kor_travel_map_service_token": READ},
    ),
)
def test_reconciliation_tokens_cannot_reuse_other_map_boundary(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match=r"must differ|must not reuse"):
        _settings(**{**_enabled_values(), **overrides})


def test_production_reconciliation_enable_is_forbidden_before_paired_gate() -> None:
    loaded = _settings(**_enabled_values())
    with pytest.raises(ValueError, match="forbidden in production"):
        loaded.model_copy(
            update={"pinvi_environment": "production"}
        ).validate_feature_reference_reconciliation()


def test_compose_and_examples_keep_m05_credentials_api_only_and_default_off() -> None:
    root = Path(__file__).resolve().parents[4]
    compose = (root / "infra/docker-compose.app.yml").read_text(encoding="utf-8")
    prod = (root / "infra/.env.prod.example").read_text(encoding="utf-8")
    example = (root / ".env.example").read_text(encoding="utf-8")
    for variable in (
        "PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_READ_TOKEN",
        "PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ACK_TOKEN",
    ):
        assert variable in compose
        assert f"{variable}=" in prod
        assert f"{variable}=" in example
    assert "PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ENABLED=false" in prod
    assert "PINVI_KOR_TRAVEL_MAP_FEATURE_REFERENCE_RECONCILIATION_ENABLED=false" in example
