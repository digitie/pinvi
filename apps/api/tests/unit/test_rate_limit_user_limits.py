"""검증된 사용자 설정만 네 사용자 정책의 실제 상한을 대체한다."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.security import create_access_token
from app.middleware.rate_limit import MemoryRateLimitBackend, RateLimitMiddleware

USER = "00000000-0000-0000-0000-000000000101"
OTHER = "00000000-0000-0000-0000-000000000102"
FIELD = "pinvi_rate_limit_user_limit_overrides"


@pytest.fixture(autouse=True)
def limits(monkeypatch: pytest.MonkeyPatch) -> None:
    values: dict[str, Any] = {
        "enabled": True,
        "backend": "memory",
        "fail_open": False,
        "window_seconds": 60,
        "authenticated_per_minute": 60,
        "feature_search_per_minute": 60,
        "storage_upload_per_minute": 30,
        "trip_export_per_minute": 20,
        "public_per_minute": 60,
        "auth_per_minute": 5,
        "oauth_per_minute": 10,
        "shared_token_per_minute": 60,
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, "pinvi_rate_limit_" + name, value)
    monkeypatch.setitem(settings.__dict__, FIELD, {})
    import app.middleware.rate_limit as module

    fixed = datetime.now(UTC).replace(second=10, microsecond=0)

    class Clock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return fixed

    monkeypatch.setattr(module, "datetime", Clock)


def client(backend: MemoryRateLimitBackend | None = None) -> TestClient:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, backend=backend or MemoryRateLimitBackend())

    @app.api_route("/{rest:path}", methods=["GET", "POST"])
    async def endpoint(rest: str) -> dict[str, str]:
        return {"path": rest}

    return TestClient(app)


def configured(monkeypatch: pytest.MonkeyPatch, cap: int) -> None:
    monkeypatch.setitem(settings.__dict__, FIELD, {USER: cap})


def test_valid_config_and_default() -> None:
    config = Settings(_env_file=None, **{FIELD: {USER: 600}})
    assert getattr(config, FIELD) == {USER: 600}
    assert getattr(Settings(_env_file=None), FIELD) == {}


@pytest.mark.parametrize("value", [True, 0, -1, 4.5, 600.0, "600", None])
def test_config_rejects_non_positive_strict_integer(value: Any) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{FIELD: {USER: value}})


@pytest.mark.parametrize("value", [6001, 1_000_000_000])
def test_config_rejects_effectively_unlimited_cap(value: int) -> None:
    # 설정 하나로 무제한 우회(#653이 없애려던 `allowed`)가 되돌아오지 않도록 상한을 둔다.
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{FIELD: {USER: value}})


def test_config_accepts_cap_at_ceiling() -> None:
    config = Settings(_env_file=None, **{FIELD: {USER: 6000}})
    assert getattr(config, FIELD) == {USER: 6000}


@pytest.mark.parametrize(
    "key", ["not-a-uuid", USER.replace("-", ""), "00000000-0000-0000-0000-000000000A01"]
)
def test_config_requires_canonical_uuid(key: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{FIELD: {key: 600}})


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/trips"),
        ("GET", "/features/in-bounds"),
        ("POST", "/storage/upload-urls"),
        ("GET", "/trips/t/exports/pdf"),
    ],
)
def test_four_user_policies_use_exact_cap(
    monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    from app.middleware.rate_limit import _policy_for_request

    expected = {
        "/trips": "authenticated_default",
        "/features/in-bounds": "feature_search",
        "/storage/upload-urls": "storage_upload_urls",
        "/trips/t/exports/pdf": "trip_exports",
    }
    assert _policy_for_request(path).name == expected[path]
    configured(monkeypatch, 4)
    http = client()
    http.cookies.set("pinvi_access", create_access_token(subject=USER))
    for _ in range(4):
        assert http.request(method, path).status_code == 200
    response = http.request(method, path)
    assert response.status_code == 429
    assert response.json()["error"]["details"]["limit"] == 4
    assert 1 <= int(response.headers["Retry-After"]) <= 60


def test_cap_can_raise_without_changing_default_for_other_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured(monkeypatch, 80)
    http = client()
    http.cookies.set("pinvi_access", create_access_token(subject=USER))
    for _ in range(80):
        assert http.get("/trips").status_code == 200
    assert http.get("/trips").json()["error"]["details"]["limit"] == 80
    http.cookies.set("pinvi_access", create_access_token(subject=OTHER))
    for _ in range(60):
        assert http.get("/trips").status_code == 200
    assert http.get("/trips").json()["error"]["details"]["limit"] == 60


def test_cookie_bearer_and_new_token_share_one_user_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured(monkeypatch, 4)
    http = client()
    first = create_access_token(subject=USER)
    claims = jwt.get_unverified_claims(first)
    claims["jti"] = "fixture-second-token"
    second = jwt.encode(claims, settings.pinvi_jwt_secret_key, algorithm="HS256")
    http.cookies.set("pinvi_access", first)
    assert http.get("/trips").status_code == 200
    http.cookies.clear()
    for _ in range(3):
        assert http.get("/trips", headers={"Authorization": "Bearer " + second}).status_code == 200
    assert http.get("/trips", headers={"Authorization": "Bearer " + first}).status_code == 429


@pytest.mark.parametrize("kind", ["forged", "expired", "bad-subject", "anonymous"])
def test_unverified_identity_never_receives_configured_cap(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    configured(monkeypatch, 80)
    monkeypatch.setattr(settings, "pinvi_rate_limit_authenticated_per_minute", 2)
    token = create_access_token(subject=USER)
    if kind == "forged":
        token = token.rsplit(".", 1)[0] + ".invalid"
    elif kind == "expired":
        claims = jwt.get_unverified_claims(token)
        claims["exp"] = 1
        token = jwt.encode(claims, settings.pinvi_jwt_secret_key, algorithm="HS256")
    elif kind == "bad-subject":
        token = create_access_token(subject="not-a-uuid")
    http = client()
    headers = {} if kind == "anonymous" else {"Authorization": "Bearer " + token}
    assert http.get("/trips", headers=headers).status_code == 200
    assert http.get("/trips", headers=headers).status_code == 200
    response = http.get("/trips", headers=headers)
    assert response.status_code == 429
    assert response.json()["error"]["details"]["limit"] == 2


def test_login_and_bypass_keep_their_own_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    configured(monkeypatch, 80)
    http = client()
    http.cookies.set("pinvi_access", create_access_token(subject=USER))
    for _ in range(5):
        assert http.post("/auth/login", json={"email": "fixture@example.com"}).status_code == 200
    response = http.post("/auth/login", json={"email": "fixture@example.com"})
    assert response.status_code == 429
    assert response.json()["error"]["details"]["limit"] == 5
    for _ in range(8):
        assert http.get("/health").status_code == 200


def test_next_window_recovers_and_secret_rotation_keeps_uuid_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.middleware.rate_limit as module

    configured(monkeypatch, 4)
    now = [datetime(2026, 11, 5, tzinfo=UTC)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return now[0]

    monkeypatch.setattr(module, "datetime", Clock)
    http = client()
    http.cookies.set("pinvi_access", create_access_token(subject=USER))
    for _ in range(4):
        assert http.get("/trips").status_code == 200
    assert http.get("/trips").status_code == 429
    now[0] += timedelta(seconds=60)
    assert http.get("/trips").status_code == 200
    old_hash = module.rate_limit_bucket_hash("authenticated_default", "user:" + USER)
    monkeypatch.setattr(settings, "pinvi_jwt_secret_key", "fixture-rotated-secret-" + "r" * 40)
    http.cookies.set("pinvi_access", create_access_token(subject=USER))
    assert module.rate_limit_bucket_hash("authenticated_default", "user:" + USER) != old_hash
    for _ in range(4):
        assert http.get("/trips").status_code == 200
    assert http.get("/trips").json()["error"]["details"]["limit"] == 4


@pytest.mark.parametrize(
    "path,field",
    [
        ("/public/ping", "pinvi_rate_limit_public_per_minute"),
        ("/auth/oauth/google/start", "pinvi_rate_limit_oauth_per_minute"),
        ("/trips/t/shared/fixture-token", "pinvi_rate_limit_shared_token_per_minute"),
    ],
)
def test_non_user_policies_are_not_elevated(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    field: str,
) -> None:
    configured(monkeypatch, 80)
    monkeypatch.setattr(settings, field, 2)
    http = client()
    http.cookies.set("pinvi_access", create_access_token(subject=USER))
    assert http.get(path).status_code == 200
    assert http.get(path).status_code == 200
    response = http.get(path)
    assert response.status_code == 429
    assert response.json()["error"]["details"]["limit"] == 2


def test_user_policy_counters_are_independent_but_feature_reads_share_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured(monkeypatch, 4)
    http = client()
    http.cookies.set("pinvi_access", create_access_token(subject=USER))
    for path in ("/features/in-bounds", "/weather/markers-in-bounds", "/search", "/search"):
        assert http.get(path).status_code == 200
    assert http.get("/weather/markers-in-bounds").status_code == 429
    for path in ("/trips", "/storage/upload-urls", "/trips/t/exports/pdf"):
        for _ in range(4):
            assert http.get(path).status_code == 200
        assert http.get(path).status_code == 429
