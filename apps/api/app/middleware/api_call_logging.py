"""외부 API 호출 로깅 (httpx event_hook). `docs/api/admin.md`."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_call_log import ApiCallLog

log = structlog.get_logger("api_call")

_PROVIDER_EXTENSION = "pinvi_provider"
_REQUEST_ID_EXTENSION = "pinvi_request_id"
_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "client_secret",
    "key",
    "password",
    "secret",
    "service_key",
    "servicekey",
    "token",
}
_TELEGRAM_BOT_TOKEN_RE = re.compile(r"/bot(\d+):[A-Za-z0-9_-]+")


class ApiCallTracker:
    """httpx AsyncClient에 event_hook으로 부착.

    `request.extensions["pinvi_provider"]`에 provider 이름을 넣어 호출.
    """

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory
        self._start_times: dict[int, float] = {}

    async def on_request(self, request: httpx.Request) -> None:
        self._start_times[id(request)] = time.perf_counter()

    async def on_response(self, response: httpx.Response) -> None:
        request = response.request
        start = self._start_times.pop(id(request), None)
        latency_ms = int((time.perf_counter() - start) * 1000) if start else None
        provider = request.extensions.get(_PROVIDER_EXTENSION, "unknown")
        request_id_raw = request.extensions.get(_REQUEST_ID_EXTENSION)
        request_id = None
        if isinstance(request_id_raw, str):
            try:
                request_id = uuid.UUID(request_id_raw)
            except ValueError:
                request_id = None

        try:
            async with self._session_factory() as session:
                await _append(
                    session,
                    provider=str(provider),
                    endpoint=sanitize_api_call_endpoint(request.url),
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    error_class=None,
                    error_message=None,
                    request_id=request_id,
                )
        except Exception as exc:
            log.warning("api_call_log.persist_failed", provider=str(provider), error=str(exc))


def api_call_event_hooks(
    session_factory: Any,
    *,
    provider: str,
) -> dict[str, list[Callable[..., Any]]]:
    """provider tag + DB tracker hook 묶음.

    client별 요청 코드가 `extensions`를 직접 넘기지 않아도 provider가 `unknown`으로
    떨어지지 않게 request hook에서 기본 tag를 채운다.
    """

    tracker = ApiCallTracker(session_factory)
    provider_name = provider.strip() or "unknown"

    async def tag_provider(request: httpx.Request) -> None:
        request.extensions.setdefault(_PROVIDER_EXTENSION, provider_name)

    return {
        "request": [tag_provider, tracker.on_request],
        "response": [tracker.on_response],
    }


def sanitize_api_call_endpoint(url: httpx.URL | str) -> str:
    """api_call_log endpoint에서 query secret과 Telegram bot token path를 마스킹한다."""

    raw = str(url)
    parts = urlsplit(raw)
    path = _TELEGRAM_BOT_TOKEN_RE.sub(r"/bot\1:***", parts.path)
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    query = urlencode(
        [
            (key, "***" if key.lower() in _SENSITIVE_QUERY_KEYS else value)
            for key, value in query_pairs
        ],
        doseq=True,
    )
    return urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


async def _append(
    session: AsyncSession,
    *,
    provider: str,
    endpoint: str,
    status_code: int | None,
    latency_ms: int | None,
    error_class: str | None,
    error_message: str | None,
    request_id: uuid.UUID | None,
) -> None:
    row = ApiCallLog(
        provider=provider,
        endpoint=endpoint,
        status_code=status_code,
        latency_ms=latency_ms,
        error_class=error_class,
        error_message=error_message,
        request_id=request_id,
    )
    session.add(row)
    await session.commit()
