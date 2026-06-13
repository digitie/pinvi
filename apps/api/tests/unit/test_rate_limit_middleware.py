"""HTTP rate-limit middleware tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token
from app.middleware.rate_limit import MemoryRateLimitBackend, RateLimitMiddleware

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
