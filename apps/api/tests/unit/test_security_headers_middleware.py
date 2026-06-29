"""Security header middleware tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.core.config import settings
from app.middleware.security_headers import SecurityHeadersMiddleware


def _client() -> TestClient:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/docs")
    async def docs() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


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


def test_hsts_is_enabled_for_forwarded_https(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "pinvi_environment", "development")
    response = _client().get("/health", headers={"X-Forwarded-Proto": "https"})

    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


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
