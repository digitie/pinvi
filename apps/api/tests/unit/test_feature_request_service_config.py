"""Feature 요청 writer principal은 다른 Map credential과 분리돼야 한다."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_TOKEN = "f" * 32
_OTHER = "g" * 32


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, pinvi_environment="test", **overrides)  # type: ignore[arg-type]


def test_feature_request_token_is_optional_and_empty_is_unset() -> None:
    assert _settings().pinvi_kor_travel_map_feature_request_token is None
    assert _settings(pinvi_kor_travel_map_feature_request_token="").pinvi_kor_travel_map_feature_request_token is None


@pytest.mark.parametrize(
    "value",
    ["short", "x" * 31, "x" * 31 + " "],
)
def test_feature_request_token_requires_a_strong_no_whitespace_value(value: str) -> None:
    with pytest.raises(ValidationError, match="FEATURE_REQUEST_TOKEN"):
        _settings(pinvi_kor_travel_map_feature_request_token=value)


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"pinvi_kor_travel_map_service_token": _TOKEN}, "must not reuse"),
        ({"pinvi_kor_travel_map_admin_service_token": _TOKEN}, "must not reuse"),
        ({"pinvi_kor_travel_map_admin_proxy_secret": _TOKEN}, "must not reuse"),
        (
            {
                "pinvi_kor_travel_map_ops_read_token": _TOKEN,
                "pinvi_kor_travel_map_ops_cancel_token": _OTHER,
            },
            "must not reuse",
        ),
        ({"pinvi_kor_travel_map_curation_snapshot_token": _TOKEN}, "must differ"),
        ({"pinvi_kor_travel_map_cache_target_command_token": _TOKEN}, "must not reuse"),
    ],
)
def test_feature_request_token_cannot_reuse_other_map_trust_boundary(
    overrides: dict[str, str], error: str
) -> None:
    with pytest.raises(ValidationError, match=error):
        _settings(pinvi_kor_travel_map_feature_request_token=_TOKEN, **overrides)


def test_feature_request_token_accepts_a_distinct_credential() -> None:
    loaded = _settings(
        pinvi_kor_travel_map_feature_request_token=_TOKEN,
        pinvi_kor_travel_map_curation_snapshot_token=_OTHER,
    )
    assert loaded.pinvi_kor_travel_map_feature_request_token is not None
