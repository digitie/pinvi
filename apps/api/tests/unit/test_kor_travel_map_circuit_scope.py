"""#702 — Map 회로가 Map 정상인데 열리던 문제.

운영 기록(2026-11-06 n150 `app.api_call_log`): 실패는 전부 전국 bbox(zoom 6~8) `/v1/features/in-bounds`의
5초 ``ReadTimeout``이었고, 같은 요청을 3번 다시 보냈으며(``ReadTimeout`` x3), 열린 공용 회로가
검색·상세·trip batch까지 120초 끊었다. weather·transport 표면도 같은 회로를 셌다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import httpx
import pytest

from app.clients.kor_travel_map import (
    KEEPALIVE_EXPIRY_SECONDS,
    KorTravelMapClient,
    KorTravelMapUnavailable,
    create_kor_travel_map_client,
)
from app.clients.kor_travel_map_transport import (
    KorTravelMapTransportClient,
    KorTravelMapTransportUnavailable,
)
from app.clients.kor_travel_map_weather import (
    KorTravelMapWeatherClient,
    KorTravelMapWeatherUnavailable,
)
from app.core.config import Settings

Handler = Callable[[httpx.Request], httpx.Response]
_OK = {"data": {}, "meta": {}}


def _client(handler: Handler, **kwargs: object) -> KorTravelMapClient:
    http = httpx.AsyncClient(base_url="http://map.test", transport=httpx.MockTransport(handler))
    params: dict[str, object] = {
        "max_attempts": 3,
        "backoff_base_seconds": 0.0,
        "service_token": "svc-token-secret",
    }
    params.update(kwargs)
    return KorTravelMapClient(http, **params)  # type: ignore[arg-type]


async def _in_bounds(client: KorTravelMapClient) -> object:
    return await client.features_in_bounds(
        min_lon=124.8, min_lat=34.94, max_lon=130.2, max_lat=38.03, zoom=7
    )


async def test_read_timeout_is_sent_once_and_logged_with_its_class(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sent = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        raise httpx.ReadTimeout("slow", request=request)

    client = _client(handler)
    with caplog.at_level(logging.WARNING, logger="app.clients.kor_travel_map"):
        with pytest.raises(KorTravelMapUnavailable) as info:
            await _in_bounds(client)
    # Map은 요청을 받아 처리 중이다 — 같은 무거운 질의를 겹쳐 쌓지 않는다.
    assert sent == 1
    assert info.value.error_class == "ReadTimeout"
    messages = [r.getMessage() for r in caplog.records]
    assert any(
        "kor_travel_map.unavailable" in m and "ReadTimeout" in m and "sent=1" in m for m in messages
    ), messages
    assert all("svc-token-secret" not in m and "min_lon" not in m for m in messages)
    await client.aclose()


async def test_connection_failures_still_retry_with_backoff() -> None:
    sent = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        raise httpx.ConnectError("refused", request=request)

    client = _client(handler)
    with pytest.raises(KorTravelMapUnavailable) as info:
        await client.get_feature("f_x")
    assert sent == 3
    assert info.value.error_class == "ConnectError"
    await client.aclose()


async def test_viewport_timeouts_do_not_cut_search_detail_or_batch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/features/in-bounds":
            raise httpx.ReadTimeout("slow nationwide viewport", request=request)
        if request.url.path == "/v1/features/search":
            return httpx.Response(200, json={"data": {"items": []}, "meta": {}})
        return httpx.Response(200, json={"data": {"feature_id": "f_x"}, "meta": {}})

    client = _client(handler)
    for _ in range(3):
        with pytest.raises(KorTravelMapUnavailable):
            await _in_bounds(client)
    with pytest.raises(KorTravelMapUnavailable) as info:
        await _in_bounds(client)
    assert info.value.code == "CIRCUIT_OPEN"
    # 다른 표면은 그대로 Map에 닿는다.
    assert (await client.search_features(q="안동하회마을"))["items"] == []
    assert await client.get_feature("f_x") == {"feature_id": "f_x"}
    await client.aclose()


async def test_feature_failures_do_not_cut_the_viewport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/features/in-bounds":
            return httpx.Response(200, json={"data": {"items": [], "clusters": []}, "meta": {}})
        raise httpx.ReadTimeout("slow detail", request=request)

    client = _client(handler)
    for _ in range(4):
        with pytest.raises(KorTravelMapUnavailable):
            await client.get_feature("f_x")
    assert (await _in_bounds(client))["items"] == []
    await client.aclose()


async def test_weather_timeouts_never_open_the_map_feature_circuits() -> None:
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.url.path)
        if request.url.path.startswith("/v1/service/weather/"):
            raise httpx.ReadTimeout("slow weather", request=request)
        return httpx.Response(200, json={"data": {"items": [], "clusters": []}, "meta": {}})

    client = _client(handler)
    weather = KorTravelMapWeatherClient(client)
    for _ in range(3):
        with pytest.raises(KorTravelMapWeatherUnavailable):
            await weather.nearest(lon=126.9, lat=37.5)
    # weather 자체 회로는 열린다 — Map을 더 부르지 않는다.
    with pytest.raises(KorTravelMapWeatherUnavailable) as info:
        await weather.nearest(lon=126.9, lat=37.5)
    assert info.value.code == "CIRCUIT_OPEN"
    assert sent.count("/v1/service/weather/nearest") == 3
    # 지도·검색·상세는 영향 없다.
    assert (await _in_bounds(client))["items"] == []
    await client.get_feature("f_x")
    await client.search_features(q="경복궁")
    await client.aclose()


async def test_transport_failures_never_open_the_map_feature_circuits() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/v1/service/transport/"):
            raise httpx.ReadTimeout("slow transport", request=request)
        return httpx.Response(200, json={"data": {"items": [], "clusters": []}, "meta": {}})

    client = _client(handler)
    transport = KorTravelMapTransportClient(client)
    for _ in range(3):
        with pytest.raises(KorTravelMapTransportUnavailable):
            await transport.list_items("rest-areas", bbox=(126.0, 37.0, 127.0, 38.0))
    with pytest.raises(KorTravelMapTransportUnavailable, match="회로 열림"):
        await transport.list_items("rest-areas", bbox=(126.0, 37.0, 127.0, 38.0))
    assert (await _in_bounds(client))["items"] == []
    await client.get_feature("f_x")
    await client.aclose()


async def test_stale_disconnect_on_get_is_resent_once_even_without_retry() -> None:
    sent = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        if sent == 1:
            raise httpx.RemoteProtocolError(
                "Server disconnected without sending a response.", request=request
            )
        return httpx.Response(200, json={"data": {"items": []}, "meta": {}})

    client = _client(handler)
    transport = KorTravelMapTransportClient(client)
    assert (await transport.list_items("rest-areas"))["items"] == []
    assert sent == 2
    await client.aclose()


async def test_stale_resend_is_once_and_counts_as_one_failure() -> None:
    sent = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        raise httpx.RemoteProtocolError("disconnected", request=request)

    client = _client(handler)
    transport = KorTravelMapTransportClient(client)
    for calls in (1, 2):
        with pytest.raises(KorTravelMapTransportUnavailable):
            await transport.list_items("rest-areas")
        assert sent == 2 * calls
    # 논리 호출 하나가 실패 하나다 — 세 번째에서야 회로가 열린다.
    with pytest.raises(KorTravelMapTransportUnavailable):
        await transport.list_items("rest-areas")
    assert sent == 6
    with pytest.raises(KorTravelMapTransportUnavailable, match="회로 열림"):
        await transport.list_items("rest-areas")
    assert sent == 6
    await client.aclose()


@pytest.mark.parametrize(
    "error",
    [httpx.ReadError, httpx.WriteError, httpx.ReadTimeout, httpx.WriteTimeout],
)
async def test_errors_after_map_got_the_request_are_never_resent(
    error: type[httpx.TransportError],
) -> None:
    """Map이 요청을 받은 뒤의 끊김·timeout은 무거운 질의 도중일 수 있다 — GET·POST batch 모두 한 번만."""
    sent = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        raise error("mid-query", request=request)

    client = _client(handler)
    with pytest.raises(KorTravelMapUnavailable):
        await _in_bounds(client)
    assert sent == 1
    with pytest.raises(KorTravelMapUnavailable):
        await client.get_features(["f_a"])
    assert sent == 2
    await client.aclose()


async def test_persistent_disconnect_on_retrying_get_is_bounded() -> None:
    """free resend 1번 + 연결 실패 재시도는 attempt 상한 안 — 끊김만 반복되면 2번에서 멈춘다."""
    sent = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        raise httpx.RemoteProtocolError("disconnected", request=request)

    client = _client(handler)
    with pytest.raises(KorTravelMapUnavailable):
        await client.get_feature("f_x")
    assert sent == 2
    await client.aclose()


async def test_viewport_5xx_still_retries_within_attempts() -> None:
    sent = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        return httpx.Response(503, json={"code": "UPSTREAM"})

    client = _client(handler)
    with pytest.raises(KorTravelMapUnavailable) as info:
        await _in_bounds(client)
    assert sent == 3
    assert info.value.error_class == "HTTP503"
    await client.aclose()


async def test_public_marker_layers_use_the_viewport_circuit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/map-markers"):
            raise httpx.ReadTimeout("slow nationwide markers", request=request)
        return httpx.Response(200, json={"data": {"items": []}, "meta": {}})

    client = _client(handler)
    for _ in range(3):
        with pytest.raises(KorTravelMapUnavailable):
            await client.public_festival_markers(
                min_lon=124.8, min_lat=33.0, max_lon=130.2, max_lat=38.6
            )
    with pytest.raises(KorTravelMapUnavailable) as info:
        await _in_bounds(client)
    assert info.value.code == "CIRCUIT_OPEN"
    assert (await client.search_features(q="축제"))["items"] == []
    await client.aclose()


async def test_circuit_open_is_logged_once_with_scope_and_class(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = _client(handler)
    with caplog.at_level(logging.WARNING, logger="app.clients.kor_travel_map"):
        for _ in range(5):
            with pytest.raises(KorTravelMapUnavailable):
                await _in_bounds(client)
    opened = [r.getMessage() for r in caplog.records if "circuit_open" in r.getMessage()]
    assert opened == [
        "kor_travel_map.circuit_open scope=viewport path=/v1/features/in-bounds "
        "error=ReadTimeout trial=False"
    ]
    await client.aclose()


async def test_non_idempotent_request_is_not_resent_after_disconnect() -> None:
    sent = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        raise httpx.RemoteProtocolError("disconnected", request=request)

    client = _client(handler)
    with pytest.raises(KorTravelMapUnavailable):
        await client._send("POST", "/v1/service/weather/locations/batch", json={}, retry=False)
    assert sent == 1
    with pytest.raises(KorTravelMapUnavailable):
        await client.get_features(["f_a"])
    assert sent == 2
    await client.aclose()


async def test_real_server_closing_a_kept_alive_connection_is_survived() -> None:
    """실제 소켓: 첫 응답은 keep-alive로 주고, 같은 연결의 다음 요청은 읽고 응답 없이 닫는다.

    uvicorn이 idle 연결을 닫는 순간 client가 그 연결을 재사용한 경우와 같은 결과(`RemoteProtocolError`)다.
    """
    body = b'{"data": {"items": []}, "meta": {}}'
    requests = 0

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal requests
        served_on_this_connection = 0
        try:
            while True:
                try:
                    await reader.readuntil(b"\r\n\r\n")
                except (asyncio.IncompleteReadError, ConnectionError):
                    return
                requests += 1
                if served_on_this_connection >= 1:
                    return  # 응답 없이 닫는다
                served_on_this_connection += 1
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    + f"Content-Length: {len(body)}\r\n\r\n".encode()
                    + body
                )
                await writer.drain()
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    http = httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=2.0)
    client = KorTravelMapClient(http, service_token="svc", max_attempts=1)
    transport = KorTravelMapTransportClient(client)
    try:
        for _ in range(4):
            assert (await transport.list_items("rest-areas"))["items"] == []
        # 2·3·4번째 논리 호출은 각각 끊긴 재사용 연결 1번 + 새 연결 1번이다.
        assert requests == 7
    finally:
        await client.aclose()
        server.close()
        await server.wait_closed()


async def test_pooled_connections_expire_before_map_keep_alive() -> None:
    client = create_kor_travel_map_client(Settings(_env_file=None))
    try:
        pool = client._http._transport._pool  # type: ignore[attr-defined]
        # Map uvicorn 기본 --timeout-keep-alive는 5초다.
        assert pool._keepalive_expiry == KEEPALIVE_EXPIRY_SECONDS < 5.0
    finally:
        await client.aclose()
