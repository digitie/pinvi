"""DSR intake and CPO workflow integration tests — T-278."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.models.audit import AdminAuditLog
from app.models.dsr import DsrRequest
from app.models.email_queue import EmailQueue
from app.models.user import User
from app.services.admin_users import mask_email
from app.services.email_deliverability import email_hash

pytestmark = pytest.mark.asyncio


async def _create_user(
    session_factory: Any,
    *,
    roles: list[str],
    email_prefix: str,
) -> tuple[uuid.UUID, str]:
    async with session_factory() as db:
        email = f"{email_prefix}-{uuid.uuid4().hex[:8]}@pinvi.test"
        user = User(
            email=email,
            password_hash="x",
            nickname="테스트",
            status="active",
            roles=roles,
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id, email


async def _create_dsr_request(
    client: Any,
    *,
    user_id: uuid.UUID,
    auth_cookies: Any,
    request_type: str = "access",
) -> dict[str, Any]:
    response = await client.post(
        "/users/me/dsr-requests",
        json={
            "request_type": request_type,
            "request_summary": f"{request_type} 권리행사 요청",
            "request_details": {"scope": "profile_location"},
        },
        cookies=auth_cookies(str(user_id)),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_user_creates_lists_and_withdraws_dsr_request(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    user_id, email = await _create_user(
        session_factory,
        roles=["user"],
        email_prefix="dsr-user",
    )

    created = await _create_dsr_request(
        client,
        user_id=user_id,
        auth_cookies=auth_cookies,
        request_type="access",
    )

    assert created["status"] == "received"
    assert created["requester_email_masked"] == mask_email(email)
    assert created["next_action"] == "identity_check"

    listed = await client.get(
        "/users/me/dsr-requests",
        cookies=auth_cookies(str(user_id)),
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["total"] == 1

    withdrawn = await client.post(
        f"/users/me/dsr-requests/{created['request_id']}/withdraw",
        json={"reason": "다른 채널로 요청"},
        cookies=auth_cookies(str(user_id)),
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["data"]["status"] == "withdrawn"

    async with session_factory() as db:
        row = await db.get(DsrRequest, uuid.UUID(created["request_id"]))

    assert row is not None
    assert row.requester_email_hash == email_hash(email)
    assert row.requester_email_masked == mask_email(email)
    assert row.due_at - row.received_at == timedelta(days=10)
    assert row.request_details["withdrawal"]["reason"] == "다른 채널로 요청"


async def test_cpo_dsr_workflow_writes_audit_and_result_notice(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    user_id, user_email = await _create_user(
        session_factory,
        roles=["user"],
        email_prefix="dsr-subject",
    )
    cpo_id, _ = await _create_user(
        session_factory,
        roles=["user", "cpo"],
        email_prefix="dsr-cpo",
    )
    created = await _create_dsr_request(client, user_id=user_id, auth_cookies=auth_cookies)
    request_id = created["request_id"]

    identity = await client.post(
        f"/admin/dsr/{request_id}/identity-check",
        json={
            "access_reason": "본인 확인",
            "identity_verified": True,
            "identity_note": "인증 세션 확인",
        },
        cookies=auth_cookies(str(cpo_id)),
    )
    assert identity.status_code == 200, identity.text
    assert identity.json()["data"]["status"] == "identity_check"
    assert identity.json()["data"]["identity_verified_at"] is not None

    processing = await client.post(
        f"/admin/dsr/{request_id}/process",
        json={"access_reason": "처리 시작", "processing_note": "export 생성"},
        cookies=auth_cookies(str(cpo_id)),
    )
    assert processing.status_code == 200, processing.text
    assert processing.json()["data"]["status"] == "processing"

    completed = await client.post(
        f"/admin/dsr/{request_id}/complete",
        json={
            "access_reason": "결과 통지",
            "result_summary": "프로필과 위치 접근 로그 export 제공",
            "export_manifest": {"files": ["profile.json"], "masked_fields": ["email"]},
            "partial_response": True,
        },
        cookies=auth_cookies(str(cpo_id)),
    )
    assert completed.status_code == 200, completed.text
    result = completed.json()["data"]
    assert result["status"] == "completed"
    assert result["result_notice_hash"]
    assert result["result_notice_email_id"]
    assert result["partial_response"] is True

    async with session_factory() as db:
        row = await db.get(DsrRequest, uuid.UUID(request_id))
        email = await db.scalar(
            select(EmailQueue).where(EmailQueue.template == "dsr_result_notice")
        )
        audits = list(
            (await db.scalars(select(AdminAuditLog).order_by(AdminAuditLog.log_id))).all()
        )

    assert row is not None
    assert row.result_notice_hash == result["result_notice_hash"]
    assert row.requester_email_hash == email_hash(user_email)
    assert email is not None
    assert email.to_email == user_email
    assert email.payload["result_notice_hash"] == result["result_notice_hash"]
    assert email.payload["export_manifest"]["masked_fields"] == ["email"]
    assert [audit.action for audit in audits] == [
        "dsr.identity_check",
        "dsr.process",
        "dsr.complete",
    ]


async def test_dsr_rbac_and_invalid_transition(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    user_id, _ = await _create_user(
        session_factory,
        roles=["user"],
        email_prefix="dsr-rbac-user",
    )
    admin_id, _ = await _create_user(
        session_factory,
        roles=["user", "admin"],
        email_prefix="dsr-admin",
    )
    cpo_id, _ = await _create_user(
        session_factory,
        roles=["user", "cpo"],
        email_prefix="dsr-cpo-invalid",
    )
    created = await _create_dsr_request(client, user_id=user_id, auth_cookies=auth_cookies)
    request_id = created["request_id"]

    denied = await client.post(
        f"/admin/dsr/{request_id}/identity-check",
        json={"access_reason": "admin 전이 시도"},
        cookies=auth_cookies(str(admin_id)),
    )
    assert denied.status_code == 404

    invalid = await client.post(
        f"/admin/dsr/{request_id}/process",
        json={"access_reason": "순서 오류"},
        cookies=auth_cookies(str(cpo_id)),
    )
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "INVALID_STATE"
