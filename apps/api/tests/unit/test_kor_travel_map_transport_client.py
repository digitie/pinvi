"""Map transport 상태 표면 client (ADR-076 D2) — httpx.MockTransport."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import httpx
import pytest

from app.clients.kor_travel_map import (
    KorTravelMapBadRequest,
    KorTravelMapClient,
    KorTravelMapContractError,
    KorTravelMapFeatureNotFound,
    KorTravelMapUnavailable,
)
from app.clients.kor_travel_map_transport import (
    KorTravelMapTransportClient,
    KorTravelMapTransportCursorExpired,
    KorTravelMapTransportUnavailable,
)
from app.core.time import KST
from tests import transport_map_fixtures as fx

Handler = Callable[[httpx.Request], httpx.Response]


def _map(handler: Handler, *, token: str = "svc-token") -> KorTravelMapClient:
    http = httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler))
    return KorTravelMapClient(
        http,
        service_token=token,
        public_api_key="public-key",
        max_attempts=3,
        backoff_base_seconds=0.0,
    )


def _client(handler: Handler, *, token: str = "svc-token") -> KorTravelMapTransportClient:
    return KorTravelMapTransportClient(_map(handler, token=token))


def _recorder(response: httpx.Response) -> tuple[Handler, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response

    return handler, seen


async def test_list_bbox_sends_service_token_and_threads_cursor() -> None:
    body = fx.list_body("rest-areas")
    body["meta"]["page"]["next_cursor"] = None
    handler, seen = _recorder(httpx.Response(200, json=body))
    data = await _client(handler).list_items(
        "rest-areas", bbox=(126.9, 37.4, 127.1, 37.6), limit=50
    )
    request = seen[0]
    assert request.url.path == "/v1/service/transport/rest-areas"
    assert dict(request.url.params) == {
        "min_lon": "126.9",
        "min_lat": "37.4",
        "max_lon": "127.1",
        "max_lat": "37.6",
        "limit": "50",
    }
    assert request.headers["X-Kor-Travel-Map-Service-Token"] == "svc-token"
    # transport는 service 표면이다 — public API key로 fallback하지 않는다.
    assert "X-Kor-Travel-Map-Api-Key" not in request.headers
    assert data["items"][0]["feature_id"] == fx.REST_AREA_ID
    assert data["next_cursor"] is None


async def test_near_query_shape() -> None:
    handler, seen = _recorder(httpx.Response(200, json=fx.list_body("airports")))
    await _client(handler).list_items("airports", near=(126.8, 37.5, 5000.0))
    assert dict(seen[0].url.params) == {"lon": "126.8", "lat": "37.5", "radius_m": "5000.0"}


async def test_missing_service_token_short_circuits_without_calling_map() -> None:
    """service token이 없으면 운영 Map은 401이다 — 뷰포트마다 거절당하러 가지 않는다."""
    handler, seen = _recorder(httpx.Response(200, json=fx.list_body("airports")))
    with pytest.raises(KorTravelMapTransportUnavailable) as caught:
        await _client(handler, token="").list_items("airports", near=(126.8, 37.5, 5000.0))
    assert caught.value.code == "UPSTREAM_AUTH"
    assert seen == []


async def test_non_transport_httpx_errors_become_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.DecodingError("bad gzip", request=request)

    with pytest.raises(KorTravelMapTransportUnavailable):
        await _client(handler).status()


async def test_route_404_without_not_found_code_is_not_item_missing() -> None:
    """transport 라우터가 없는 옛 Map의 404는 "항목 없음"이 아니다."""
    handler, _ = _recorder(httpx.Response(404, json={"detail": "Not Found"}))
    with pytest.raises(KorTravelMapTransportUnavailable) as caught:
        await _client(handler).detail("airports", fx.AIRPORT_ID)
    assert caught.value.code == "UPSTREAM_REJECTED"


async def test_list_rejects_combinations_map_would_422() -> None:
    client = _client(_recorder(httpx.Response(200, json={}))[0])
    with pytest.raises(ValueError):
        await client.list_items("airports", bbox=(1, 2, 3, 4), near=(1, 2, 3))
    with pytest.raises(ValueError):
        await client.list_items("airports", bbox=(1, 2, 3, 4), cursor="abc")


async def test_503_not_loaded_is_not_retried_and_keeps_code() -> None:
    handler, seen = _recorder(
        httpx.Response(503, json=fx.problem_body(503, "TRANSPORT_STATE_NOT_LOADED"))
    )
    with pytest.raises(KorTravelMapTransportUnavailable) as caught:
        await _client(handler).list_items("fuel-stations", bbox=(126, 37, 127, 38))
    assert caught.value.code == "TRANSPORT_STATE_NOT_LOADED"
    assert len(seen) == 1


async def test_timeout_is_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(KorTravelMapTransportUnavailable) as caught:
        await _client(handler).status()
    assert caught.value.code is None
    assert calls == 1


@pytest.mark.parametrize("status_code", [401, 403])
async def test_auth_rejection_is_upstream_auth(status_code: int) -> None:
    handler, _ = _recorder(
        httpx.Response(status_code, json=fx.problem_body(status_code, "UNAUTHORIZED"))
    )
    with pytest.raises(KorTravelMapTransportUnavailable) as caught:
        await _client(handler).status()
    assert caught.value.code == "UPSTREAM_AUTH"


async def test_404_409_422_mapping() -> None:
    handler, _ = _recorder(httpx.Response(404, json=fx.problem_body(404, "NOT_FOUND")))
    with pytest.raises(KorTravelMapFeatureNotFound):
        await _client(handler).detail("airports", fx.AIRPORT_ID)
    handler, _ = _recorder(
        httpx.Response(409, json=fx.problem_body(409, "TRANSPORT_STATE_GENERATION_EXPIRED"))
    )
    with pytest.raises(KorTravelMapTransportCursorExpired):
        await _client(handler).list_items("airports", cursor="c1")
    handler, _ = _recorder(httpx.Response(422, json=fx.problem_body(422, "VALIDATION_ERROR")))
    with pytest.raises(KorTravelMapBadRequest) as caught:
        await _client(handler).list_items("airports", bbox=(126, 37, 127, 38))
    assert caught.value.code == "VALIDATION_ERROR"


async def test_success_body_is_parsed_strictly() -> None:
    handler, _ = _recorder(
        httpx.Response(200, content=b'{"data": {"items": [], "items": []}, "meta": {}}')
    )
    with pytest.raises(KorTravelMapContractError):
        await _client(handler).list_items("airports")


async def test_price_history_since_is_aware_and_encoded() -> None:
    handler, seen = _recorder(httpx.Response(200, json=fx.history_body(available=False)))
    since = datetime(2026, 10, 1, 9, 0, tzinfo=KST)
    data = await _client(handler).fuel_price_history(fx.FUEL_STATION_ID, since=since)
    request = seen[0]
    assert (
        request.url.path
        == f"/v1/service/transport/fuel-stations/{fx.FUEL_STATION_ID}/price-history"
    )
    assert request.url.params["since"] == "2026-10-01T09:00:00+09:00"
    assert b"%2B09%3A00" in request.url.query
    assert data["history"]["status"] == "unavailable"
    with pytest.raises(ValueError):
        await _client(handler).fuel_price_history(fx.FUEL_STATION_ID, since=datetime(2026, 10, 1))


async def test_feature_paths_keep_retrying_5xx() -> None:
    """기존 feature 경로의 재시도 동작은 그대로다(retry 기본값)."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    with pytest.raises(KorTravelMapUnavailable):
        await _map(handler).get_feature("f-1")
    assert calls == 3
