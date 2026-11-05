"""외부 HTTP 호출의 제한된 메모리 배치 기록. 감사/업무 outbox가 아닌 손실 허용 관측이다."""

from __future__ import annotations

import asyncio
import sys
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import structlog
from prometheus_client import Counter, Gauge
from sqlalchemy import insert

from app.core.redaction import sanitize_url
from app.core.time import kst_now
from app.models.api_call_log import ApiCallLog

log = structlog.get_logger("api_call")
_PROVIDER_EXTENSION = "pinvi_provider"
_REQUEST_ID_EXTENSION = "request_id"
_REQUEST_STARTED_EXTENSION = "pinvi_api_call_started_at"
_TRACKER_EXTENSION = "pinvi_api_call_tracker"
_DEFER_RESPONSE_EXTENSION = "pinvi_api_call_defer_response"

LOG_ROWS = Counter("pinvi_api_call_log_rows_total", "External HTTP observation rows.", ("outcome",))
LOG_QUEUED = Gauge(
    "pinvi_api_call_log_queued",
    "External HTTP observation rows awaiting flush.",
    multiprocess_mode="livesum",
)


class ApiCallLogOutbox:
    """프로세스의 session factory 하나당 큐 하나, worker 하나. 큐 포화/DB 실패는 버린다."""

    def __init__(
        self,
        session_factory: Any,
        *,
        capacity: int = 1024,
        batch_size: int = 100,
        flush_interval: float = 0.25,
        flush_timeout: float = 2.0,
        shutdown_timeout: float = 3.0,
    ) -> None:
        if (
            capacity < 1
            or batch_size < 1
            or min(flush_interval, flush_timeout, shutdown_timeout) <= 0
        ):
            raise ValueError("logging queue limits must be positive")
        self._session_factory = session_factory
        self._capacity = capacity
        self._batch_size = min(batch_size, capacity)
        self._flush_interval = flush_interval
        self._flush_timeout = flush_timeout
        self._shutdown_timeout = shutdown_timeout
        self._queue: deque[dict[str, Any]] = deque()
        self._wake = asyncio.Event()
        self._flush_lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._closed = False
        self.dropped = 0
        self.persisted = 0

    @property
    def pending(self) -> int:
        return len(self._queue)

    def _drop(self, count: int, reason: str) -> None:
        self.dropped += count
        LOG_ROWS.labels(outcome=reason).inc(count)

    def submit(self, row: dict[str, Any]) -> None:
        # await/DB 호출이 없는 원자 구간이다. in-flight batch는 별도로 최대 batch_size개다.
        if self._closed:
            self._drop(1, "closed")
            return
        if len(self._queue) >= self._capacity:
            self._drop(1, "overflow")
            return
        self._queue.append(row)
        LOG_QUEUED.inc()
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="pinvi-api-call-log")
        if len(self._queue) >= self._batch_size:
            self._wake.set()

    async def _run(self) -> None:
        while not self._closed or self._queue:
            try:
                await asyncio.wait_for(self._wake.wait(), self._flush_interval)
            except TimeoutError:
                pass
            self._wake.clear()
            await self._flush_batch()
            if self._queue:
                self._wake.set()

    async def _flush_batch(self) -> None:
        async with self._flush_lock:
            batch = [self._queue.popleft() for _ in range(min(self._batch_size, len(self._queue)))]
            if not batch:
                return
            LOG_QUEUED.dec(len(batch))
            try:
                async with asyncio.timeout(self._flush_timeout):
                    async with self._session_factory() as session:
                        await session.execute(insert(ApiCallLog), batch)
                        await session.commit()
            except asyncio.CancelledError:
                self._drop(len(batch), "cancelled")
                raise
            except Exception as exc:
                self._drop(len(batch), "persist_failed")
                # DB exception의 SQL parameters/DSN은 로그에 복사하지 않는다.
                log.warning(
                    "api_call_log.persist_failed",
                    error_class=type(exc).__name__,
                    dropped=len(batch),
                )
            else:
                self.persisted += len(batch)
                LOG_ROWS.labels(outcome="persisted").inc(len(batch))

    async def flush(self) -> None:
        while self._queue:
            await self._flush_batch()

    async def close(self) -> None:
        self._closed = True
        self._wake.set()
        try:
            if self._task is not None:
                async with asyncio.timeout(self._shutdown_timeout):
                    await self._task
        finally:
            if self._task is not None and not self._task.done():
                self._task.cancel()
                await asyncio.gather(self._task, return_exceptions=True)
            remaining = len(self._queue)
            if remaining:
                self._queue.clear()
                LOG_QUEUED.dec(remaining)
                self._drop(remaining, "shutdown")


_OUTBOXES: dict[Any, ApiCallLogOutbox] = {}


def _outbox_for(session_factory: Any) -> ApiCallLogOutbox:
    if session_factory not in _OUTBOXES:
        _OUTBOXES[session_factory] = ApiCallLogOutbox(session_factory)
    return _OUTBOXES[session_factory]


async def close_api_call_logs(session_factory: Any) -> None:
    """전송 client/업무 worker가 닫힌 뒤 lifespan 바깥에서 호출한다."""
    outbox = _OUTBOXES.pop(session_factory, None)
    if outbox is not None:
        try:
            await outbox.close()
        except TimeoutError:
            log.warning("api_call_log.shutdown_timeout")


class ApiCallTracker:
    """request.extensions에 시작 시각을 보관한다. 전역 request 추적표는 없다."""

    def __init__(self, session_factory: Any) -> None:
        self.outbox = _outbox_for(session_factory)

    async def on_request(self, request: httpx.Request) -> None:
        request.extensions[_REQUEST_STARTED_EXTENSION] = time.perf_counter()
        request.extensions[_TRACKER_EXTENSION] = self

    def _record(
        self,
        request: httpx.Request,
        *,
        status_code: int | None,
        error: BaseException | None = None,
    ) -> None:
        start = request.extensions.pop(_REQUEST_STARTED_EXTENSION, None)
        request.extensions.pop(_TRACKER_EXTENSION, None)
        if start is None:
            return  # response/예외/취소가 같은 attempt를 중복 기록하지 않는다.
        raw_id = request.extensions.get(_REQUEST_ID_EXTENSION)
        try:
            request_id = uuid.UUID(raw_id) if isinstance(raw_id, str) else None
        except ValueError:
            request_id = None
        error_class = type(error).__name__[:64] if error is not None else None
        # 임의 예외 메시지는 헤더·body·SQL·자격증명을 포함할 수 있어 저장하지 않는다.
        error_message = f"외부 HTTP 요청 실패: {error_class}" if error_class else None
        if error is None and status_code is not None and status_code >= 400:
            error_class, error_message = "HTTPStatusError", f"HTTP {status_code}"
        self.outbox.submit(
            {
                "provider": str(request.extensions.get(_PROVIDER_EXTENSION, "unknown"))[:64],
                "endpoint": sanitize_api_call_endpoint(request.url),
                "status_code": status_code,
                "latency_ms": max(0, int((time.perf_counter() - start) * 1000)),
                "error_class": error_class,
                "error_message": error_message,
                "request_id": request_id,
                "occurred_at": kst_now(),
            }
        )

    async def on_response(self, response: httpx.Response) -> None:
        if not response.request.extensions.get(_DEFER_RESPONSE_EXTENSION):
            self._record(response.request, status_code=response.status_code)

    def on_error(self, request: httpx.Request, error: BaseException) -> None:
        self._record(request, status_code=None, error=error)


class _ObservedResponseStream(httpx.AsyncByteStream):
    """stream=True 응답은 헤더가 아닌 EOF/실패/취소/조기 close에서 한 번 기록한다."""

    def __init__(
        self,
        stream: httpx.AsyncByteStream,
        request: httpx.Request,
        tracker: ApiCallTracker,
        status_code: int,
    ) -> None:
        self._stream = stream
        self._request = request
        self._tracker = tracker
        self._status_code = status_code

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self._stream:
                yield chunk
        except BaseException as exc:
            self._tracker.on_error(self._request, exc)
            raise
        else:
            self._tracker._record(self._request, status_code=self._status_code)

    async def aclose(self) -> None:
        # bounded reader의 상한 예외/호출자 취소도 context manager의 close에서 보존한다.
        active_error = sys.exception()
        try:
            await self._stream.aclose()
        except BaseException as exc:
            self._tracker.on_error(self._request, exc)
            raise
        finally:
            self._tracker.on_error(
                self._request,
                active_error if active_error is not None else httpx.ResponseNotRead(),
            )


class ApiCallLoggingClient(httpx.AsyncClient):
    """event hook에 없는 전송·body read 오류/취소도 기록하고 원래 예외를 그대로 올린다."""

    async def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        request.extensions[_DEFER_RESPONSE_EXTENSION] = True
        try:
            response = await super().send(request, **kwargs)
        except BaseException as exc:
            tracker = request.extensions.get(_TRACKER_EXTENSION)
            if isinstance(tracker, ApiCallTracker):
                tracker.on_error(request, exc)
            raise
        else:
            tracker = request.extensions.get(_TRACKER_EXTENSION)
            if isinstance(tracker, ApiCallTracker):
                if (
                    kwargs.get("stream")
                    and not response.is_stream_consumed
                    and isinstance(response.stream, httpx.AsyncByteStream)
                ):
                    response.stream = _ObservedResponseStream(
                        response.stream, request, tracker, response.status_code
                    )
                else:
                    tracker._record(request, status_code=response.status_code)
            return response
        finally:
            request.extensions.pop(_DEFER_RESPONSE_EXTENSION, None)


def api_call_event_hooks(
    session_factory: Any,
    *,
    provider: str,
) -> dict[str, list[Callable[..., Any]]]:
    """기존 provider tag 계약을 유지한다. transport 예외 기록은 ApiCallLoggingClient가 맡는다."""
    tracker = ApiCallTracker(session_factory)
    provider_name = provider.strip() or "unknown"

    async def tag_provider(request: httpx.Request) -> None:
        request.extensions.setdefault(_PROVIDER_EXTENSION, provider_name)

    return {"request": [tag_provider, tracker.on_request], "response": [tracker.on_response]}


def sanitize_api_call_endpoint(url: httpx.URL | str) -> str:
    """stdout과 같은 redaction 규칙으로 query·path 자격증명을 가린다."""
    return sanitize_url(url)
