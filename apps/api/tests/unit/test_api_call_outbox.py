"""외부 호출 기록은 요청의 DB 대기와 분리되고 실패도 유실하지 않는다."""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest

from app.middleware.api_call_logging import (
    ApiCallLoggingClient,
    ApiCallLogOutbox,
    ApiCallTracker,
    api_call_event_hooks,
    close_api_call_logs,
)


class RecordingFactory:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.rows = []
        self.batches = []
        self.commits = 0
        self.fail = False

    async def __aenter__(self):
        self.entered.set()
        await self.release.wait()
        if self.fail:
            raise RuntimeError("password=not-for-logs")
        return self

    async def __aexit__(self, *_args):
        return None

    def __call__(self):
        return self

    async def execute(self, _statement, rows):
        self.rows.extend(rows)
        self.batches.append(rows)

    async def commit(self):
        self.commits += 1


async def test_response_does_not_wait_for_log_database() -> None:
    factory = RecordingFactory()
    tracker = ApiCallTracker(factory)
    request = httpx.Request("GET", "https://fixture.invalid/item")
    await tracker.on_request(request)
    task = asyncio.create_task(tracker.on_response(httpx.Response(200, request=request)))
    try:
        await asyncio.sleep(0)
        assert task.done(), "HTTP response hook is waiting for the logging database"
    finally:
        factory.release.set()
        await task
        await close_api_call_logs(factory)
    assert len(factory.rows) == 1


@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ConnectError])
async def test_transport_failure_is_recorded_without_response_hook(error_type) -> None:
    factory = RecordingFactory()
    factory.release.set()
    request_id = uuid.uuid4()

    async def fail(request: httpx.Request) -> httpx.Response:
        raise error_type("Authorization: Bearer should-never-persist", request=request)

    async with ApiCallLoggingClient(
        transport=httpx.MockTransport(fail),
        event_hooks=api_call_event_hooks(factory, provider="fixture"),
    ) as client:
        with pytest.raises(error_type):
            await client.get(
                "https://fixture.invalid/item?key=fixture-private",
                extensions={"request_id": str(request_id)},
            )
    await close_api_call_logs(factory)
    assert len(factory.rows) == 1
    row = factory.rows[0]
    assert row["error_class"] == error_type.__name__
    assert row["status_code"] is None
    assert row["request_id"] == request_id
    assert row["latency_ms"] is not None
    assert row["occurred_at"].tzinfo is not None
    assert "should-never-persist" not in repr(row)
    assert "fixture-private" not in repr(row)


async def test_cancelled_attempt_is_observed_and_reraises_cancellation() -> None:
    factory = RecordingFactory()
    factory.release.set()
    entered = asyncio.Event()

    async def hang(request: httpx.Request) -> httpx.Response:
        entered.set()
        await asyncio.Event().wait()
        return httpx.Response(200, request=request)

    async with ApiCallLoggingClient(
        transport=httpx.MockTransport(hang),
        event_hooks=api_call_event_hooks(factory, provider="fixture"),
    ) as client:
        pending = asyncio.create_task(client.get("https://fixture.invalid/cancel"))
        await entered.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    await close_api_call_logs(factory)
    assert [row["error_class"] for row in factory.rows] == ["CancelledError"]


async def test_body_failure_is_not_misreported_as_http_success() -> None:
    factory = RecordingFactory()
    factory.release.set()

    class BrokenStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"partial"
            raise httpx.ReadError("token=private")

    async def response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=BrokenStream(), request=request)

    async with ApiCallLoggingClient(
        transport=httpx.MockTransport(response),
        event_hooks=api_call_event_hooks(factory, provider="fixture"),
    ) as client:
        with pytest.raises(httpx.ReadError):
            await client.get("https://fixture.invalid/broken")
    await close_api_call_logs(factory)
    assert [row["error_class"] for row in factory.rows] == ["ReadError"]
    assert factory.rows[0]["status_code"] is None


async def test_batch_capacity_failures_and_shutdown_are_bounded() -> None:
    factory = RecordingFactory()
    factory.release.set()
    outbox = ApiCallLogOutbox(factory, capacity=3, batch_size=2, flush_interval=60)
    for i in range(5):
        outbox.submit({"provider": "fixture", "endpoint": f"/{i}"})
    assert outbox.pending == 3
    assert outbox.dropped == 2
    await outbox.close()
    assert outbox.pending == 0
    assert outbox.persisted == 3
    assert len(factory.batches) == 2
    assert factory.commits == 2
    outbox.submit({})
    assert outbox.dropped == 3

    failed = RecordingFactory()
    failed.release.set()
    failed.fail = True
    dropping = ApiCallLogOutbox(failed, flush_interval=60)
    dropping.submit({"provider": "fixture"})
    await dropping.close()
    assert dropping.dropped == 1
    assert dropping.persisted == 0


async def test_database_hang_does_not_block_shutdown_or_leave_worker() -> None:
    factory = RecordingFactory()
    outbox = ApiCallLogOutbox(factory, flush_interval=0.001, shutdown_timeout=0.05)
    outbox.submit({"provider": "fixture"})
    await factory.entered.wait()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(outbox.close(), 1)
    assert outbox.pending == 0
    assert outbox.dropped == 1
    assert outbox._task.done()


class FlakyFactory:
    """attempt마다 지정한 단계(enter/commit)에서 멈추거나 실패하는 세션 팩토리."""

    def __init__(self, plan: list[str | None]) -> None:
        # plan[i]: i번째 attempt의 실패 지점. None=성공, "hang_enter"/"hang_commit"/"fail_enter".
        self.plan = plan
        self.attempts = 0
        self.rows: list[dict] = []
        self.contexts: list[dict] = []
        self._current: str | None = None

    def __call__(self):
        return self

    async def __aenter__(self):
        import structlog

        self.contexts.append(dict(structlog.contextvars.get_contextvars()))
        step = self.plan[self.attempts] if self.attempts < len(self.plan) else None
        self.attempts += 1
        self._current = step
        if step == "hang_enter":
            await asyncio.Event().wait()
        if step == "fail_enter":
            raise ConnectionError("dsn=postgresql://user:secret@db")
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, _statement, rows):
        self._pending = list(rows)

    async def commit(self):
        if self._current == "hang_commit":
            await asyncio.Event().wait()
        self.rows.extend(self._pending)


def _retry_count() -> float:
    from prometheus_client import REGISTRY

    return REGISTRY.get_sample_value("pinvi_api_call_log_flush_retries_total") or 0.0


async def test_flush_timeout_is_retried_once_instead_of_dropping_batch() -> None:
    """#721: 2s timeout 한 번에 batch 전체를 버리지 않는다(backoff 뒤 1회 재시도)."""
    factory = FlakyFactory(["hang_enter", None])
    outbox = ApiCallLogOutbox(factory, flush_interval=60, flush_timeout=0.05, retry_backoff=0.01)
    retries_before = _retry_count()
    for i in range(3):
        outbox.submit({"provider": "fixture", "endpoint": f"/{i}"})
    await outbox.close()
    assert factory.attempts == 2
    assert outbox.persisted == 3
    assert outbox.dropped == 0
    assert len(factory.rows) == 3
    assert _retry_count() == retries_before + 1


async def test_second_failure_drops_batch_and_logs_size_and_elapsed() -> None:
    from structlog.testing import capture_logs

    factory = FlakyFactory(["fail_enter", "hang_enter"])
    outbox = ApiCallLogOutbox(factory, flush_interval=60, flush_timeout=0.05, retry_backoff=0.01)
    outbox.submit({"provider": "fixture"})
    outbox.submit({"provider": "fixture"})
    with capture_logs() as logs:
        await outbox.close()
    assert factory.attempts == 2
    assert outbox.dropped == 2
    assert outbox.persisted == 0
    failed = [entry for entry in logs if entry["event"] == "api_call_log.persist_failed"]
    assert len(failed) == 1
    assert failed[0]["error_class"] == "TimeoutError"
    assert failed[0]["dropped"] == 2
    assert failed[0]["attempts"] == 2
    assert failed[0]["during_commit"] is False
    assert failed[0]["elapsed_ms"] >= 50
    assert "secret" not in repr(logs)


async def test_commit_timeout_is_not_retried_to_avoid_duplicate_rows() -> None:
    """commit 도중 timeout은 서버가 이미 commit했을 수 있어 재시도하면 중복 적재다."""
    factory = FlakyFactory(["hang_commit", None])
    outbox = ApiCallLogOutbox(factory, flush_interval=60, flush_timeout=0.05, retry_backoff=0.01)
    outbox.submit({"provider": "fixture"})
    await outbox.close()
    assert factory.attempts == 1
    assert outbox.dropped == 1
    assert factory.rows == []


async def test_flusher_does_not_inherit_request_log_context() -> None:
    """#721: worker task가 처음 submit한 요청의 path/request_id를 물려받지 않는다."""
    import structlog

    factory = FlakyFactory([None])
    outbox = ApiCallLogOutbox(factory, flush_interval=0.001)
    structlog.contextvars.bind_contextvars(path="/admin/etl/summary", request_id="req-1")
    try:
        outbox.submit({"provider": "fixture"})
    finally:
        structlog.contextvars.clear_contextvars()
    await outbox.close()
    assert outbox.persisted == 1
    assert factory.contexts == [{}]


async def test_response_and_exception_cannot_duplicate_same_attempt() -> None:
    factory = RecordingFactory()
    factory.release.set()
    tracker = ApiCallTracker(factory)
    request = httpx.Request("GET", "https://fixture.invalid/duplicate")
    await tracker.on_request(request)
    await tracker.on_response(httpx.Response(503, request=request))
    tracker.on_error(request, RuntimeError())
    await close_api_call_logs(factory)
    assert len(factory.rows) == 1
    assert factory.rows[0]["error_class"] == "HTTPStatusError"


@pytest.mark.parametrize("mode", ["failure", "cancel", "incomplete", "complete"])
async def test_stream_records_final_body_result_once(mode) -> None:
    factory = RecordingFactory()
    factory.release.set()
    started = asyncio.Event()
    closed = asyncio.Event()

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"first"
            started.set()
            if mode == "failure":
                raise httpx.ReadError("token=fixture-private")
            if mode == "cancel":
                await asyncio.Event().wait()
            yield b"last"

        async def aclose(self):
            closed.set()

    async def handler(request):
        return httpx.Response(200, stream=Stream(), request=request)

    async with ApiCallLoggingClient(
        transport=httpx.MockTransport(handler),
        event_hooks=api_call_event_hooks(factory, provider="stream_fixture"),
    ) as client:

        async def read():
            async with client.stream("GET", "https://fixture.invalid/stream") as response:
                if mode == "incomplete":
                    return
                await response.aread()

        if mode == "failure":
            with pytest.raises(httpx.ReadError):
                await read()
        elif mode == "cancel":
            task = asyncio.create_task(read())
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await read()
    await close_api_call_logs(factory)
    assert closed.is_set()
    assert len(factory.rows) == 1
    expected = {
        "failure": "ReadError",
        "cancel": "CancelledError",
        "incomplete": "ResponseNotRead",
        "complete": None,
    }
    assert factory.rows[0]["error_class"] == expected[mode]
    assert "fixture-private" not in repr(factory.rows)
