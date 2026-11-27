"""로그인 유지(remember me) — 세션 수명·절대 상한·회전 승계·재사용 감지·폐기·OAuth state 승계.

`docs/api/auth.md` §3.5. 유지하지 않은 세션은 기존처럼 7일 미끄럼이고, 유지한 세션은 로그인부터 365일이다.
access JWT는 둘 다 10분이다. 모든 계열은 로그인 + 365일을 넘겨 연장되지 않는다.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.security import hash_password
from app.models.oauth_identity import OAuthLoginState, OAuthMobileExchange
from app.models.session import UserSession
from app.models.user import User
from app.services.admin_users import disable_user
from app.services.auth_session import (
    REFRESH_REUSE_GRACE,
    RefreshTokenExpiredError,
    RefreshTokenInvalidError,
    hash_session_token,
    lock_user_sessions,
    refresh_user_session,
    revoke_active_user_sessions,
)
from app.services.oauth_google import GoogleClaims, issue_login_state

pytestmark = pytest.mark.asyncio

_DAY = 24 * 60 * 60
_PASSWORD = "remember-pw-12345"


async def _seed_user(session_factory, *, roles: list[str] | None = None) -> tuple[uuid.UUID, str]:  # type: ignore[no-untyped-def]
    email = f"remember_{uuid.uuid4().hex[:8]}@example.com"
    async with session_factory() as db:
        user = User(
            email=email,
            password_hash=hash_password(_PASSWORD),
            nickname="remember-user",
            status="active",
            email_verified_at=datetime.now(UTC),
            roles=roles or ["user"],
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id, email


async def _login(client, email: str, *, remember_me: bool | None):  # type: ignore[no-untyped-def]
    body: dict[str, object] = {"email": email, "password": _PASSWORD}
    if remember_me is not None:
        body["remember_me"] = remember_me
    resp = await client.post("/auth/login", json=body)
    assert resp.status_code == 200, resp.text
    client.cookies.clear()
    return resp


def _cookie_max_age(resp, name: str) -> int:  # type: ignore[no-untyped-def]
    for header in resp.headers.get_list("set-cookie"):
        if header.startswith(f"{name}="):
            assert "HttpOnly" in header
            assert "SameSite=lax" in header
            match = re.search(r"Max-Age=(\d+)", header)
            assert match is not None, header
            return int(match.group(1))
    raise AssertionError(f"{name} cookie 없음")


async def _session_for(session_factory, refresh_token: str) -> UserSession:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        row = await db.scalar(
            select(UserSession).where(
                UserSession.session_token_hash == hash_session_token(refresh_token)
            )
        )
        assert row is not None
        return row


def _assert_close(actual: datetime, expected: datetime, *, seconds: int = 60) -> None:
    assert abs((actual - expected).total_seconds()) <= seconds, (actual, expected)


async def _rotate(session_factory, refresh_token: str) -> str:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        try:
            await refresh_user_session(db, refresh_token=refresh_token)
        except (RefreshTokenExpiredError, RefreshTokenInvalidError) as exc:
            return exc.code
        return "OK"


def _claims(*, sub: str, email: str) -> GoogleClaims:
    return GoogleClaims(
        provider_user_id=sub, email=email, email_verified=True, display_name="구글 사용자"
    )


async def test_login_without_remember_keeps_seven_day_sliding_session(
    client, session_factory
) -> None:  # type: ignore[no-untyped-def]
    _user_id, email = await _seed_user(session_factory)
    now = datetime.now(UTC)

    resp = await _login(client, email, remember_me=None)

    assert _cookie_max_age(resp, "pinvi_access") == settings.pinvi_access_token_minutes * 60
    assert abs(_cookie_max_age(resp, "pinvi_refresh") - 7 * _DAY) <= 60
    row = await _session_for(session_factory, resp.cookies["pinvi_refresh"])
    assert row.remember_me is False
    _assert_close(row.expires_at, now + timedelta(days=7))
    _assert_close(row.absolute_expires_at, now + timedelta(days=365))


async def test_login_with_remember_issues_one_year_session_but_short_access(
    client, session_factory
) -> None:  # type: ignore[no-untyped-def]
    _user_id, email = await _seed_user(session_factory)
    now = datetime.now(UTC)

    resp = await _login(client, email, remember_me=True)

    assert _cookie_max_age(resp, "pinvi_access") == settings.pinvi_access_token_minutes * 60
    assert abs(_cookie_max_age(resp, "pinvi_refresh") - 365 * _DAY) <= 60
    row = await _session_for(session_factory, resp.cookies["pinvi_refresh"])
    assert row.remember_me is True
    assert row.expires_at == row.absolute_expires_at
    _assert_close(row.absolute_expires_at, now + timedelta(days=365))


async def test_remembered_refresh_rotates_in_family_without_extending_absolute(
    client, session_factory
) -> None:  # type: ignore[no-untyped-def]
    _user_id, email = await _seed_user(session_factory)
    login = await _login(client, email, remember_me=True)
    first = await _session_for(session_factory, login.cookies["pinvi_refresh"])
    # 로그인 뒤 100일이 흐른 계열처럼 — 절대 만료를 앞당겨 둔다.
    shortened = datetime.now(UTC) + timedelta(days=265)
    async with session_factory() as db:
        await db.execute(
            update(UserSession)
            .where(UserSession.session_id == first.session_id)
            .values(expires_at=shortened, absolute_expires_at=shortened)
        )
        await db.commit()

    refreshed = await client.post(
        "/auth/refresh", cookies={"pinvi_refresh": login.cookies["pinvi_refresh"]}
    )

    assert refreshed.status_code == 200, refreshed.text
    assert abs(_cookie_max_age(refreshed, "pinvi_refresh") - 265 * _DAY) <= 60
    second = await _session_for(session_factory, refreshed.cookies["pinvi_refresh"])
    assert second.family_id == first.family_id
    assert second.remember_me is True
    assert second.absolute_expires_at == shortened
    assert second.expires_at == shortened
    old = await _session_for(session_factory, login.cookies["pinvi_refresh"])
    assert old.revoked_at is not None
    assert old.rotated_at is not None


async def test_unremembered_sliding_refresh_is_capped_by_absolute_expiry(
    client, session_factory
) -> None:  # type: ignore[no-untyped-def]
    _user_id, email = await _seed_user(session_factory)
    login = await _login(client, email, remember_me=False)
    first = await _session_for(session_factory, login.cookies["pinvi_refresh"])
    cap = datetime.now(UTC) + timedelta(days=2)
    async with session_factory() as db:
        await db.execute(
            update(UserSession)
            .where(UserSession.session_id == first.session_id)
            .values(expires_at=cap, absolute_expires_at=cap)
        )
        await db.commit()

    refreshed = await client.post(
        "/auth/refresh", cookies={"pinvi_refresh": login.cookies["pinvi_refresh"]}
    )

    assert refreshed.status_code == 200, refreshed.text
    second = await _session_for(session_factory, refreshed.cookies["pinvi_refresh"])
    assert second.remember_me is False
    # 7일 미끄럼이 절대 상한(2일 뒤)을 넘지 못한다.
    assert second.expires_at == cap
    assert abs(_cookie_max_age(refreshed, "pinvi_refresh") - 2 * _DAY) <= 60


@pytest.mark.parametrize("role", ["admin", "operator", "cpo"])
async def test_privileged_roles_do_not_get_remembered_sessions(
    client, session_factory, role: str
) -> None:  # type: ignore[no-untyped-def]
    _user_id, email = await _seed_user(session_factory, roles=["user", role])
    now = datetime.now(UTC)

    resp = await _login(client, email, remember_me=True)

    row = await _session_for(session_factory, resp.cookies["pinvi_refresh"])
    assert row.remember_me is False
    _assert_close(row.expires_at, now + timedelta(days=7))
    assert abs(_cookie_max_age(resp, "pinvi_refresh") - 7 * _DAY) <= 60


async def test_late_reuse_of_rotated_token_revokes_whole_family_only(
    client, session_factory
) -> None:  # type: ignore[no-untyped-def]
    user_id, email = await _seed_user(session_factory)
    stolen = (await _login(client, email, remember_me=True)).cookies["pinvi_refresh"]
    other_device = (await _login(client, email, remember_me=True)).cookies["pinvi_refresh"]
    rotated = await client.post("/auth/refresh", cookies={"pinvi_refresh": stolen})
    assert rotated.status_code == 200
    current = rotated.cookies["pinvi_refresh"]
    client.cookies.clear()
    async with session_factory() as db:
        version_before = await db.scalar(
            select(User.access_token_version).where(User.user_id == user_id)
        )
        # 회전 후 유예가 지난 뒤 옛 토큰이 다시 온다(탈취된 사본).
        await db.execute(
            update(UserSession)
            .where(UserSession.session_token_hash == hash_session_token(stolen))
            .values(rotated_at=datetime.now(UTC) - REFRESH_REUSE_GRACE - timedelta(seconds=5))
        )
        await db.commit()

    replay = await client.post("/auth/refresh", cookies={"pinvi_refresh": stolen})

    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "TOKEN_EXPIRED"
    assert (await _session_for(session_factory, current)).revoked_at is not None
    client.cookies.clear()
    after_current = await client.post("/auth/refresh", cookies={"pinvi_refresh": current})
    assert after_current.status_code == 401
    # 다른 계열(다른 기기 로그인)은 살아 있다.
    assert (await _session_for(session_factory, other_device)).revoked_at is None
    async with session_factory() as db:
        version_after = await db.scalar(
            select(User.access_token_version).where(User.user_id == user_id)
        )
    assert version_after == (version_before or 0) + 1


async def test_reuse_within_grace_does_not_revoke_family(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    """두 탭이 거의 동시에 갱신하는 경우 — 진 쪽은 401만 받고 이긴 쪽 세션은 산다."""
    _user_id, email = await _seed_user(session_factory)
    old = (await _login(client, email, remember_me=True)).cookies["pinvi_refresh"]
    rotated = await client.post("/auth/refresh", cookies={"pinvi_refresh": old})
    assert rotated.status_code == 200
    current = rotated.cookies["pinvi_refresh"]
    client.cookies.clear()

    replay = await client.post("/auth/refresh", cookies={"pinvi_refresh": old})

    assert replay.status_code == 401
    assert (await _session_for(session_factory, current)).revoked_at is None


async def test_logout_revokes_remembered_session(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    _user_id, email = await _seed_user(session_factory)
    login = await _login(client, email, remember_me=True)
    refresh_token = login.cookies["pinvi_refresh"]

    out = await client.post(
        "/auth/logout",
        cookies={"pinvi_refresh": refresh_token, "pinvi_access": login.cookies["pinvi_access"]},
    )

    assert out.status_code == 204
    client.cookies.clear()
    assert (await _session_for(session_factory, refresh_token)).revoked_at is not None
    again = await client.post("/auth/refresh", cookies={"pinvi_refresh": refresh_token})
    assert again.status_code == 401


async def test_admin_disable_revokes_remembered_sessions(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    user_id, email = await _seed_user(session_factory)
    admin_id, _admin_email = await _seed_user(session_factory, roles=["user", "admin"])
    refresh_token = (await _login(client, email, remember_me=True)).cookies["pinvi_refresh"]

    async with session_factory() as db:
        await disable_user(db, user_id=user_id, actor_id=admin_id)
        await db.commit()

    assert (await _session_for(session_factory, refresh_token)).revoked_at is not None
    resp = await client.post("/auth/refresh", cookies={"pinvi_refresh": refresh_token})
    assert resp.status_code == 401


async def test_password_reset_revokes_remembered_sessions(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    from app.models.email_queue import EmailQueue

    user_id, email = await _seed_user(session_factory)
    refresh_token = (await _login(client, email, remember_me=True)).cookies["pinvi_refresh"]
    assert (
        await client.post("/auth/password/reset-request", json={"email": email})
    ).status_code == 200
    async with session_factory() as db:
        queue_row = await db.scalar(
            select(EmailQueue).where(
                EmailQueue.user_id == user_id, EmailQueue.template == "reset_password"
            )
        )
        assert queue_row is not None
        token = parse_qs(urlparse(str(queue_row.payload["reset_url"])).query)["token"][0]

    reset = await client.post(
        "/auth/password/reset", json={"token": token, "new_password": "new-remember-pw-67890"}
    )

    assert reset.status_code == 200, reset.text
    client.cookies.clear()
    assert (await _session_for(session_factory, refresh_token)).revoked_at is not None
    resp = await client.post("/auth/refresh", cookies={"pinvi_refresh": refresh_token})
    assert resp.status_code == 401


async def test_oauth_start_stores_remember_choice_in_state(
    client, session_factory, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "pinvi_google_oauth_client_id", "test-client")
    monkeypatch.setattr(settings, "pinvi_google_oauth_client_secret", "test-secret")

    resp = await client.post(
        "/auth/oauth/google/start",
        json={"return_to": "/trips", "mode": "login", "remember_me": True},
    )

    assert resp.status_code == 200
    authorize_url = resp.json()["data"]["authorize_url"]
    params = parse_qs(urlparse(authorize_url).query)
    # 선택 값은 provider로 가는 URL에 싣지 않는다 — 서버 state row에만 있다.
    assert "remember_me" not in params
    state_hash = hashlib.sha256(params["state"][0].encode("utf-8")).hexdigest()
    async with session_factory() as db:
        row = await db.scalar(
            select(OAuthLoginState).where(OAuthLoginState.state_hash == state_hash)
        )
        assert row is not None
        assert row.remember_me is True


@pytest.mark.parametrize("remember_me", [True, False])
async def test_oauth_callback_uses_state_remember_choice(
    client, session_factory, monkeypatch, remember_me: bool
) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        state, _nonce, _verifier = await issue_login_state(
            db, mode="login", return_to="/trips", remember_me=remember_me
        )

    async def fake_exchange(**_kwargs) -> GoogleClaims:  # type: ignore[no-untyped-def]
        return _claims(
            sub=f"remember-{uuid.uuid4().hex[:8]}", email=f"g{uuid.uuid4().hex[:8]}@gmail.com"
        )

    monkeypatch.setattr("app.api.v1.oauth.exchange_code_for_claims", fake_exchange)

    resp = await client.get(
        f"/auth/oauth/google/callback?code=test-code&state={state}", follow_redirects=False
    )

    assert resp.status_code == 303
    row = await _session_for(session_factory, resp.cookies["pinvi_refresh"])
    assert row.remember_me is remember_me
    expected_days = 365 if remember_me else 7
    assert abs(_cookie_max_age(resp, "pinvi_refresh") - expected_days * _DAY) <= 60


async def test_oauth_callback_ignores_forged_remember_query(
    client, session_factory, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """callback 쿼리에 `remember_me=true`를 덧붙여도 state가 false면 1년 세션이 나오지 않는다."""
    async with session_factory() as db:
        state, _nonce, _verifier = await issue_login_state(db, mode="login", return_to="/trips")

    async def fake_exchange(**_kwargs) -> GoogleClaims:  # type: ignore[no-untyped-def]
        return _claims(sub="forged-remember", email="forged-remember@gmail.com")

    monkeypatch.setattr("app.api.v1.oauth.exchange_code_for_claims", fake_exchange)

    resp = await client.get(
        f"/auth/oauth/google/callback?code=test-code&state={state}&remember_me=true",
        follow_redirects=False,
    )

    assert resp.status_code == 303
    row = await _session_for(session_factory, resp.cookies["pinvi_refresh"])
    assert row.remember_me is False


async def test_oauth_link_callback_keeps_current_session_and_opens_no_family(
    client, session_factory, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """계정 연결은 새 회전 계열을 열지 않는다.

    절대 만료가 연결마다 다시 시작되지 않고, 브라우저에 묶이지 않은 state로 연 callback이 그 브라우저를
    연결한 사용자로 로그인시키지도 않는다.
    """
    user_id, email = await _seed_user(session_factory)
    refresh_token = (await _login(client, email, remember_me=True)).cookies["pinvi_refresh"]
    async with session_factory() as db:
        state, _nonce, _verifier = await issue_login_state(
            db, mode="link", return_to="/profile", user_id=user_id
        )

    async def fake_exchange(**_kwargs) -> GoogleClaims:  # type: ignore[no-untyped-def]
        return _claims(sub="link-no-session", email=email)

    monkeypatch.setattr("app.api.v1.oauth.exchange_code_for_claims", fake_exchange)

    resp = await client.get(
        f"/auth/oauth/google/callback?code=test-code&state={state}", follow_redirects=False
    )

    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/profile")
    assert resp.headers.get_list("set-cookie") == []
    async with session_factory() as db:
        families = (
            await db.scalars(
                select(UserSession.family_id).where(UserSession.user_id == user_id).distinct()
            )
        ).all()
    assert len(families) == 1
    assert (await _session_for(session_factory, refresh_token)).revoked_at is None


async def test_reuse_within_grace_after_family_moved_on_revokes_family(
    client, session_factory
) -> None:  # type: ignore[no-untyped-def]
    """유예 안이라도 계열이 그 뒤 다시 회전했으면 정상 경합이 아니다(탈취 사본) — 계열을 폐기한다."""
    _user_id, email = await _seed_user(session_factory)
    first = (await _login(client, email, remember_me=True)).cookies["pinvi_refresh"]
    second = (await client.post("/auth/refresh", cookies={"pinvi_refresh": first})).cookies[
        "pinvi_refresh"
    ]
    client.cookies.clear()
    third = (await client.post("/auth/refresh", cookies={"pinvi_refresh": second})).cookies[
        "pinvi_refresh"
    ]
    client.cookies.clear()

    replay = await client.post("/auth/refresh", cookies={"pinvi_refresh": first})

    assert replay.status_code == 401
    assert (await _session_for(session_factory, third)).revoked_at is not None


async def test_replaying_token_of_revoked_family_does_not_bump_access_version(
    client, session_factory
) -> None:  # type: ignore[no-untyped-def]
    user_id, email = await _seed_user(session_factory)
    old = (await _login(client, email, remember_me=True)).cookies["pinvi_refresh"]
    current = (await client.post("/auth/refresh", cookies={"pinvi_refresh": old})).cookies[
        "pinvi_refresh"
    ]
    client.cookies.clear()
    logout = await client.post("/auth/logout", cookies={"pinvi_refresh": current})
    assert logout.status_code == 204
    client.cookies.clear()
    async with session_factory() as db:
        await db.execute(
            update(UserSession)
            .where(UserSession.session_token_hash == hash_session_token(old))
            .values(rotated_at=datetime.now(UTC) - REFRESH_REUSE_GRACE - timedelta(seconds=5))
        )
        await db.commit()
        version_before = await db.scalar(
            select(User.access_token_version).where(User.user_id == user_id)
        )

    for _ in range(3):
        replay = await client.post("/auth/refresh", cookies={"pinvi_refresh": old})
        assert replay.status_code == 401

    async with session_factory() as db:
        version_after = await db.scalar(
            select(User.access_token_version).where(User.user_id == user_id)
        )
    assert version_after == version_before


async def test_logout_with_just_rotated_token_revokes_its_successor(
    client, session_factory
) -> None:  # type: ignore[no-untyped-def]
    """로그아웃과 갱신이 엇갈려 로그아웃이 방금 회전된 토큰을 들고 와도 그 로그인(계열)은 끊긴다."""
    _user_id, email = await _seed_user(session_factory)
    other = (await _login(client, email, remember_me=True)).cookies["pinvi_refresh"]
    old = (await _login(client, email, remember_me=True)).cookies["pinvi_refresh"]
    successor = (await client.post("/auth/refresh", cookies={"pinvi_refresh": old})).cookies[
        "pinvi_refresh"
    ]
    client.cookies.clear()

    out = await client.post("/auth/logout", cookies={"pinvi_refresh": old})

    assert out.status_code == 204
    assert (await _session_for(session_factory, successor)).revoked_at is not None
    assert (await _session_for(session_factory, other)).revoked_at is None


async def test_rotation_waits_for_concurrent_revoke_all(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    """비밀번호 재설정·비활성화의 전체 폐기가 진행 중이면 회전은 끝날 때까지 기다렸다가 401이 된다.

    직렬화가 없으면 폐기 UPDATE가 못 본 새 row(회전 결과)가 살아남아 1년 세션이 이어진다.
    """
    user_id, email = await _seed_user(session_factory)
    refresh_token = (await _login(client, email, remember_me=True)).cookies["pinvi_refresh"]

    holder = session_factory()
    try:
        await revoke_active_user_sessions(holder, user_id=user_id)  # 락을 쥔 채 아직 commit 전
        rotation = asyncio.create_task(_rotate(session_factory, refresh_token))
        await asyncio.sleep(0.5)
        assert not rotation.done()
        await holder.commit()
    finally:
        await holder.close()

    assert await rotation == "TOKEN_EXPIRED"
    async with session_factory() as db:
        active = await db.scalar(
            select(func.count())
            .select_from(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        )
    assert active == 0


async def test_reuse_revoke_sees_rotation_committed_while_waiting(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    """재사용 감지의 계열 폐기는 그 사이 끝난 회전이 만든 row까지 폐기한다(보안 리뷰 major)."""
    user_id, email = await _seed_user(session_factory)
    stolen = (await _login(client, email, remember_me=True)).cookies["pinvi_refresh"]
    current = (await client.post("/auth/refresh", cookies={"pinvi_refresh": stolen})).cookies[
        "pinvi_refresh"
    ]
    client.cookies.clear()
    family_id = (await _session_for(session_factory, current)).family_id
    async with session_factory() as db:
        await db.execute(
            update(UserSession)
            .where(UserSession.session_token_hash == hash_session_token(stolen))
            .values(rotated_at=datetime.now(UTC) - REFRESH_REUSE_GRACE - timedelta(seconds=5))
        )
        await db.commit()

    # 진행 중인 회전을 흉내 낸다: 사용자 락을 쥐고 같은 계열에 새 row를 넣은 채 아직 commit하지 않았다.
    in_flight = session_factory()
    try:
        await lock_user_sessions(in_flight, user_id=user_id)
        in_flight.add(
            UserSession(
                user_id=user_id,
                session_token_hash=hash_session_token("in-flight-successor"),
                family_id=family_id,
                remember_me=True,
                expires_at=datetime.now(UTC) + timedelta(days=300),
                absolute_expires_at=datetime.now(UTC) + timedelta(days=300),
            )
        )
        await in_flight.flush()
        replay = asyncio.create_task(_rotate(session_factory, stolen))
        await asyncio.sleep(0.5)
        assert not replay.done()
        await in_flight.commit()
    finally:
        await in_flight.close()

    assert await replay == "TOKEN_EXPIRED"
    assert (await _session_for(session_factory, "in-flight-successor")).revoked_at is not None
    assert (await _session_for(session_factory, current)).revoked_at is not None


async def test_mobile_login_with_remember_returns_one_year_refresh(client, session_factory) -> None:  # type: ignore[no-untyped-def]
    _user_id, email = await _seed_user(session_factory)
    now = datetime.now(UTC)

    resp = await client.post(
        "/mobile/auth/login",
        json={"email": email, "password": _PASSWORD, "remember_me": True},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    _assert_close(datetime.fromisoformat(data["expires_at"]), now + timedelta(days=365))
    row = await _session_for(session_factory, data["refresh_token"])
    assert row.remember_me is True


@pytest.mark.parametrize(
    "body", [None, "empty-json", {"remember_me": False}, {"remember_me": True}]
)
async def test_mobile_oauth_carries_remember_through_exchange(
    client, session_factory, monkeypatch, body: dict[str, bool] | str | None
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "pinvi_google_oauth_client_id", "test-client")
    monkeypatch.setattr(settings, "pinvi_google_oauth_client_secret", "test-secret")
    expected = isinstance(body, dict) and body["remember_me"]

    if body is None:
        start = await client.post("/mobile/auth/oauth/google/start")
    elif body == "empty-json":
        # 이전 앱 빌드: 본문 없이 JSON Content-Type만 붙여 보낸다.
        start = await client.post(
            "/mobile/auth/oauth/google/start", headers={"Content-Type": "application/json"}
        )
    else:
        start = await client.post("/mobile/auth/oauth/google/start", json=body)
    assert start.status_code == 200, start.text
    state = parse_qs(urlparse(start.json()["data"]["authorize_url"]).query)["state"][0]

    async def fake_exchange(**_kwargs) -> GoogleClaims:  # type: ignore[no-untyped-def]
        return _claims(
            sub=f"mob-{uuid.uuid4().hex[:8]}", email=f"m{uuid.uuid4().hex[:8]}@gmail.com"
        )

    monkeypatch.setattr("app.api.v1.oauth.exchange_code_for_claims", fake_exchange)
    callback = await client.get(
        f"/auth/oauth/google/callback?code=test-code&state={state}", follow_redirects=False
    )
    assert callback.status_code == 303
    code = parse_qs(urlparse(callback.headers["location"]).query)["code"][0]
    async with session_factory() as db:
        exchange_row = await db.scalar(
            select(OAuthMobileExchange).where(
                OAuthMobileExchange.code_hash == hashlib.sha256(code.encode()).hexdigest()
            )
        )
        assert exchange_row is not None
        assert exchange_row.remember_me is expected

    exchanged = await client.post("/mobile/auth/oauth/exchange", json={"code": code})

    assert exchanged.status_code == 200, exchanged.text
    row = await _session_for(session_factory, exchanged.json()["data"]["refresh_token"])
    assert row.remember_me is expected
