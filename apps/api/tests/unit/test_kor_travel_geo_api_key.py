"""kor-travel-geo client는 geo 전용 key만 보낸다(ADR-075, ADR-048 대체).

운영 geo는 `ops.public_api_keys`의 발급 key만 받는다(VWorld key는 그 표가 빌 때의 기본값).
VWorld key는 모바일·브라우저에 노출되므로 geo key로 fallback하면 안 된다.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.clients.kor_travel_geo import KorTravelGeoUnavailable, create_kor_travel_geo_client
from app.core.config import Settings

GEO_KEY = "g" * 32
VWORLD_KEY = "v" * 36


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"pinvi_environment": "test"}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


async def test_geo_client_sends_dedicated_key() -> None:
    client = create_kor_travel_geo_client(
        _settings(pinvi_kor_travel_geo_api_key=GEO_KEY, pinvi_vworld_api_key=VWORLD_KEY)
    )
    try:
        assert client._auth_params() == {"key": GEO_KEY}
    finally:
        await client.aclose()


async def test_geo_client_never_falls_back_to_vworld_key() -> None:
    client = create_kor_travel_geo_client(_settings(pinvi_vworld_api_key=VWORLD_KEY))
    try:
        with pytest.raises(KorTravelGeoUnavailable):
            client._auth_params()
    finally:
        await client.aclose()


def test_geo_key_must_differ_from_vworld_key() -> None:
    with pytest.raises(ValidationError, match="must differ from PINVI_VWORLD_API_KEY"):
        _settings(pinvi_kor_travel_geo_api_key=VWORLD_KEY, pinvi_vworld_api_key=VWORLD_KEY)


def test_geo_key_rejects_whitespace() -> None:
    with pytest.raises(ValidationError, match="must not contain whitespace"):
        _settings(pinvi_kor_travel_geo_api_key="abc def")


def test_geo_key_is_not_rendered_in_settings_repr() -> None:
    assert GEO_KEY not in repr(_settings(pinvi_kor_travel_geo_api_key=GEO_KEY))


async def test_empty_geo_key_from_compose_means_unset() -> None:
    """compose `${PINVI_KOR_TRAVEL_GEO_API_KEY:-}`의 빈 값은 기동을 막지 않고 미설정으로 degrade한다."""
    client = create_kor_travel_geo_client(
        _settings(pinvi_kor_travel_geo_api_key="", pinvi_vworld_api_key=VWORLD_KEY)
    )
    try:
        with pytest.raises(KorTravelGeoUnavailable):
            client._auth_params()
    finally:
        await client.aclose()
