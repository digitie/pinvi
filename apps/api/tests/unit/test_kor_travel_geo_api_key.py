"""kor-travel-geo client가 geo 전용 key를 우선하고, 없을 때만 VWorld key로 fallback하는지 센다.

운영 geo는 `ops.public_api_keys`의 발급 key만 받으므로(VWorld key는 표가 빌 때의 기본값),
PinVi가 VWorld key만 보내면 모든 geo 호출이 401이다(2026-10-14 n150 실측).
"""

from __future__ import annotations

import pytest

from app.clients.kor_travel_geo import create_kor_travel_geo_client
from app.core.config import Settings

GEO_KEY = "g" * 40
VWORLD_KEY = "v" * 36


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"pinvi_environment": "test"}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {"pinvi_kor_travel_geo_api_key": GEO_KEY, "pinvi_vworld_api_key": VWORLD_KEY},
            GEO_KEY,
        ),
        ({"pinvi_vworld_api_key": VWORLD_KEY}, VWORLD_KEY),
        ({"pinvi_kor_travel_geo_api_key": GEO_KEY}, GEO_KEY),
    ],
)
async def test_geo_client_prefers_dedicated_key(
    overrides: dict[str, object], expected: str
) -> None:
    client = create_kor_travel_geo_client(_settings(**overrides))
    try:
        assert client._auth_params() == {"key": expected}
    finally:
        await client.aclose()
