"""ADR-018 FastAPI geofence fallback 단위 테스트."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token
from app.middleware.geofence import GeofenceMiddleware

ADMIN_USER_ID = "00000000-0000-0000-0000-000000000001"
PLAIN_USER_ID = "00000000-0000-0000-0000-000000000002"
TRUSTED_PROXY_SECRET = "test-geofence-proxy-secret"


@pytest.fixture(autouse=True)
def _reset_geofence_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tripmate_geofence_enabled", False)
    monkeypatch.setattr(settings, "tripmate_geofence_allowed_countries", ["KR"])
    monkeypatch.setattr(settings, "tripmate_geofence_country_header", "CF-IPCountry")
    monkeypatch.setattr(
        settings, "tripmate_geofence_trusted_proxy_header", "X-TripMate-Geofence-Proxy"
    )
    monkeypatch.setattr(settings, "tripmate_geofence_trusted_proxy_secret", "")
    monkeypatch.setattr(settings, "tripmate_geofence_block_unknown", False)
    monkeypatch.setattr(
        settings,
        "tripmate_geofence_bypass_paths",
        ["/health", "/health/db", "/docs", "/redoc", "/openapi.json"],
    )


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.add_middleware(GeofenceMiddleware)

    @app.get("/private")
    async def private() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def _trusted_country_headers(country: str) -> dict[str, str]:
    return {
        "CF-IPCountry": country,
        "X-TripMate-Geofence-Proxy": TRUSTED_PROXY_SECRET,
    }


def _enable_strict_geofence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tripmate_geofence_enabled", True)
    monkeypatch.setattr(settings, "tripmate_geofence_block_unknown", True)
    monkeypatch.setattr(settings, "tripmate_geofence_trusted_proxy_secret", TRUSTED_PROXY_SECRET)


def test_geofence_disabled_allows_unknown_country(client: TestClient) -> None:
    response = client.get("/private")
    assert response.status_code == 200


def test_geofence_allows_kr_country(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_strict_geofence(monkeypatch)
    response = client.get("/private", headers=_trusted_country_headers("KR"))
    assert response.status_code == 200


def test_geofence_blocks_non_kr_country(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_strict_geofence(monkeypatch)
    response = client.get("/private", headers=_trusted_country_headers("US"))
    assert response.status_code == 451
    assert response.json()["error"]["code"] == "GEO_BLOCKED"
    assert response.json()["error"]["details"]["detected_country"] == "US"
    assert response.headers["X-TripMate-Geofence"] == "blocked"


def test_geofence_blocks_spoofed_country_without_trusted_proxy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_strict_geofence(monkeypatch)
    response = client.get("/private", headers={"CF-IPCountry": "KR"})
    assert response.status_code == 451
    assert response.json()["error"]["details"]["detected_country"] == "UNKNOWN"


def test_geofence_blocks_spoofed_country_with_wrong_proxy_secret(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_strict_geofence(monkeypatch)
    response = client.get(
        "/private",
        headers={
            "CF-IPCountry": "KR",
            "X-TripMate-Geofence-Proxy": "wrong-secret",
        },
    )
    assert response.status_code == 451
    assert response.json()["error"]["details"]["detected_country"] == "UNKNOWN"


def test_geofence_bypasses_health(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_strict_geofence(monkeypatch)
    response = client.get("/health", headers={"CF-IPCountry": "US"})
    assert response.status_code == 200


def test_geofence_blocks_unknown_when_strict(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "tripmate_geofence_enabled", True)
    monkeypatch.setattr(settings, "tripmate_geofence_block_unknown", True)
    response = client.get("/private")
    assert response.status_code == 451
    assert response.json()["error"]["details"]["detected_country"] == "UNKNOWN"


def test_geofence_allows_admin_role_from_db_resolver(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_strict_geofence(monkeypatch)
    client.app.state.geofence_role_resolver = lambda subject: (
        ["user", "admin"] if subject == ADMIN_USER_ID else ["user"]
    )
    token = create_access_token(subject=ADMIN_USER_ID)
    client.cookies.set("tripmate_access", token)
    response = client.get(
        "/private",
        headers=_trusted_country_headers("US"),
    )
    assert response.status_code == 200


def test_geofence_ignores_token_role_claim_without_db_role(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_strict_geofence(monkeypatch)
    client.app.state.geofence_role_resolver = lambda _subject: ["user"]
    token = create_access_token(subject=PLAIN_USER_ID, extra={"roles": ["admin"]})
    client.cookies.set("tripmate_access", token)

    response = client.get(
        "/private",
        headers=_trusted_country_headers("US"),
    )

    assert response.status_code == 451
