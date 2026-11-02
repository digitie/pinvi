"""외부 API 비밀값이 stdout 로그에 남지 않는다.

2026-11-02 prod 점검: httpx의 INFO 줄 `HTTP Request: POST http://…/v2/geocode?key=…`이 컨테이너
stdout에 kor-travel-geo 공개 API key를 그대로 찍었다(`api_call_log` 테이블만 가리고 있었다).
테스트는 운영과 같은 경로 — `configure_logging()`이 만든 root stdout handler — 의 출력을 본다.
"""

from __future__ import annotations

import io
import logging
import sys
from collections.abc import Iterator

import httpx
import pytest
import structlog

from app.clients.kor_travel_geo import KorTravelGeoClient
from app.core.logging import configure_logging, get_logger

SECRET = "SECRET-GEO-KEY-1234"
_TOUCHED_LOGGERS = ("httpx", "httpcore", "uvicorn", "uvicorn.access", "uvicorn.error")


@pytest.fixture
def prod_stdout() -> Iterator[io.StringIO]:
    """root handler를 비운 뒤 운영처럼 `configure_logging("INFO")`을 부르고, 끝나면 되돌린다.

    운영에서는 root에 handler가 없어 `basicConfig`가 `sys.stdout` handler를 만든다. 그 호출
    순간에만 `sys.stdout`을 StringIO로 바꿔, 만들어진 handler가 쓰는 내용을 그대로 읽는다.
    """

    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    saved = {
        name: (logging.getLogger(name).level, logging.getLogger(name).filters[:])
        for name in _TOUCHED_LOGGERS
    }
    for handler in saved_handlers:
        root.removeHandler(handler)
    structlog.reset_defaults()
    stream = io.StringIO()
    real_stdout = sys.stdout
    sys.stdout = stream
    try:
        configure_logging("INFO")
    finally:
        sys.stdout = real_stdout
    try:
        yield stream
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        for handler in saved_handlers:
            root.addHandler(handler)
        root.setLevel(saved_level)
        for name, (level, filters) in saved.items():
            named = logging.getLogger(name)
            named.setLevel(level)
            named.filters[:] = filters
        structlog.reset_defaults()
        configure_logging("WARNING")


def _geo_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"status": "OK", "query_id": "q", "input": {}, "candidates": []},
        request=request,
    )


async def test_geo_client_call_does_not_write_api_key_to_stdout(
    prod_stdout: io.StringIO,
) -> None:
    http = httpx.AsyncClient(transport=httpx.MockTransport(_geo_ok), base_url="http://geo.test")
    client = KorTravelGeoClient(http, api_key=SECRET, max_attempts=1)
    try:
        await client.geocode(query="안동시 하회마을길 186")
    finally:
        await client.aclose()
    logging.getLogger("app.test").warning("probe.after_geo_call")

    out = prod_stdout.getvalue()
    assert "probe.after_geo_call" in out  # stdout handler가 실제로 쓰고 있다
    assert SECRET not in out


def test_httpx_record_that_is_emitted_is_redacted(
    prod_stdout: io.StringIO,
) -> None:
    """WARNING 이상으로 나오는 httpx 줄도 가린다(URL은 `httpx.URL` 객체 인자로 온다)."""

    url = httpx.URL(f"http://geo.test/v2/geocode?key={SECRET}&limit=5")
    logging.getLogger("httpx").warning('HTTP Request: %s %s "%s"', "POST", url, "HTTP/1.1 500")

    out = prod_stdout.getvalue()
    assert "HTTP Request: POST" in out  # 줄은 실제로 나왔다
    assert SECRET not in out
    assert "key=***&limit=5" in out


def test_structlog_fields_and_tracebacks_are_redacted(
    prod_stdout: io.StringIO,
) -> None:
    get_logger("app.test").warning(
        "weather.failed", url=f"http://weather.test/v1?serviceKey={SECRET}&lat=1"
    )
    try:
        raise httpx.HTTPStatusError(
            f"Server error '500' for url 'http://geo.test/v2/reverse?key={SECRET}'",
            request=httpx.Request("POST", "http://geo.test/v2/reverse"),
            response=httpx.Response(500),
        )
    except httpx.HTTPStatusError:
        logging.getLogger("app.test").exception("geo.failed")

    out = prod_stdout.getvalue()
    assert "weather.failed" in out
    assert "geo.failed" in out
    assert SECRET not in out
    assert "serviceKey=***" in out


@pytest.mark.usefixtures("prod_stdout")
def test_uvicorn_access_line_keeps_args_shape_and_hides_inbound_token() -> None:
    """uvicorn AccessFormatter는 args를 5-튜플로 풀어 쓴다 — 모양을 지키며 토큰만 가린다."""

    from uvicorn.logging import AccessFormatter

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s'))
    access = logging.getLogger("uvicorn.access")
    saved_propagate = access.propagate
    access.addHandler(handler)
    access.propagate = False
    trip_id = "11111111-1111-4111-8111-111111111111"
    try:
        for path in (
            f"/api/v1/auth/reset?token={SECRET}",
            f"/api/v1/trips/{trip_id}/shared/{SECRET}",
            f"/api/v1/storage/downloads/{SECRET}",
        ):
            access.info('%s - "%s %s HTTP/%s" %d', "203.0.113.5:4000", "GET", path, "1.1", 200)
    finally:
        access.removeHandler(handler)
        access.propagate = saved_propagate

    lines = stream.getvalue()
    assert "GET /api/v1/auth/reset?token=*** HTTP/1.1" in lines
    assert f"GET /api/v1/trips/{trip_id}/shared/*** HTTP/1.1" in lines
    assert "GET /api/v1/storage/downloads/*** HTTP/1.1" in lines
    assert SECRET not in lines
