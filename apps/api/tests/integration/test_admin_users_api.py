"""Admin 사용자 관리 검색 / PII reveal audit 통합 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.audit import AdminAuditLog
from app.models.session import UserSession
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _create_user(
    session_factory,
    *,
    email: str,
    nickname: str | None = None,
    status: str = "active",
    roles: list[str] | None = None,
) -> uuid.UUID:
    async with session_factory() as db:
        user = User(
            email=email,
            password_hash="x",
            nickname=nickname,
            status=status,
            roles=roles or ["user"],
            email_verified_at=datetime.now(UTC) if status == "active" else None,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def test_admin_users_list_searches_and_masks_email(
    client,
    session_factory,
    auth_cookies,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin@example.com",
        nickname="관리자",
        roles=["user", "admin"],
    )
    await _create_user(
        session_factory,
        email="kim@example.com",
        nickname="김여행",
        status="active",
    )
    await _create_user(
        session_factory,
        email="kim-disabled@example.com",
        nickname="김비활성",
        status="disabled",
    )
    await _create_user(
        session_factory,
        email="park@example.com",
        nickname="박여행",
        status="active",
    )

    resp = await client.get(
        "/admin/users?q=김&status_filter=active",
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["total"] == 1
    assert body["items"][0]["email_masked"] == "k***@example.com"
    assert body["items"][0]["nickname"] == "김여행"
    assert "kim@example.com" not in resp.text


async def test_admin_user_detail_masks_then_reveals_with_audit(
    client,
    session_factory,
    auth_cookies,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin@example.com",
        nickname="관리자",
        roles=["user", "admin"],
    )
    target_id = await _create_user(
        session_factory,
        email="secret@example.com",
        nickname="비밀사용자",
        status="active",
    )
    cookies = auth_cookies(str(admin_id))

    masked = await client.get(f"/admin/users/{target_id}", cookies=cookies)

    assert masked.status_code == 200
    masked_data = masked.json()["data"]
    assert masked_data["email"] == "s***@example.com"
    assert masked_data["email_revealed"] is False
    assert masked_data["recent_audit"] == []

    missing_reason = await client.get(
        f"/admin/users/{target_id}?reveal=true",
        cookies=cookies,
    )

    assert missing_reason.status_code == 422
    assert missing_reason.json()["error"]["code"] == "VALIDATION_ERROR"

    query_reason = await client.get(
        f"/admin/users/{target_id}?reveal=true&access_reason=고객 문의 확인",
        cookies=cookies,
    )

    assert query_reason.status_code == 422
    assert query_reason.json()["error"]["code"] == "VALIDATION_ERROR"

    request_id = uuid.uuid4()
    revealed = await client.post(
        f"/admin/users/{target_id}/reveal-pii",
        headers={
            "X-Request-Id": str(request_id),
        },
        json={"access_reason": "고객 문의 확인"},
        cookies=cookies,
    )

    assert revealed.status_code == 200
    revealed_data = revealed.json()["data"]
    assert revealed_data["email"] == "secret@example.com"
    assert revealed_data["email_revealed"] is True
    assert revealed_data["recent_audit"][0]["action"] == "user.reveal_pii"
    assert revealed_data["recent_audit"][0]["target_pii_fields"] == ["email"]
    assert revealed_data["recent_audit"][0]["access_reason"] == "고객 문의 확인"

    async with session_factory() as db:
        audit = await db.scalar(select(AdminAuditLog).where(AdminAuditLog.request_id == request_id))

    assert audit is not None
    assert audit.actor_user_id == admin_id
    assert audit.resource_id == str(target_id)


async def test_admin_user_force_verify_writes_status_audit(
    client,
    session_factory,
    auth_cookies,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin@example.com",
        nickname="관리자",
        roles=["user", "admin"],
    )
    target_id = await _create_user(
        session_factory,
        email="pending@example.com",
        nickname="가입대기",
        status="pending_verification",
    )
    request_id = uuid.uuid4()

    resp = await client.post(
        f"/admin/users/{target_id}/force-verify",
        headers={"X-Request-Id": str(request_id)},
        json={"access_reason": "가입 메일 반송 고객 지원"},
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "pending_profile"
    assert data["email_verified_at"] is not None
    assert data["recent_audit"][0]["action"] == "user.force_verify"

    async with session_factory() as db:
        audit = await db.scalar(select(AdminAuditLog).where(AdminAuditLog.request_id == request_id))

    assert audit is not None
    assert audit.before_state == {
        "status": "pending_verification",
        "email_verified_at": None,
    }
    assert audit.after_state["status"] == "pending_profile"
    assert audit.after_state["email_verified_at"] is not None


async def test_admin_user_disable_rolls_back_when_audit_fails(
    client,
    session_factory,
    auth_cookies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.v1.admin.users as admin_users_router

    admin_id = await _create_user(
        session_factory,
        email="admin@example.com",
        nickname="관리자",
        roles=["user", "admin"],
    )
    target_id = await _create_user(
        session_factory,
        email="active@example.com",
        nickname="활성사용자",
        status="active",
    )
    async with session_factory() as db:
        db.add(
            UserSession(
                user_id=target_id,
                session_token_hash=f"session-{uuid.uuid4().hex}",
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        await db.commit()

    async def _fail_append(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("audit failed")

    monkeypatch.setattr(admin_users_router, "append_admin_audit", _fail_append)

    with pytest.raises(RuntimeError, match="audit failed"):
        await client.post(
            f"/admin/users/{target_id}/disable",
            json={"access_reason": "테스트 감사 실패"},
            cookies=auth_cookies(str(admin_id)),
        )

    async with session_factory() as db:
        user = await db.scalar(select(User).where(User.user_id == target_id))
        stored_session = await db.scalar(
            select(UserSession).where(UserSession.user_id == target_id)
        )
        audit_count = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.resource_id == str(target_id))
        )

    assert user is not None
    assert user.status == "active"
    assert user.is_active is True
    assert stored_session is not None
    assert stored_session.revoked_at is None
    assert audit_count is None
