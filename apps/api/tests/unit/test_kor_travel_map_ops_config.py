"""kor-travel-map canonical ops 운영 설정의 fail-closed 계약 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_READ_TOKEN = "r" * 32
_CANCEL_TOKEN = "c" * 32


def _production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "pinvi_environment": "production",
        "pinvi_kor_travel_map_admin_base_url": "http://host.docker.internal:12701",
        "pinvi_kor_travel_map_ops_read_token": _READ_TOKEN,
        "pinvi_kor_travel_map_ops_cancel_token": _CANCEL_TOKEN,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "base_url",
    [
        "http://host.docker.internal:12701",
        "http://127.0.0.1:12701",
        "https://host.docker.internal:12701/",
        "https://127.0.0.1:12701/",
    ],
)
def test_production_accepts_distinct_strong_ops_tokens_and_supported_base_url(
    base_url: str,
) -> None:
    loaded = _production_settings(pinvi_kor_travel_map_admin_base_url=base_url)

    assert loaded.pinvi_kor_travel_map_ops_read_token is not None
    assert loaded.pinvi_kor_travel_map_ops_cancel_token is not None
    assert _READ_TOKEN not in repr(loaded)
    assert _CANCEL_TOKEN not in repr(loaded)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"pinvi_kor_travel_map_ops_read_token": None}, "OPS_READ_TOKEN"),
        ({"pinvi_kor_travel_map_ops_cancel_token": "short"}, "OPS_CANCEL_TOKEN"),
        (
            {"pinvi_kor_travel_map_ops_read_token": f"{_READ_TOKEN} "},
            "must not contain whitespace",
        ),
        (
            {"pinvi_kor_travel_map_ops_cancel_token": f" {_CANCEL_TOKEN}"},
            "must not contain whitespace",
        ),
        (
            {"pinvi_kor_travel_map_ops_read_token": f"{'r' * 16}\u2003{'r' * 16}"},
            "must not contain whitespace",
        ),
        ({"pinvi_kor_travel_map_ops_cancel_token": _READ_TOKEN}, "must differ"),
        (
            {"pinvi_kor_travel_map_admin_base_url": "ftp://map.internal:12701"},
            "allowed root HTTP",
        ),
        (
            {"pinvi_kor_travel_map_admin_base_url": "map.internal:12701"},
            "allowed root HTTP",
        ),
        (
            {"pinvi_kor_travel_map_admin_base_url": "http:///missing-host"},
            "allowed root HTTP",
        ),
        (
            {"pinvi_kor_travel_map_admin_base_url": ("http://operator:password@127.0.0.1:12701")},
            "allowed root HTTP",
        ),
        (
            {"pinvi_kor_travel_map_admin_base_url": "http://127.0.0.1:12701?mode=ops"},
            "allowed root HTTP",
        ),
        (
            {"pinvi_kor_travel_map_admin_base_url": "http://127.0.0.1:12701#ops"},
            "allowed root HTTP",
        ),
        (
            {"pinvi_kor_travel_map_admin_base_url": "http://map.internal:12701"},
            "allowed root HTTP",
        ),
        (
            {"pinvi_kor_travel_map_admin_base_url": "http://127.0.0.1:12702"},
            "allowed root HTTP",
        ),
        (
            {"pinvi_kor_travel_map_admin_base_url": "http://127.0.0.1:12701/v1/ops"},
            "allowed root HTTP",
        ),
    ],
)
def test_production_rejects_unsafe_ops_configuration(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        _production_settings(**overrides)


@pytest.mark.parametrize(
    "environment",
    ["prod", " production", "production ", "PRODUCTION", "local", "unknown", ""],
)
def test_environment_rejects_alias_whitespace_and_unknown_values(environment: str) -> None:
    with pytest.raises(ValidationError, match="pinvi_environment"):
        Settings(_env_file=None, pinvi_environment=environment)  # type: ignore[arg-type]


@pytest.mark.parametrize("environment", ["development", "test", "smoke", "staging"])
def test_non_production_allows_only_both_empty_ops_tokens(environment: str) -> None:
    loaded = Settings(_env_file=None, pinvi_environment=environment)  # type: ignore[arg-type]

    assert loaded.pinvi_kor_travel_map_ops_read_token is None
    assert loaded.pinvi_kor_travel_map_ops_cancel_token is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"pinvi_kor_travel_map_ops_read_token": _READ_TOKEN},
        {"pinvi_kor_travel_map_ops_cancel_token": _CANCEL_TOKEN},
        {
            "pinvi_kor_travel_map_ops_read_token": _READ_TOKEN,
            "pinvi_kor_travel_map_ops_cancel_token": "c" * 31,
        },
        {
            "pinvi_kor_travel_map_ops_read_token": _READ_TOKEN,
            "pinvi_kor_travel_map_ops_cancel_token": f"{'c' * 16}\u2003{'c' * 16}",
        },
        {
            "pinvi_kor_travel_map_ops_read_token": _READ_TOKEN,
            "pinvi_kor_travel_map_ops_cancel_token": _READ_TOKEN,
        },
    ],
)
def test_non_production_rejects_partial_or_weak_ops_tokens(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, pinvi_environment="development", **overrides)  # type: ignore[arg-type]


def test_deploy_compose_passes_dual_ops_credentials_to_api_only() -> None:
    root = Path(__file__).resolve().parents[4]
    compose = (root / "infra/docker-compose.app.yml").read_text(encoding="utf-8")
    prod_example = (root / "infra/.env.prod.example").read_text(encoding="utf-8")

    api_block, web_block = compose.split("  app-web:", maxsplit=1)
    for env_name in (
        "PINVI_KOR_TRAVEL_MAP_ADMIN_BASE_URL",
        "PINVI_KOR_TRAVEL_MAP_OPS_READ_TOKEN",
        "PINVI_KOR_TRAVEL_MAP_OPS_CANCEL_TOKEN",
    ):
        assert env_name in api_block
        assert env_name in prod_example
        assert env_name not in web_block
    assert "PINVI_KOR_TRAVEL_MAP_OPS_TOKEN" not in compose
    assert "PINVI_KOR_TRAVEL_MAP_OPS_TOKEN" not in prod_example
