"""실제 kor-travel-map public/service 인증 계약 opt-in smoke."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

import httpx
import pytest

from app.clients.kor_travel_map import KorTravelMapClient

_PUBLIC_API_KEY_HEADER = "X-Kor-Travel-Map-Api-Key"
_SERVICE_TOKEN_HEADER = "X-Kor-Travel-Map-Service-Token"
_LIVE_OPT_IN = "PINVI_KOR_TRAVEL_MAP_LIVE_SMOKE"
_REQUIRED_ENV = (
    "PINVI_KOR_TRAVEL_MAP_API_BASE_URL",
    "PINVI_KOR_TRAVEL_MAP_SERVICE_TOKEN",
    "PINVI_KOR_TRAVEL_MAP_PUBLIC_API_KEY",
    "PINVI_KOR_TRAVEL_MAP_LIVE_FEATURE_ID",
)

pytestmark = pytest.mark.skipif(
    os.environ.get(_LIVE_OPT_IN) != "1",
    reason=f"실제 kor-travel-map smoke는 {_LIVE_OPT_IN}=1에서만 실행",
)


@pytest.fixture(scope="module")
def live_env() -> dict[str, str]:
    values = {name: os.environ.get(name, "").strip() for name in _REQUIRED_ENV}
    missing = [name for name, value in values.items() if not value]
    if missing:
        pytest.fail(f"live smoke 필수 환경변수 누락: {', '.join(missing)}")
    return values


async def _recorded_client_call(
    live_env: dict[str, str],
    *,
    service_token: str,
    public_api_key: str,
    call: Callable[[KorTravelMapClient], Awaitable[dict[str, object]]],
) -> tuple[dict[str, bool], dict[str, object]]:
    recorded: dict[str, bool] = {}

    async def capture(request: httpx.Request) -> None:
        service_header = request.headers.get(_SERVICE_TOKEN_HEADER)
        public_header = request.headers.get(_PUBLIC_API_KEY_HEADER)
        recorded.update(
            {
                "service_token_present": service_header is not None,
                "service_token_matches": (
                    service_header == service_token if service_token else service_header is None
                ),
                "public_api_key_present": public_header is not None,
                "public_api_key_matches": (
                    public_header == public_api_key
                    if public_api_key and not service_token
                    else public_header is None
                ),
                "query_key_absent": request.url.params.get("key") is None,
            }
        )

    http = httpx.AsyncClient(
        base_url=live_env["PINVI_KOR_TRAVEL_MAP_API_BASE_URL"],
        timeout=10.0,
        event_hooks={"request": [capture]},
    )
    client = KorTravelMapClient(
        http,
        service_token=service_token,
        public_api_key=public_api_key,
        max_attempts=1,
    )
    try:
        result = await call(client)
    finally:
        await client.aclose()
    return recorded, result


async def test_live_public_key_header_succeeds_without_query(
    live_env: dict[str, str],
) -> None:
    recorded, result = await _recorded_client_call(
        live_env,
        service_token="",
        public_api_key=live_env["PINVI_KOR_TRAVEL_MAP_PUBLIC_API_KEY"],
        call=lambda client: client.categories(),
    )
    assert isinstance(result, dict)
    assert recorded == {
        "service_token_present": False,
        "service_token_matches": True,
        "public_api_key_present": True,
        "public_api_key_matches": True,
        "query_key_absent": True,
    }


async def test_live_service_token_takes_priority_over_public_key(
    live_env: dict[str, str],
) -> None:
    recorded, result = await _recorded_client_call(
        live_env,
        service_token=live_env["PINVI_KOR_TRAVEL_MAP_SERVICE_TOKEN"],
        public_api_key=live_env["PINVI_KOR_TRAVEL_MAP_PUBLIC_API_KEY"],
        call=lambda client: client.categories(),
    )
    assert isinstance(result, dict)
    assert recorded == {
        "service_token_present": True,
        "service_token_matches": True,
        "public_api_key_present": False,
        "public_api_key_matches": True,
        "query_key_absent": True,
    }


async def test_live_batch_uses_service_token_only(live_env: dict[str, str]) -> None:
    feature_id = live_env["PINVI_KOR_TRAVEL_MAP_LIVE_FEATURE_ID"]
    recorded, result = await _recorded_client_call(
        live_env,
        service_token=live_env["PINVI_KOR_TRAVEL_MAP_SERVICE_TOKEN"],
        public_api_key=live_env["PINVI_KOR_TRAVEL_MAP_PUBLIC_API_KEY"],
        call=lambda client: client.get_features([feature_id]),
    )
    assert set(result) == {"found", "missing"}
    assert recorded == {
        "service_token_present": True,
        "service_token_matches": True,
        "public_api_key_present": False,
        "public_api_key_matches": True,
        "query_key_absent": True,
    }
