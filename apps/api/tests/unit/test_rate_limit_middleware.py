"""HTTP rate-limit middleware tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token
from app.middleware.rate_limit import (
    MemoryRateLimitBackend,
    RateLimitMiddleware,
    _policy_for_request,
)

USER_ID = "00000000-0000-0000-0000-000000000101"


@pytest.fixture(autouse=True)
def _reset_rate_limit_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pinvi_rate_limit_enabled", True)
    monkeypatch.setattr(settings, "pinvi_rate_limit_backend", "memory")
    monkeypatch.setattr(settings, "pinvi_rate_limit_fail_open", False)
    monkeypatch.setattr(settings, "pinvi_rate_limit_window_seconds", 60)
    monkeypatch.setattr(settings, "pinvi_rate_limit_public_per_minute", 60)
    monkeypatch.setattr(settings, "pinvi_rate_limit_authenticated_per_minute", 60)
    monkeypatch.setattr(settings, "pinvi_rate_limit_auth_per_minute", 5)
    monkeypatch.setattr(settings, "pinvi_rate_limit_oauth_per_minute", 10)
    monkeypatch.setattr(settings, "pinvi_rate_limit_storage_upload_per_minute", 30)
    monkeypatch.setattr(settings, "pinvi_rate_limit_feature_search_per_minute", 60)
    monkeypatch.setattr(settings, "pinvi_rate_limit_trip_export_per_minute", 20)
    monkeypatch.setattr(settings, "pinvi_rate_limit_shared_token_per_minute", 60)
    monkeypatch.setattr(settings, "pinvi_rate_limit_body_peek_max_bytes", 65536)
    monkeypatch.setattr(settings, "pinvi_rate_limit_client_ip_header", "")
    monkeypatch.setattr(settings, "pinvi_rate_limit_bypass_paths", ["/health", "/metrics"])


def _client(backend: MemoryRateLimitBackend | None = None) -> TestClient:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, backend=backend or MemoryRateLimitBackend())

    @app.get("/public/ping")
    async def public_ping() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/auth/login")
    async def login(request: Request) -> dict[str, object]:
        body = await request.json()
        return {"email": body.get("email")}

    @app.get("/trips")
    async def trips() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def test_weather_markers_in_bounds_shares_feature_search_bucket() -> None:
    """T-368 — 같은 pan/zoom 이벤트로 병렬 호출되므로 `/features/in-bounds`와 같은
    버킷이어야 한다. 다르면 빠른 팬 중 weather marker만 조용히 사라진다."""

    feature_policy = _policy_for_request("/features/in-bounds")
    search_policy = _policy_for_request("/search")
    weather_policy = _policy_for_request("/weather/markers-in-bounds")

    assert weather_policy.name == feature_policy.name == search_policy.name == "feature_search"


def test_public_paths_are_limited_by_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pinvi_rate_limit_public_per_minute", 2)
    client = _client()

    assert client.get("/public/ping").status_code == 200
    assert client.get("/public/ping").status_code == 200
    response = client.get("/public/ping")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    assert response.headers["Retry-After"].isdigit()


def test_auth_low_policy_uses_email_dimension_and_replays_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_rate_limit_auth_per_minute", 1)
    client = _client()

    first = client.post("/auth/login", json={"email": "a@example.com", "password": "x"})
    second = client.post("/auth/login", json={"email": "a@example.com", "password": "x"})
    other_email = client.post("/auth/login", json={"email": "b@example.com", "password": "x"})

    assert first.status_code == 200
    assert first.json()["email"] == "a@example.com"
    assert second.status_code == 429
    assert other_email.status_code == 200
    assert other_email.json()["email"] == "b@example.com"


def test_authenticated_paths_use_access_token_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_rate_limit_authenticated_per_minute", 1)
    client = _client()
    client.cookies.set("pinvi_access", create_access_token(subject=USER_ID))

    assert client.get("/trips").status_code == 200
    assert client.get("/trips").status_code == 429


def test_bypass_paths_are_not_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pinvi_rate_limit_authenticated_per_minute", 1)
    client = _client()

    for _ in range(5):
        response = client.get("/health")
        assert response.status_code == 200


class RaisingBackend:
    async def hit(self, **_: object) -> int:
        from sqlalchemy.exc import SQLAlchemyError

        raise SQLAlchemyError("rate store down")


def test_backend_failure_can_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pinvi_rate_limit_fail_open", True)
    client = _client(backend=RaisingBackend())  # type: ignore[arg-type]

    assert client.get("/public/ping").status_code == 200


def test_backend_failure_fails_closed_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pinvi_rate_limit_fail_open", False)
    client = _client(backend=RaisingBackend())  # type: ignore[arg-type]

    response = client.get("/public/ping")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


@pytest.mark.parametrize("fail_open", [False, True])
@pytest.mark.parametrize("response_started", [False, True])
@pytest.mark.asyncio
async def test_allowed_override_never_catches_or_replays_handler_db_error(
    monkeypatch: pytest.MonkeyPatch, fail_open: bool, response_started: bool
) -> None:
    import uuid
    from datetime import UTC, datetime, timedelta

    from sqlalchemy.exc import SQLAlchemyError

    import app.middleware.rate_limit as module

    monkeypatch.setattr(settings, "pinvi_rate_limit_backend", "postgres")
    monkeypatch.setattr(settings, "pinvi_rate_limit_fail_open", fail_open)
    decision = module.RateLimitOverrideDecision(
        override_id=uuid.uuid4(),
        action="allowed",
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )

    async def check(_self: object, **_: object) -> module.RateLimitStoreResult:
        return module.RateLimitStoreResult(count=0, override=decision)

    monkeypatch.setattr(module.PostgresRateLimitBackend, "check", check)
    calls = 0
    sent = []
    failure = SQLAlchemyError("handler fixture database error")

    async def handler(scope, receive, send):
        nonlocal calls
        calls += 1
        if response_started:
            await send({"type": "http.response.start", "status": 200, "headers": []})
        raise failure

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "GET", "path": "/trips", "headers": []}
    with pytest.raises(SQLAlchemyError) as raised:
        await RateLimitMiddleware(handler)(scope, receive, send)
    assert raised.value is failure
    assert calls == 1
    assert sent == (
        [{"type": "http.response.start", "status": 200, "headers": []}] if response_started else []
    )


@pytest.mark.parametrize("fail_open", [False, True])
def test_allowed_handler_failure_is_server_error_not_store_unavailable(
    monkeypatch: pytest.MonkeyPatch, fail_open: bool
) -> None:
    import uuid
    from datetime import UTC, datetime, timedelta

    from sqlalchemy.exc import SQLAlchemyError

    import app.middleware.rate_limit as module

    monkeypatch.setattr(settings, "pinvi_rate_limit_backend", "postgres")
    monkeypatch.setattr(settings, "pinvi_rate_limit_fail_open", fail_open)

    async def check(_self: object, **_: object) -> module.RateLimitStoreResult:
        decision = module.RateLimitOverrideDecision(
            override_id=uuid.uuid4(),
            action="allowed",
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        )
        return module.RateLimitStoreResult(count=0, override=decision)

    monkeypatch.setattr(module.PostgresRateLimitBackend, "check", check)
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)
    calls = 0

    @app.get("/trips")
    async def handler():
        nonlocal calls
        calls += 1
        raise SQLAlchemyError("fixture handler failure")

    response = TestClient(app, raise_server_exceptions=False).get("/trips")
    assert response.status_code == 500
    assert "요청 한도" not in response.text
    assert calls == 1


@pytest.mark.parametrize("fail_open", [False, True])
@pytest.mark.asyncio
async def test_blocked_response_send_error_never_runs_handler_or_sends_fallback(
    monkeypatch: pytest.MonkeyPatch, fail_open: bool
) -> None:
    import uuid
    from datetime import UTC, datetime, timedelta

    from sqlalchemy.exc import SQLAlchemyError

    import app.middleware.rate_limit as module

    monkeypatch.setattr(settings, "pinvi_rate_limit_backend", "postgres")
    monkeypatch.setattr(settings, "pinvi_rate_limit_fail_open", fail_open)

    async def check(_self: object, **_: object) -> module.RateLimitStoreResult:
        decision = module.RateLimitOverrideDecision(
            override_id=uuid.uuid4(),
            action="blocked",
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        )
        return module.RateLimitStoreResult(count=0, override=decision)

    monkeypatch.setattr(module.PostgresRateLimitBackend, "check", check)
    calls = 0
    statuses = []
    failure = SQLAlchemyError("fixture send failure")

    async def handler(scope, receive, send):
        nonlocal calls
        calls += 1

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            statuses.append(message["status"])
        raise failure

    scope = {"type": "http", "method": "GET", "path": "/trips", "headers": []}
    with pytest.raises(SQLAlchemyError) as raised:
        await RateLimitMiddleware(handler)(scope, receive, send)
    assert raised.value is failure
    assert calls == 0
    assert statuses == [429]


@pytest.mark.parametrize("fail_open", [False, True])
def test_only_real_store_failures_use_fallback_and_log_safe_exception_class(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    fail_open: bool,
) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    import app.middleware.rate_limit as module

    monkeypatch.setattr(settings, "pinvi_rate_limit_backend", "postgres")
    monkeypatch.setattr(settings, "pinvi_rate_limit_fail_open", fail_open)

    async def check(_self: object, **_: object) -> module.RateLimitStoreResult:
        raise SQLAlchemyError("fixture-private-sql-param")

    monkeypatch.setattr(module.PostgresRateLimitBackend, "check", check)
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)
    calls = 0

    @app.get("/trips")
    async def handler():
        nonlocal calls
        calls += 1
        return {"ok": True}

    response = TestClient(app).get("/trips")
    assert response.status_code == (200 if fail_open else 503)
    assert calls == int(fail_open)
    records = [r for r in caplog.records if r.message == "rate_limit.store_unavailable"]
    assert len(records) == 1
    assert records[0].error_type == "SQLAlchemyError"
    assert "fixture-private-sql-param" not in str(records[0].__dict__)
    assert "fixture-private-sql-param" not in response.text
