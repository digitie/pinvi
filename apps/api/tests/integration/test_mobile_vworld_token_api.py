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


async def _share_token(client, cookies, *, title: str = "공유 지도") -> tuple[str, str, str]:  # type: ignore[no-untyped-def]
    created = await client.post("/trips", json={"title": title}, cookies=cookies)
    assert created.status_code == 201, created.text
    trip_id = created.json()["data"]["trip_id"]
    issued = await client.post(
        f"/trips/{trip_id}/share-tokens",
        json={"visibility": "view_only"},
        cookies=cookies,
    )
    assert issued.status_code == 201, issued.text
    share = issued.json()["data"]
    return trip_id, share["token"], share["share_id"]


async def test_shared_vworld_token_requires_valid_share_token_not_login(
    client, verified_user, auth_cookies, monkeypatch
) -> None:
    """로그인 없는 공유 화면 — 그 여행의 유효한 공유 토큰이면 같은 키, 아니면 404."""
    monkeypatch.setattr(KEY_ATTR, VWORLD_KEY)
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id, token, share_id = await _share_token(client, cookies)
    other_trip_id, _, _ = await _share_token(client, cookies, title="다른 여행")

    # 로그인 쿠키·Bearer 없이.
    resp = await client.get(f"/mobile/shared/{trip_id}/{token}/vworld/token")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["api_key"] == VWORLD_KEY
    assert data["key_source"] == "server-issued"

    wrong_trip = await client.get(f"/mobile/shared/{other_trip_id}/{token}/vworld/token")
    assert wrong_trip.status_code == 404
    wrong_token = await client.get(f"/mobile/shared/{trip_id}/not-a-token/vworld/token")
    assert wrong_token.status_code == 404
    assert VWORLD_KEY not in wrong_token.text

    revoked = await client.delete(f"/trips/{trip_id}/share-tokens/{share_id}", cookies=cookies)
    assert revoked.status_code == 204
    after_revoke = await client.get(f"/mobile/shared/{trip_id}/{token}/vworld/token")
    assert after_revoke.status_code == 404


async def test_shared_vworld_token_not_configured(
    client, verified_user, auth_cookies, monkeypatch
) -> None:
    monkeypatch.setattr(KEY_ATTR, "")
    user_id, _ = verified_user
    trip_id, token, _ = await _share_token(client, auth_cookies(user_id))

    resp = await client.get(f"/mobile/shared/{trip_id}/{token}/vworld/token")

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "VWORLD_NOT_CONFIGURED"


async def test_transport_still_requires_login_for_share_viewers(client) -> None:
    """공유 화면용 지도 키를 열어도 교통 endpoint는 그대로 로그인 필요(NEAR-027 — 공유 화면은 교통 없음)."""
    resp = await client.get("/transport/status")
    assert resp.status_code == 401
