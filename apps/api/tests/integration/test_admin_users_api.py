"""Admin 사용자 관리 검색 / PII reveal audit 통합 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.audit import AdminAuditLog
from app.models.email_queue import EmailQueue
from app.models.oauth_identity import UserOAuthIdentity
from app.models.session import UserSession
from app.models.user import User
from app.models.user_email_verification import UserEmailVerification

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


def _attachment_payload(
    user_id: uuid.UUID,
    filename: str = "admin-file.jpg",
    *,
    purpose: str = "trip_attachment",
    byte_size: int = 2048,
) -> dict[str, object]:
    return {
        "bucket": "pinvi-media",
        "storage_key": f"user-uploads/{purpose}/{user_id}/2026/06/{uuid.uuid4().hex}.jpg",
        "original_filename": filename,
        "content_type": "image/jpeg",
        "byte_size": byte_size,
        "role": "image",
        "description": "관리자 파일 테스트",
        "sort_order": 0,
    }


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


async def test_admin_user_role_grant_revoke_matrix_and_guards(
    client,
    session_factory,
    auth_cookies,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin-rbac@example.com",
        nickname="RBAC관리자",
        roles=["user", "admin"],
    )
    second_admin_id = await _create_user(
        session_factory,
        email="admin-rbac-2@example.com",
        nickname="RBAC관리자2",
        roles=["user", "admin"],
    )
    operator_id = await _create_user(
        session_factory,
        email="operator-rbac@example.com",
        nickname="오퍼레이터",
        roles=["user", "operator"],
    )
    target_id = await _create_user(
        session_factory,
        email="target-rbac@example.com",
        nickname="대상",
        status="active",
    )
    async with session_factory() as db:
        db.add(
            UserSession(
                user_id=target_id,
                session_token_hash=f"rbac-session-{uuid.uuid4().hex}",
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        await db.commit()
    admin_cookies = auth_cookies(str(admin_id))

    matrix = await client.get(
        "/admin/rbac/permission-matrix", cookies=auth_cookies(str(operator_id))
    )
    assert matrix.status_code == 200, matrix.text
    matrix_data = matrix.json()["data"]
    assert matrix_data["roles"]["admin"]
    assert any(
        entry["resource"] == "admin.users" and entry["action"] == "role_grant_revoke"
        for entry in matrix_data["entries"]
    )

    denied = await client.post(
        f"/admin/users/{target_id}/roles/grant",
        json={"role": "admin", "access_reason": "권한 요청 승인"},
        cookies=auth_cookies(str(operator_id)),
    )
    assert denied.status_code == 404

    grant_request_id = uuid.uuid4()
    granted = await client.post(
        f"/admin/users/{target_id}/roles/grant",
        headers={"X-Request-Id": str(grant_request_id)},
        json={"role": "operator", "access_reason": "운영 담당자 지정"},
        cookies=admin_cookies,
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["data"]["roles"] == ["user", "operator"]
    assert granted.json()["data"]["recent_audit"][0]["action"] == "user.role_grant"

    duplicate = await client.post(
        f"/admin/users/{target_id}/roles/grant",
        json={"role": "operator", "access_reason": "중복 부여"},
        cookies=admin_cookies,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "INVALID_STATE"

    revoke_request_id = uuid.uuid4()
    revoked = await client.post(
        f"/admin/users/{target_id}/roles/revoke",
        headers={"X-Request-Id": str(revoke_request_id)},
        json={"role": "operator", "access_reason": "운영 담당 해제"},
        cookies=admin_cookies,
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["data"]["roles"] == ["user"]
    assert revoked.json()["data"]["recent_audit"][0]["action"] == "user.role_revoke"

    self_admin_revoke = await client.post(
        f"/admin/users/{admin_id}/roles/revoke",
        json={"role": "admin", "access_reason": "자기 권한 회수 시도"},
        cookies=admin_cookies,
    )
    assert self_admin_revoke.status_code == 403
    assert self_admin_revoke.json()["error"]["code"] == "PERMISSION_DENIED"

    second_admin_revoke = await client.post(
        f"/admin/users/{second_admin_id}/roles/revoke",
        json={"role": "admin", "access_reason": "보조 관리자 해제"},
        cookies=admin_cookies,
    )
    assert second_admin_revoke.status_code == 200, second_admin_revoke.text
    assert second_admin_revoke.json()["data"]["roles"] == ["user"]

    async with session_factory() as db:
        target = await db.scalar(select(User).where(User.user_id == target_id))
        stored_session = await db.scalar(
            select(UserSession).where(UserSession.user_id == target_id)
        )
        grant_audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.request_id == grant_request_id)
        )
        revoke_audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.request_id == revoke_request_id)
        )

    assert target is not None
    assert target.roles == ["user"]
    assert target.access_token_version == 2
    assert stored_session is not None
    assert stored_session.revoked_at is not None
    assert grant_audit is not None
    assert grant_audit.action == "user.role_grant"
    assert grant_audit.before_state == {"roles": ["user"]}
    assert grant_audit.after_state == {"roles": ["user", "operator"]}
    assert revoke_audit is not None
    assert revoke_audit.action == "user.role_revoke"
    assert revoke_audit.before_state == {"roles": ["user", "operator"]}
    assert revoke_audit.after_state == {"roles": ["user"]}


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


async def test_admin_user_lifecycle_resend_verification(
    client,
    session_factory,
    auth_cookies,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin-lifecycle-resend@example.com",
        nickname="관리자",
        roles=["user", "admin"],
    )
    target_id = await _create_user(
        session_factory,
        email="pending-lifecycle@example.com",
        nickname="인증대기",
        status="pending_verification",
    )
    request_id = uuid.uuid4()

    resp = await client.post(
        f"/admin/users/{target_id}/lifecycle/resend-verify",
        headers={"X-Request-Id": str(request_id)},
        json={"access_reason": "가입 인증 메일 재발송 요청"},
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "pending_verification"
    assert data["recent_audit"][0]["action"] == "user.verification_resend"

    async with session_factory() as db:
        verification = await db.scalar(
            select(UserEmailVerification).where(
                UserEmailVerification.user_id == target_id,
                UserEmailVerification.purpose == "signup",
                UserEmailVerification.used_at.is_(None),
            )
        )
        queued = await db.scalar(
            select(EmailQueue).where(
                EmailQueue.user_id == target_id,
                EmailQueue.template == "verify_email",
            )
        )
        audit = await db.scalar(select(AdminAuditLog).where(AdminAuditLog.request_id == request_id))

    assert verification is not None
    assert queued is not None
    assert audit is not None
    assert audit.after_state["verification_id"] == str(verification.verification_id)


async def test_admin_user_lifecycle_sessions_reset_delete_reactivate_anonymize(
    client,
    session_factory,
    auth_cookies,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin-lifecycle@example.com",
        nickname="관리자",
        roles=["user", "admin"],
    )
    target_id = await _create_user(
        session_factory,
        email="target-lifecycle@example.com",
        nickname="대상",
        status="active",
    )
    async with session_factory() as db:
        db.add_all(
            [
                UserSession(
                    user_id=target_id,
                    session_token_hash=f"lifecycle-session-{uuid.uuid4().hex}",
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                    user_agent="Firefox",
                    ip_address="203.0.113.10",
                ),
                UserSession(
                    user_id=target_id,
                    session_token_hash=f"lifecycle-session-{uuid.uuid4().hex}",
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                    user_agent="Chrome",
                    ip_address="203.0.113.11",
                ),
                UserOAuthIdentity(
                    user_id=target_id,
                    provider="google",
                    provider_user_id=f"google-{uuid.uuid4().hex}",
                    provider_email="target-lifecycle@example.com",
                    provider_email_verified=True,
                    display_name_snapshot="대상",
                    linked_at=datetime.now(UTC),
                ),
            ]
        )
        await db.commit()

    cookies = auth_cookies(str(admin_id))
    sessions = await client.get(f"/admin/users/{target_id}/sessions", cookies=cookies)
    assert sessions.status_code == 200, sessions.text
    session_items = sessions.json()["data"]["items"]
    assert len(session_items) == 2
    assert session_items[0]["ip_hash"]
    assert "203.0.113.10" not in sessions.text

    revoke_one = await client.post(
        f"/admin/users/{target_id}/sessions/{session_items[0]['session_id']}/revoke",
        json={"access_reason": "분실 기기 세션 종료"},
        cookies=cookies,
    )
    assert revoke_one.status_code == 200, revoke_one.text
    assert revoke_one.json()["data"]["recent_audit"][0]["action"] == "user.session_revoke"

    reset_request_id = uuid.uuid4()
    reset = await client.post(
        f"/admin/users/{target_id}/lifecycle/force-password-reset",
        headers={"X-Request-Id": str(reset_request_id)},
        json={"access_reason": "계정 탈취 의심"},
        cookies=cookies,
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["data"]["recent_audit"][0]["action"] == "user.password_reset_force"

    async with session_factory() as db:
        target = await db.scalar(select(User).where(User.user_id == target_id))
        reset_verification = await db.scalar(
            select(UserEmailVerification).where(
                UserEmailVerification.user_id == target_id,
                UserEmailVerification.purpose == "password_reset",
                UserEmailVerification.used_at.is_(None),
            )
        )
        reset_email = await db.scalar(
            select(EmailQueue).where(
                EmailQueue.user_id == target_id,
                EmailQueue.template == "reset_password",
            )
        )
        active_session_count = len(
            (
                await db.execute(
                    select(UserSession).where(
                        UserSession.user_id == target_id,
                        UserSession.revoked_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )

    assert target is not None
    assert target.password_hash is None
    assert target.access_token_version > 0
    assert reset_verification is not None
    assert reset_email is not None
    assert active_session_count == 0

    disabled = await client.post(
        f"/admin/users/{target_id}/disable",
        json={"access_reason": "고객센터 잠금"},
        cookies=cookies,
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["data"]["status"] == "disabled"

    reactivated = await client.post(
        f"/admin/users/{target_id}/lifecycle/reactivate",
        json={"access_reason": "본인 확인 완료"},
        cookies=cookies,
    )
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["data"]["status"] == "active"

    deleted = await client.post(
        f"/admin/users/{target_id}/lifecycle/delete",
        json={"access_reason": "탈퇴 요청 접수", "confirm": "DELETE"},
        cookies=cookies,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["status"] == "pending_delete"

    pending_list = await client.get(
        "/admin/users?status_filter=pending_delete",
        cookies=cookies,
    )
    assert pending_list.status_code == 200, pending_list.text
    assert pending_list.json()["data"]["total"] == 1
    assert pending_list.json()["data"]["items"][0]["user_id"] == str(target_id)

    restored = await client.post(
        f"/admin/users/{target_id}/lifecycle/reactivate",
        json={"access_reason": "탈퇴 요청 철회"},
        cookies=cookies,
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["data"]["status"] == "active"

    await client.post(
        f"/admin/users/{target_id}/lifecycle/delete",
        json={"access_reason": "탈퇴 요청 재접수", "confirm": "DELETE"},
        cookies=cookies,
    )
    anonymized = await client.post(
        f"/admin/users/{target_id}/lifecycle/anonymize",
        json={"access_reason": "즉시 익명화 승인", "confirm": "ANONYMIZE"},
        cookies=cookies,
    )
    assert anonymized.status_code == 200, anonymized.text
    anonymized_data = anonymized.json()["data"]
    assert anonymized_data["status"] == "deleted"
    assert anonymized_data["email_masked"].startswith("d***@deleted.pinvi.local")
    assert anonymized_data["recent_audit"][0]["action"] == "user.anonymize"

    async with session_factory() as db:
        stored = await db.scalar(select(User).where(User.user_id == target_id))
        identity = await db.scalar(
            select(UserOAuthIdentity).where(UserOAuthIdentity.user_id == target_id)
        )

    assert stored is not None
    assert stored.email == f"deleted+{target_id}@deleted.pinvi.local"
    assert stored.nickname is None
    assert stored.status == "deleted"
    assert identity is None


async def test_user_delete_me_marks_pending_delete_and_revokes_sessions(
    client,
    session_factory,
    auth_cookies,
) -> None:
    user_id = await _create_user(
        session_factory,
        email="self-delete@example.com",
        nickname="탈퇴사용자",
        status="active",
    )
    async with session_factory() as db:
        db.add(
            UserSession(
                user_id=user_id,
                session_token_hash=f"self-delete-{uuid.uuid4().hex}",
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        await db.commit()

    cookies = auth_cookies(str(user_id))
    resp = await client.delete("/users/me", cookies=cookies)

    assert resp.status_code == 204, resp.text
    assert "pinvi_access" in resp.headers.get("set-cookie", "")

    async with session_factory() as db:
        user = await db.scalar(select(User).where(User.user_id == user_id))
        stored_session = await db.scalar(select(UserSession).where(UserSession.user_id == user_id))

    assert user is not None
    assert user.status == "pending_delete"
    assert user.is_active is False
    assert user.deleted_at is not None
    assert stored_session is not None
    assert stored_session.revoked_at is not None

    after = await client.get("/auth/me", cookies=cookies)
    assert after.status_code == 401


async def test_admin_avatar_settings_and_user_avatar_audit(
    client,
    session_factory,
    auth_cookies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin-avatar@example.com",
        nickname="관리자",
        roles=["user", "admin"],
    )
    target_id = await _create_user(
        session_factory,
        email="avatar-target@example.com",
        nickname="아바타 대상",
        status="active",
    )
    cookies = auth_cookies(str(admin_id))

    settings_resp = await client.get("/admin/settings/avatar", cookies=cookies)
    assert settings_resp.status_code == 200
    assert settings_resp.json()["data"]["avatar_max_upload_bytes"] == 2 * 1024 * 1024

    settings_request_id = uuid.uuid4()
    settings_update = await client.put(
        "/admin/settings/avatar",
        headers={"X-Request-Id": str(settings_request_id)},
        json={
            "avatar_max_upload_bytes": 4096,
            "access_reason": "운영 정책상 아바타 제한 조정",
        },
        cookies=cookies,
    )

    assert settings_update.status_code == 200, settings_update.text
    assert settings_update.json()["data"]["avatar_max_upload_bytes"] == 4096

    upload = await client.post(
        f"/admin/users/{target_id}/avatar/upload-url",
        json={
            "filename": "face.png",
            "content_type": "image/png",
            "content_length": 2048,
        },
        cookies=cookies,
    )

    assert upload.status_code == 200, upload.text
    upload_data = upload.json()["data"]
    assert upload_data["storage_key"].startswith(f"user-uploads/avatar/{target_id}/")
    assert upload_data["max_upload_bytes"] == 4096

    avatar_request_id = uuid.uuid4()
    updated = await client.put(
        f"/admin/users/{target_id}/avatar",
        headers={"X-Request-Id": str(avatar_request_id)},
        json={
            "bucket": upload_data["bucket"],
            "storage_key": upload_data["storage_key"],
            "content_type": "image/png",
            "byte_size": 2048,
            "public_url": None,
            "access_reason": "사용자 요청 대행 업로드",
        },
        cookies=cookies,
    )

    assert updated.status_code == 200, updated.text
    updated_data = updated.json()["data"]
    assert updated_data["has_avatar"] is True
    assert updated_data["avatar_kind"] == "upload"
    assert updated_data["recent_audit"][0]["action"] == "user.avatar_replace"
    assert updated_data["recent_audit"][0]["target_pii_fields"] == ["avatar"]

    download = await client.get(f"/admin/users/{target_id}/avatar/download-url", cookies=cookies)
    assert download.status_code == 200
    assert "/storage/downloads/" in download.json()["data"]["download_url"]
    assert "127.0.0.1" not in download.json()["data"]["download_url"]

    deleted_keys: list[str] = []

    async def _delete_object(*, key: str) -> None:
        deleted_keys.append(key)

    import app.api.v1.admin.users as admin_users_router

    monkeypatch.setattr(admin_users_router, "delete_object", _delete_object)

    delete_request_id = uuid.uuid4()
    deleted = await client.request(
        "DELETE",
        f"/admin/users/{target_id}/avatar",
        headers={"X-Request-Id": str(delete_request_id)},
        json={"access_reason": "사용자 요청 대행 삭제"},
        cookies=cookies,
    )

    assert deleted.status_code == 200, deleted.text
    deleted_data = deleted.json()["data"]
    assert deleted_data["has_avatar"] is False
    assert deleted_data["recent_audit"][0]["action"] == "user.avatar_delete"
    assert deleted_keys == [upload_data["storage_key"]]

    async with session_factory() as db:
        settings_audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.request_id == settings_request_id)
        )
        avatar_audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.request_id == avatar_request_id)
        )
        delete_audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.request_id == delete_request_id)
        )

    assert settings_audit is not None
    assert settings_audit.action == "settings.avatar_update"
    assert settings_audit.before_state == {"avatar_max_upload_bytes": 2 * 1024 * 1024}
    assert settings_audit.after_state == {"avatar_max_upload_bytes": 4096}
    assert avatar_audit is not None
    assert avatar_audit.action == "user.avatar_replace"
    assert delete_audit is not None
    assert delete_audit.action == "user.avatar_delete"


async def test_admin_file_settings_user_quota_and_file_management(
    client,
    session_factory,
    auth_cookies,
) -> None:
    admin_id = await _create_user(
        session_factory,
        email="admin-files@example.com",
        nickname="파일관리자",
        roles=["user", "admin"],
    )
    target_id = await _create_user(
        session_factory,
        email="file-target@example.com",
        nickname="파일사용자",
        status="active",
    )
    admin_cookies = auth_cookies(str(admin_id))
    user_cookies = auth_cookies(str(target_id))

    created = await client.post(
        "/trips",
        json={"title": "관리 파일 여행"},
        cookies=user_cookies,
    )
    assert created.status_code == 201, created.text
    trip_id = created.json()["data"]["trip_id"]
    attachment = await client.post(
        f"/trips/{trip_id}/attachments",
        json=_attachment_payload(target_id, "admin-file.jpg"),
        cookies=user_cookies,
    )
    assert attachment.status_code == 201, attachment.text
    attachment_id = attachment.json()["data"]["attachment_id"]

    defaults = await client.get("/admin/settings/files", cookies=admin_cookies)
    assert defaults.status_code == 200, defaults.text
    assert defaults.json()["data"]["attachment_max_upload_bytes"] == 10 * 1024 * 1024

    settings_request_id = uuid.uuid4()
    settings_update = await client.put(
        "/admin/settings/files",
        headers={"X-Request-Id": str(settings_request_id)},
        json={
            "attachment_max_upload_bytes": 4096,
            "trip_attachment_quota_bytes": 8192,
            "user_attachment_quota_bytes": 16384,
            "access_reason": "파일 업로드 정책 조정",
        },
        cookies=admin_cookies,
    )
    assert settings_update.status_code == 200, settings_update.text
    assert settings_update.json()["data"] == {
        "attachment_max_upload_bytes": 4096,
        "trip_attachment_quota_bytes": 8192,
        "user_attachment_quota_bytes": 16384,
    }

    quota_request_id = uuid.uuid4()
    quota_update = await client.put(
        f"/admin/users/{target_id}/file-quota",
        headers={"X-Request-Id": str(quota_request_id)},
        json={
            "attachment_max_upload_bytes_override": 2048,
            "trip_attachment_quota_bytes_override": 4096,
            "user_attachment_quota_bytes_override": 8192,
            "access_reason": "VIP 고객 개별 용량 부여",
        },
        cookies=admin_cookies,
    )
    assert quota_update.status_code == 200, quota_update.text
    quota_data = quota_update.json()["data"]["file_quota"]
    assert quota_data["effective_attachment_max_upload_bytes"] == 2048
    assert quota_data["attachment_max_upload_bytes_override"] == 2048
    assert quota_data["effective_trip_attachment_quota_bytes"] == 4096
    assert quota_data["effective_user_attachment_quota_bytes"] == 8192

    listed = await client.get(
        f"/admin/files?scope=trip&q=admin-file&user_id={target_id}",
        cookies=admin_cookies,
    )
    assert listed.status_code == 200, listed.text
    listed_data = listed.json()["data"]
    assert listed_data["total"] == 1
    item = listed_data["items"][0]
    assert item["attachment_id"] == attachment_id
    assert item["trip_id"] == trip_id
    assert item["target_scope"] == "trip"
    assert item["uploaded_by_email_masked"] == "f***@example.com"
    assert "file-target@example.com" not in listed.text

    download = await client.get(
        f"/admin/files/{attachment_id}/download-url",
        cookies=admin_cookies,
    )
    assert download.status_code == 200, download.text
    assert download.json()["data"]["storage_key"] == item["storage_key"]

    delete_request_id = uuid.uuid4()
    deleted = await client.request(
        "DELETE",
        f"/admin/files/{attachment_id}",
        headers={"X-Request-Id": str(delete_request_id)},
        json={"access_reason": "사용자 요청 파일 삭제"},
        cookies=admin_cookies,
    )
    assert deleted.status_code == 204, deleted.text

    after_delete = await client.get(
        f"/admin/files?user_id={target_id}",
        cookies=admin_cookies,
    )
    assert after_delete.status_code == 200
    assert after_delete.json()["data"]["total"] == 0

    async with session_factory() as db:
        settings_audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.request_id == settings_request_id)
        )
        quota_audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.request_id == quota_request_id)
        )
        delete_audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.request_id == delete_request_id)
        )

    assert settings_audit is not None
    assert settings_audit.action == "settings.files_update"
    assert settings_audit.before_state["attachment_max_upload_bytes"] == 10 * 1024 * 1024
    assert quota_audit is not None
    assert quota_audit.action == "user.file_quota_update"
    assert quota_audit.after_state["attachment_max_upload_bytes_override"] == 2048
    assert delete_audit is not None
    assert delete_audit.action == "attachment.delete"
