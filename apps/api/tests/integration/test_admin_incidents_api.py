"""Admin security incident workflow integration tests — T-275."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from app.models.audit import AdminAuditLog
from app.models.email_queue import EmailQueue
from app.models.security import SecurityIncident
from app.models.telegram_outbox import TelegramNotificationOutbox
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _create_user(
    session_factory: Any,
    *,
    roles: list[str],
    email_prefix: str,
) -> uuid.UUID:
    async with session_factory() as db:
        user = User(
            email=f"{email_prefix}-{uuid.uuid4().hex[:8]}@pinvi.test",
            password_hash="x",
            nickname="운영자",
            status="active",
            roles=roles,
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def _seed_incident(session_factory: Any) -> uuid.UUID:
    async with session_factory() as db:
        incident = SecurityIncident(
            incident_type="audit_chain_broken",
            severity="critical",
            source="admin_audit_log",
            summary="감사 로그 체인 검증 실패",
            details={"broken_at": 42},
        )
        db.add(incident)
        await db.commit()
        await db.refresh(incident)
        return incident.incident_id


async def test_cpo_incident_workflow_writes_audit_notification_and_email(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    cpo_id = await _create_user(
        session_factory,
        roles=["user", "cpo"],
        email_prefix="cpo-incident",
    )
    request_id = uuid.uuid4()

    created = await client.post(
        "/admin/incidents",
        json={
            "incident_type": "admin_export_anomaly",
            "severity": "high",
            "source": "admin_audit_log",
            "summary": "1시간 내 개인정보 export 임계치 초과",
            "details": {"exported_rows": 1200},
            "affected_user_count": 1200,
            "access_reason": "침해사고 수동 등록",
        },
        headers={"X-Request-Id": str(request_id)},
        cookies=auth_cookies(str(cpo_id)),
    )
    assert created.status_code == 201, created.text
    incident = created.json()["data"]
    incident_id = incident["incident_id"]
    assert incident["status"] == "detected"
    assert incident["cpo_review_due_at"] > incident["detected_at"]
    assert incident["external_report_due_at"] > incident["detected_at"]

    triaged = await client.post(
        f"/admin/incidents/{incident_id}/triage",
        json={"access_reason": "CPO 1차 확인"},
        cookies=auth_cookies(str(cpo_id)),
    )
    assert triaged.status_code == 200, triaged.text
    assert triaged.json()["data"]["status"] == "triage"

    decided = await client.post(
        f"/admin/incidents/{incident_id}/notification-decision",
        json={
            "notification_required": True,
            "decision_reason": "영향 사용자에게 안내 필요",
            "access_reason": "통지 필요성 판단",
        },
        cookies=auth_cookies(str(cpo_id)),
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["data"]["status"] == "notification_decision"

    notified = await client.post(
        f"/admin/incidents/{incident_id}/notify",
        json={
            "recipient_email": "subject@example.com",
            "subject": "Pinvi 개인정보 보호 알림",
            "message": "개인정보 보호 관련 안내입니다.",
            "access_reason": "정보주체 통지 발송",
        },
        cookies=auth_cookies(str(cpo_id)),
    )
    assert notified.status_code == 200, notified.text
    assert notified.json()["data"]["notification_payload_hash"]

    reported = await client.post(
        f"/admin/incidents/{incident_id}/report",
        json={
            "receipt_ref": "KISA-PIPC-20260628-001",
            "access_reason": "72시간 신고 접수번호 기록",
        },
        cookies=auth_cookies(str(cpo_id)),
    )
    assert reported.status_code == 200, reported.text
    assert reported.json()["data"]["status"] == "reported"

    closed = await client.post(
        f"/admin/incidents/{incident_id}/close",
        json={
            "closure_note": "통지와 신고 증적 확인 완료",
            "access_reason": "종결 체크리스트 완료",
        },
        cookies=auth_cookies(str(cpo_id)),
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["data"]["status"] == "closed"

    async with session_factory() as db:
        telegram_rows = list(
            (
                await db.scalars(
                    select(TelegramNotificationOutbox).where(
                        TelegramNotificationOutbox.category == "security_incident"
                    )
                )
            ).all()
        )
        email = await db.scalar(
            select(EmailQueue).where(EmailQueue.template == "security_incident_notice")
        )
        audits = list(
            (await db.scalars(select(AdminAuditLog).order_by(AdminAuditLog.log_id))).all()
        )

    assert len(telegram_rows) == 1
    assert telegram_rows[0].payload["audience"] == "admin"
    assert email is not None
    assert email.to_email == "subject@example.com"
    assert (
        email.payload["notification_payload_hash"]
        == notified.json()["data"]["notification_payload_hash"]
    )
    assert [row.action for row in audits] == [
        "security_incident.create",
        "security_incident.triage",
        "security_incident.notification_decision",
        "security_incident.notify_subjects",
        "security_incident.report_external",
        "security_incident.close",
    ]


async def test_admin_role_cannot_run_cpo_only_transition(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory,
        roles=["user", "admin"],
        email_prefix="admin-incident",
    )
    incident_id = await _seed_incident(session_factory)

    denied = await client.post(
        f"/admin/incidents/{incident_id}/triage",
        json={"access_reason": "admin이 CPO 전이 시도"},
        cookies=auth_cookies(str(admin_id)),
    )

    assert denied.status_code == 404


async def test_invalid_incident_transition_returns_conflict(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    cpo_id = await _create_user(
        session_factory,
        roles=["user", "cpo"],
        email_prefix="cpo-invalid-incident",
    )
    incident_id = await _seed_incident(session_factory)

    resp = await client.post(
        f"/admin/incidents/{incident_id}/notify",
        json={
            "message": "순서 오류",
            "access_reason": "잘못된 상태 전이 테스트",
        },
        cookies=auth_cookies(str(cpo_id)),
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_STATE"
