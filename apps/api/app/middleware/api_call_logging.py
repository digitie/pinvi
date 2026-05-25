"""외부 API 호출 로깅 (httpx event_hook). `docs/api/admin.md`."""

from __future__ import annotations

import time
import uuid
from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_call_log import ApiCallLog

log = structlog.get_logger("api_call")


class ApiCallTracker:
    """httpx AsyncClient에 event_hook으로 부착.

    `request.extensions["tripmate_provider"]`에 provider 이름을 넣어 호출.
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
        provider = request.extensions.get("tripmate_provider", "unknown")
        request_id_raw = request.extensions.get("tripmate_request_id")
        request_id = None
        if isinstance(request_id_raw, str):
            try:
                request_id = uuid.UUID(request_id_raw)
            except ValueError:
                request_id = None

        async with self._session_factory() as session:
            await _append(
                session,
                provider=str(provider),
                endpoint=str(request.url),
                status_code=response.status_code,
                latency_ms=latency_ms,
                error_class=None,
                error_message=None,
                request_id=request_id,
            )


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
