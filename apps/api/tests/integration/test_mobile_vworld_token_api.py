"""모바일 VWorld 토큰 endpoint 통합 — server-issued 키 + Bearer 인증 (ADR-043)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

VWORLD_KEY = "test-vworld-key-1234"
KEY_ATTR = "app.core.config.settings.pinvi_vworld_api_key"


async def test_vworld_token_with_cookie(client, verified_user, auth_cookies, monkeypatch) -> None:
    monkeypatch.setattr(KEY_ATTR, VWORLD_KEY)
    user_id, _ = verified_user

    resp = await client.get("/mobile/vworld/token", cookies=auth_cookies(user_id))

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["api_key"] == VWORLD_KEY
    assert data["key_source"] == "server-issued"
    assert isinstance(data["ttl_seconds"], int)


async def test_vworld_token_with_bearer(client, verified_user, monkeypatch) -> None:
    """모바일은 cookie 대신 Authorization: Bearer — 인증 dep 확장 회귀."""
    from app.core.security import create_access_token

    monkeypatch.setattr(KEY_ATTR, VWORLD_KEY)
    user_id, _ = verified_user
    token = create_access_token(subject=user_id)

    resp = await client.get("/mobile/vworld/token", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["api_key"] == VWORLD_KEY


async def test_vworld_token_requires_auth(client, monkeypatch) -> None:
    monkeypatch.setattr(KEY_ATTR, VWORLD_KEY)

    resp = await client.get("/mobile/vworld/token")

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "TOKEN_INVALID"


async def test_vworld_token_not_configured(
    client, verified_user, auth_cookies, monkeypatch
) -> None:
    monkeypatch.setattr(KEY_ATTR, "")
    user_id, _ = verified_user

    resp = await client.get("/mobile/vworld/token", cookies=auth_cookies(user_id))

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "VWORLD_NOT_CONFIGURED"
