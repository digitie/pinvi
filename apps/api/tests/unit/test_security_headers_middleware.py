"""Security header middleware tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.core.config import settings
from app.middleware.security_headers import (
    SecurityHeadersMiddleware,
    security_headers_exception_handler,
)


def _client() -> TestClient:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SecurityHeadersMiddleware)
    # Mirror real wiring (main.py): unhandled errors → 500 with security headers via the
    # exception handler (ServerErrorMiddleware still re-raises). The middleware itself does
    # NOT catch — that would swallow exceptions and break rollback-on-error tests.
    app.add_exception_handler(Exception, security_headers_exception_handler)

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/docs")
    async def docs() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/boom")
    async def boom() -> dict[str, bool]:
        raise RuntimeError("unhandled boom")

    # raise_server_exceptions=False so the TestClient returns the 500 response
    # instead of re-raising the underlying exception.
    return TestClient(app, raise_server_exceptions=False)


def _cors_client() -> TestClient:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:12805"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    return TestClient(app)


def test_security_headers_are_added_to_api_responses(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "pinvi_environment", "development")
    response = _client().get("/health")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Permissions-Policy"] == "geolocation=(self)"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Content-Security-Policy"] == (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )
    assert "Strict-Transport-Security" not in response.headers


def test_hsts_is_enabled_for_production(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "pinvi_environment", "production")
    response = _client().get("/health")

    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


def test_hsts_is_not_enabled_for_client_supplied_forwarded_proto(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # X-Forwarded-Proto is attacker-controllable, so it must NOT enable HSTS
    # outside production (#344).
    monkeypatch.setattr(settings, "pinvi_environment", "development")
    response = _client().get("/health", headers={"X-Forwarded-Proto": "https"})

    assert "Strict-Transport-Security" not in response.headers


def test_security_headers_applied_to_unhandled_500(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "pinvi_environment", "development")
    response = _client().get("/boom")

    assert response.status_code == 500
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Content-Security-Policy"] == (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )


def test_csp_is_skipped_for_docs_paths(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "pinvi_environment", "development")
    response = _client().get("/docs")

    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" not in response.headers


def test_cors_preflight_keeps_security_headers(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "pinvi_environment", "development")
    response = _cors_client().options(
        "/health",
        headers={
            "Origin": "http://127.0.0.1:12805",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:12805"
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_cors_preflight_does_not_reflect_attacker_origin(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "pinvi_environment", "development")
    response = _cors_client().options(
        "/health",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    # A disallowed origin must not be echoed back and must not be granted creds (#342).
    assert response.headers.get("Access-Control-Allow-Origin") != "https://evil.example.com"
    assert response.headers.get("Access-Control-Allow-Origin") != "*"
