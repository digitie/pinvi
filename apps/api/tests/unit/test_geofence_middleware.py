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


@pytest.fixture(autouse=True)
def _reset_geofence_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tripmate_geofence_enabled", False)
    monkeypatch.setattr(settings, "tripmate_geofence_allowed_countries", ["KR"])
    monkeypatch.setattr(settings, "tripmate_geofence_country_header", "CF-IPCountry")
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


def test_geofence_disabled_allows_unknown_country(client: TestClient) -> None:
    response = client.get("/private")
    assert response.status_code == 200


def test_geofence_allows_kr_country(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tripmate_geofence_enabled", True)
    response = client.get("/private", headers={"CF-IPCountry": "KR"})
    assert response.status_code == 200


def test_geofence_blocks_non_kr_country(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "tripmate_geofence_enabled", True)
    response = client.get("/private", headers={"CF-IPCountry": "US"})
    assert response.status_code == 451
    assert response.json()["error"]["code"] == "GEO_BLOCKED"
    assert response.json()["error"]["details"]["detected_country"] == "US"
    assert response.headers["X-TripMate-Geofence"] == "blocked"


def test_geofence_bypasses_health(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tripmate_geofence_enabled", True)
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
    monkeypatch.setattr(settings, "tripmate_geofence_enabled", True)
    client.app.state.geofence_role_resolver = lambda subject: (
        ["user", "admin"] if subject == ADMIN_USER_ID else ["user"]
    )
    token = create_access_token(subject=ADMIN_USER_ID)
    client.cookies.set("tripmate_access", token)
    response = client.get(
        "/private",
        headers={"CF-IPCountry": "US"},
    )
    assert response.status_code == 200


def test_geofence_ignores_token_role_claim_without_db_role(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "tripmate_geofence_enabled", True)
    client.app.state.geofence_role_resolver = lambda _subject: ["user"]
    token = create_access_token(subject=PLAIN_USER_ID, extra={"roles": ["admin"]})
    client.cookies.set("tripmate_access", token)

    response = client.get(
        "/private",
        headers={"CF-IPCountry": "US"},
    )

    assert response.status_code == 451
