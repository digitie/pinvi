"""Admin feature-request 검토 큐 통합 테스트 (T-179).

kor_travel_map admin client는 `app.dependency_overrides`로 fake 주입 — fake는 change API의
`data.request`(record)에 해당하는 dict를 반환한다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select

from app.clients.kor_travel_map_admin import get_kor_travel_map_admin_client
from app.main import app
from app.models.audit import AdminAuditLog
from app.models.feature_suggestion import FeatureSuggestion
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _create_user(
    session_factory: Any,
    *,
    email: str,
    roles: list[str] | None = None,
) -> uuid.UUID:
    async with session_factory() as db:
        user = User(
            email=email,
            password_hash="x",
            status="active",
            roles=roles or ["user"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def _create_suggestion(
    session_factory: Any,
    *,
    requester_id: uuid.UUID,
    suggestion_type: str = "new_place",
    target_feature_id: str | None = None,
) -> uuid.UUID:
    async with session_factory() as db:
        row = FeatureSuggestion(
            requester_user_id=requester_id,
            suggestion_type=suggestion_type,
            target_feature_id=target_feature_id,
            kind="place",
            name="새 카페",
            lng=Decimal("129.000000"),
            lat=Decimal("35.000000"),
            categories=["카페"],
            note="좋은 곳",
            status="pending",
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.request_id


class _FakeAdminClient:
    def __init__(self, state: str = "applied") -> None:
        self.created: dict[str, Any] | None = None
        self.deleted: dict[str, Any] | None = None
        self._state = state

    async def create_feature(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created = dict(payload)
        return {
            "feature_id": "f_new_1",
            "request_id": "krq-1",
            "status": self._state,
            "review_mode": "immediate",
            "action": "create",
        }

    async def patch_feature(self, feature_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "feature_id": feature_id,
            "request_id": "krq-2",
            "status": self._state,
            "review_mode": "immediate",
            "action": "update",
        }

    async def delete_feature(
        self, feature_id: str, *, reason: str, operator: str | None = None
    ) -> dict[str, Any]:
        self.deleted = {"feature_id": feature_id, "reason": reason, "operator": operator}
        return {
            "feature_id": feature_id,
            "request_id": "krq-3",
            "status": self._state,
            "review_mode": "immediate",
            "action": "delete",
        }


def _override(fake: Any) -> None:
    app.dependency_overrides[get_kor_travel_map_admin_client] = lambda: fake


def _clear() -> None:
    app.dependency_overrides.pop(get_kor_travel_map_admin_client, None)


async def test_list_pending_masks_requester_email(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    requester_id = await _create_user(session_factory, email="reporter@example.com")
    await _create_suggestion(session_factory, requester_id=requester_id)

    resp = await client.get("/admin/feature-requests", cookies=auth_cookies(str(admin_id)))

    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["total"] == 1
    item = body["items"][0]
    assert item["status"] == "pending"
    assert item["requester_email_masked"] == "r***@example.com"
    assert item["coord"] == {"lon": 129.0, "lat": 35.0}
    assert "reporter@example.com" not in resp.text


async def test_approve_new_place_calls_kor_travel_map_and_marks_added(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    requester_id = await _create_user(session_factory, email="reporter@example.com")
    req_id = await _create_suggestion(session_factory, requester_id=requester_id)
    fake = _FakeAdminClient(state="applied")
    _override(fake)
    try:
        resp = await client.post(
            f"/admin/feature-requests/{req_id}/approve",
            json={
                "access_reason": "검토 완료 — 실재 확인",
                "category": "01070100",
                "marker_color": "P-07",
                "marker_icon": "cafe",
            },
            headers={"X-Request-Id": str(uuid.uuid4())},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "added"  # applied → added
    assert data["kor_travel_map_ref"]["feature_id"] == "f_new_1"
    assert data["kor_travel_map_ref"]["request_id"] == "krq-1"
    assert fake.created is not None
    assert fake.created["kind"] == "place"
    assert fake.created["category"] == "01070100"
    assert fake.created["coord"] == {"lon": 129.0, "lat": 35.0}
    assert fake.created["idempotency_key"] == str(req_id)
    # §7 #3 확정: operator 고정(admin id 미노출) + reason에 [suggestion:<id>] 출처 prefix
    assert fake.created["operator"] == "pinvi-admin"
    assert fake.created["reason"].startswith(f"[suggestion:{req_id}]")

    async with session_factory() as db:
        audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.action == "feature_request.approve")
        )
        stored = await db.scalar(
            select(FeatureSuggestion).where(FeatureSuggestion.request_id == req_id)
        )
    assert audit is not None
    assert stored is not None
    assert stored.status == "added"
    assert stored.reviewed_by_admin_id == admin_id


async def test_approve_new_place_requires_marker_fields(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    requester_id = await _create_user(session_factory, email="reporter@example.com")
    req_id = await _create_suggestion(session_factory, requester_id=requester_id)
    fake = _FakeAdminClient()
    _override(fake)
    try:
        resp = await client.post(
            f"/admin/feature-requests/{req_id}/approve",
            json={"access_reason": "검토"},  # category/marker_* 누락
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 422
    assert fake.created is None


async def test_reject_sets_status_rejected(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    requester_id = await _create_user(session_factory, email="reporter@example.com")
    req_id = await _create_suggestion(session_factory, requester_id=requester_id)

    resp = await client.post(
        f"/admin/feature-requests/{req_id}/reject",
        json={"access_reason": "중복 제안"},
        headers={"X-Request-Id": str(uuid.uuid4())},
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "rejected"


async def test_approve_already_resolved_conflicts(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    requester_id = await _create_user(session_factory, email="reporter@example.com")
    req_id = await _create_suggestion(session_factory, requester_id=requester_id)
    # 먼저 거절해 resolved 상태로 만든다.
    await client.post(
        f"/admin/feature-requests/{req_id}/reject",
        json={"access_reason": "중복"},
        cookies=auth_cookies(str(admin_id)),
    )
    fake = _FakeAdminClient()
    _override(fake)
    try:
        resp = await client.post(
            f"/admin/feature-requests/{req_id}/approve",
            json={
                "access_reason": "재승인 시도",
                "category": "01070100",
                "marker_color": "P-07",
                "marker_icon": "cafe",
            },
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 409
    assert fake.created is None


async def test_non_admin_is_hidden(client: Any, session_factory: Any, auth_cookies: Any) -> None:
    user_id = await _create_user(session_factory, email="plain@example.com")  # role=user
    resp = await client.get("/admin/feature-requests", cookies=auth_cookies(str(user_id)))
    assert resp.status_code == 404
