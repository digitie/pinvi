"""Content moderation / takedown workflow integration tests — T-279."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select

from app.models.attachment import CuratedPlanAttachment
from app.models.audit import AdminAuditLog
from app.models.comment import TripComment
from app.models.companion import TripCompanion
from app.models.moderation import ContentModerationAction, ContentReport
from app.models.share_link import TripShareLink
from app.models.trip import Trip
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
            nickname="테스트",
            status="active",
            roles=roles,
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def _seed_trip_targets(
    session_factory: Any,
    *,
    owner_id: uuid.UUID,
    reporter_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    async with session_factory() as db:
        trip = Trip(
            owner_user_id=owner_id,
            title="공개 신고 대상 여행",
            description="moderation test",
            visibility="public",
            status="planned",
        )
        db.add(trip)
        await db.flush()
        if reporter_id is not None:
            db.add(
                TripCompanion(
                    trip_id=trip.trip_id,
                    user_id=reporter_id,
                    invited_email="reporter@example.com",
                    role="viewer",
                    invited_at=datetime.now(UTC),
                    joined_at=datetime.now(UTC),
                )
            )
        comment = TripComment(
            trip_id=trip.trip_id,
            author_user_id=owner_id,
            body="신고 대상 댓글",
        )
        attachment = CuratedPlanAttachment(
            trip_id=trip.trip_id,
            uploaded_by_user_id=owner_id,
            bucket="pinvi-media",
            storage_key=f"user-uploads/{uuid.uuid4().hex}.jpg",
            original_filename="unsafe.jpg",
            content_type="image/jpeg",
            byte_size=10,
        )
        share = TripShareLink(
            trip_id=trip.trip_id,
            token_hash=f"token-{uuid.uuid4().hex}",
            created_by_user_id=owner_id,
            visibility="view_only",
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        db.add_all([comment, attachment, share])
        await db.commit()
        return trip.trip_id, comment.comment_id, attachment.attachment_id, share.share_id


async def _create_report(
    client: Any,
    *,
    auth_cookies: Any,
    actor_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    reason_code: str = "privacy",
) -> dict[str, Any]:
    response = await client.post(
        "/users/me/content-reports",
        json={
            "target_type": target_type,
            "target_id": str(target_id),
            "reason_code": reason_code,
            "reason_text": f"{target_type} 신고 사유",
            "evidence": {"source": "test"},
        },
        cookies=auth_cookies(str(actor_id)),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_comment_report_hide_appeal_restore_flow(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    owner_id = await _create_user(session_factory, roles=["user"], email_prefix="mod-owner")
    reporter_id = await _create_user(session_factory, roles=["user"], email_prefix="mod-reporter")
    admin_id = await _create_user(
        session_factory, roles=["user", "admin"], email_prefix="mod-admin"
    )
    _, comment_id, _, _ = await _seed_trip_targets(
        session_factory,
        owner_id=owner_id,
        reporter_id=reporter_id,
    )

    created = await _create_report(
        client,
        auth_cookies=auth_cookies,
        actor_id=reporter_id,
        target_type="comment",
        target_id=comment_id,
        reason_code="harassment",
    )
    assert created["status"] == "received"
    assert created["target_owner_user_id"] == str(owner_id)
    report_id = created["report_id"]

    hidden = await client.post(
        f"/admin/moderation/reports/{report_id}/hide",
        json={"access_reason": "신고 심사", "resolution_summary": "댓글 임시 숨김"},
        cookies=auth_cookies(str(admin_id)),
    )
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["data"]["status"] == "hidden"

    async with session_factory() as db:
        comment = await db.get(TripComment, comment_id)
    assert comment is not None
    assert comment.deleted_at is not None

    appealed = await client.post(
        f"/users/me/content-reports/{report_id}/appeal",
        json={"appeal_reason": "문맥상 문제가 없는 댓글입니다."},
        cookies=auth_cookies(str(owner_id)),
    )
    assert appealed.status_code == 200, appealed.text
    assert appealed.json()["data"]["status"] == "appealed"

    restored = await client.post(
        f"/admin/moderation/reports/{report_id}/restore",
        json={"access_reason": "appeal 심사", "resolution_summary": "댓글 복구"},
        cookies=auth_cookies(str(admin_id)),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["data"]["status"] == "restored"

    async with session_factory() as db:
        row = await db.get(ContentReport, uuid.UUID(report_id))
        comment = await db.get(TripComment, comment_id)
        actions = list(
            (
                await db.scalars(
                    select(ContentModerationAction).order_by(
                        ContentModerationAction.created_at,
                        ContentModerationAction.action_id,
                    )
                )
            ).all()
        )
        audits = list(
            (await db.scalars(select(AdminAuditLog).order_by(AdminAuditLog.log_id))).all()
        )

    assert row is not None
    assert row.status == "restored"
    assert row.appeal_summary == "문맥상 문제가 없는 댓글입니다."
    assert comment is not None
    assert comment.deleted_at is None
    assert [action.action for action in actions] == ["hide", "appeal", "restore"]
    assert [audit.action for audit in audits] == [
        "content_moderation.hide",
        "content_moderation.restore",
    ]


async def test_trip_attachment_share_link_reports_apply_takedown(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    owner_id = await _create_user(session_factory, roles=["user"], email_prefix="mod-owner-2")
    admin_id = await _create_user(
        session_factory, roles=["user", "operator"], email_prefix="mod-operator"
    )
    trip_id, _, attachment_id, share_id = await _seed_trip_targets(
        session_factory,
        owner_id=owner_id,
    )

    trip_report = await _create_report(
        client,
        auth_cookies=auth_cookies,
        actor_id=owner_id,
        target_type="trip",
        target_id=trip_id,
        reason_code="safety",
    )
    attachment_report = await _create_report(
        client,
        auth_cookies=auth_cookies,
        actor_id=owner_id,
        target_type="attachment",
        target_id=attachment_id,
        reason_code="illegal",
    )
    share_report = await _create_report(
        client,
        auth_cookies=auth_cookies,
        actor_id=owner_id,
        target_type="share_link",
        target_id=share_id,
        reason_code="privacy",
    )

    for report in [trip_report, attachment_report, share_report]:
        response = await client.post(
            f"/admin/moderation/reports/{report['report_id']}/takedown",
            json={
                "access_reason": "운영정책 위반",
                "resolution_summary": "게시중단 처리",
            },
            cookies=auth_cookies(str(admin_id)),
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == "taken_down"

    async with session_factory() as db:
        trip = await db.get(Trip, trip_id)
        attachment = await db.get(CuratedPlanAttachment, attachment_id)
        share = await db.get(TripShareLink, share_id)
        report_count = await db.scalar(select(func.count()).select_from(ContentReport))

    assert trip is not None
    assert trip.deleted_at is not None
    assert trip.status == "archived"
    assert attachment is not None
    assert attachment.deleted_at is not None
    assert share is not None
    assert share.revoked_at is not None
    assert report_count == 3


async def test_content_report_permission_and_invalid_transition(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    owner_id = await _create_user(session_factory, roles=["user"], email_prefix="mod-owner-3")
    stranger_id = await _create_user(session_factory, roles=["user"], email_prefix="mod-stranger")
    admin_id = await _create_user(
        session_factory, roles=["user", "admin"], email_prefix="mod-admin-invalid"
    )
    trip_id, _, _, _ = await _seed_trip_targets(session_factory, owner_id=owner_id)

    denied = await client.post(
        "/users/me/content-reports",
        json={
            "target_type": "share_link",
            "target_id": str(uuid.uuid4()),
            "reason_code": "privacy",
            "reason_text": "접근 불가",
        },
        cookies=auth_cookies(str(stranger_id)),
    )
    assert denied.status_code == 404

    created = await _create_report(
        client,
        auth_cookies=auth_cookies,
        actor_id=owner_id,
        target_type="trip",
        target_id=trip_id,
    )
    invalid = await client.post(
        f"/admin/moderation/reports/{created['report_id']}/restore",
        json={"access_reason": "순서 오류", "resolution_summary": "복구 시도"},
        cookies=auth_cookies(str(admin_id)),
    )
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "INVALID_STATE"
