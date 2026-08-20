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
from sqlalchemy import func, select

from app.api.v1.admin import feature_requests as feature_request_router
from app.clients.kor_travel_map_feature_request import (
    FeatureRequestQueueProblem,
    FeatureRequestQueueUnavailable,
    FeatureRequestReceipt,
)
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
    latitude: Decimal = Decimal("35.000000"),
) -> uuid.UUID:
    async with session_factory() as db:
        row = FeatureSuggestion(
            requester_user_id=requester_id,
            suggestion_type=suggestion_type,
            target_feature_id=target_feature_id,
            kind="place",
            name="새 카페",
            lng=Decimal("129.000000"),
            lat=latitude,
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
        self.outbound_calls: list[dict[str, Any]] = []
        self._state = state

    async def patch_feature(self, feature_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.outbound_calls.append(
            {"method": "PATCH", "feature_id": feature_id, "payload": dict(payload)}
        )
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
        self.outbound_calls.append(
            {
                "method": "DELETE",
                "feature_id": feature_id,
                "reason": reason,
                "operator": operator,
            }
        )
        return {
            "feature_id": feature_id,
            "request_id": "krq-3",
            "status": self._state,
            "review_mode": "immediate",
            "action": "delete",
        }


class _FakeFeatureRequestClient:
    def __init__(self, *, queue_status: str = "pending") -> None:
        self.calls: list[dict[str, Any]] = []
        self.queue_status = queue_status

    async def submit(self, **kwargs: Any) -> FeatureRequestReceipt:
        self.calls.append(dict(kwargs))
        request_id = kwargs["request_id"]
        assert isinstance(request_id, uuid.UUID)
        return FeatureRequestReceipt.model_validate(
            {
                "request_id": str(request_id),
                "status": self.queue_status,
                "kind": kwargs["kind"],
                "name": kwargs["name"],
                "coord": {"lon": kwargs["lon"], "lat": kwargs["lat"]},
                "categories": kwargs["categories"],
                "note": kwargs["note"],
                "submitted_at": "2026-08-20T09:00:00+09:00",
                "resolved_at": None,
                "resolved_by_actor": None,
                "feature_id": "01900000-0000-7000-8000-000000000001"
                if self.queue_status == "exact_conflict"
                else None,
                "rejection_reason": None,
            }
        )


class _UnavailableFeatureRequestClient:
    async def submit(self, **kwargs: Any) -> FeatureRequestReceipt:
        raise FeatureRequestQueueUnavailable("test outage")


class _ProblemFeatureRequestClient:
    def __init__(self, *, status_code: int, code: str) -> None:
        self._status_code = status_code
        self._code = code

    async def submit(self, **kwargs: Any) -> FeatureRequestReceipt:
        raise FeatureRequestQueueProblem(status_code=self._status_code, code=self._code)


def _override_admin_client(monkeypatch: pytest.MonkeyPatch, fake: Any) -> None:
    monkeypatch.setattr(
        feature_request_router,
        "get_kor_travel_map_admin_client",
        lambda _request: fake,
    )


def _override_feature_request_client(monkeypatch: pytest.MonkeyPatch, fake: Any) -> None:
    monkeypatch.setattr(
        feature_request_router,
        "get_feature_request_service_client",
        lambda _request: fake,
    )


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


async def test_approve_new_place_submits_generic_map_queue_and_commits_after_receipt(
    client: Any, session_factory: Any, auth_cookies: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    requester_id = await _create_user(session_factory, email="reporter@example.com")
    req_id = await _create_suggestion(session_factory, requester_id=requester_id)
    fake_admin = _FakeAdminClient(state="applied")
    fake_queue = _FakeFeatureRequestClient()
    _override_admin_client(monkeypatch, fake_admin)
    _override_feature_request_client(monkeypatch, fake_queue)
    resp = await client.post(
        f"/admin/feature-requests/{req_id}/approve",
        json={
            "access_reason": "검토 완료 — 실재 확인",
            "category": "01070100",
            "marker_color": "P-07",
            "marker_icon": "cafe",
        },
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "approved"
    assert fake_admin.outbound_calls == []
    assert len(fake_queue.calls) == 1
    call = fake_queue.calls[0]
    assert call["request_id"] == req_id
    assert call["kind"] == "place"
    assert call["categories"] == ["카페"]
    response_request_id = uuid.UUID(resp.headers["X-Request-Id"])
    assert call["correlation_id"] == response_request_id

    async with session_factory() as db:
        audits = list(
            (
                await db.scalars(
                    select(AdminAuditLog).where(
                        AdminAuditLog.action == "feature_request.approve",
                        AdminAuditLog.resource_id == str(req_id),
                    )
                )
            ).all()
        )
        stored = await db.scalar(
            select(FeatureSuggestion).where(FeatureSuggestion.request_id == req_id)
        )
    assert len(audits) == 1
    assert audits[0].request_id == response_request_id
    assert stored is not None
    assert stored.status == "approved"
    assert stored.kor_travel_map_ref == {
        "feature_id": None,
        "request_id": str(req_id),
        "state": "pending",
        "review_mode": "feature_request_queue",
        "action": "submit",
        "reconciled_poi_count": 0,
    }
    assert stored.reviewed_by_admin_id == admin_id
    assert stored.resolved_at is not None


async def test_approve_new_place_rejects_invalid_request_id_before_queue_submit(
    client: Any, session_factory: Any, auth_cookies: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    requester_id = await _create_user(session_factory, email="reporter@example.com")
    req_id = await _create_suggestion(session_factory, requester_id=requester_id)
    fake_queue = _FakeFeatureRequestClient()
    _override_feature_request_client(monkeypatch, fake_queue)

    resp = await client.post(
        f"/admin/feature-requests/{req_id}/approve",
        json={"access_reason": "검토"},
        headers={"X-Request-Id": "not-a-uuid"},
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 422
    assert fake_queue.calls == []


async def test_approve_legacy_out_of_range_new_place_stays_pending_without_queue_submit(
    client: Any, session_factory: Any, auth_cookies: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    requester_id = await _create_user(session_factory, email="reporter@example.com")
    req_id = await _create_suggestion(
        session_factory,
        requester_id=requester_id,
        latitude=Decimal("39.500001"),
    )
    fake_queue = _FakeFeatureRequestClient()
    _override_feature_request_client(monkeypatch, fake_queue)

    resp = await client.post(
        f"/admin/feature-requests/{req_id}/approve",
        json={"access_reason": "범위 검토"},
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "MAP_FEATURE_REQUEST_PAYLOAD_INVALID"
    assert fake_queue.calls == []
    async with session_factory() as db:
        stored = await db.scalar(
            select(FeatureSuggestion).where(FeatureSuggestion.request_id == req_id)
        )
    assert stored is not None
    assert stored.status == "pending"


async def test_approve_new_place_without_queue_keeps_pending_before_body_specific_fields(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    requester_id = await _create_user(session_factory, email="reporter@example.com")
    req_id = await _create_suggestion(session_factory, requester_id=requester_id)
    resp = await client.post(
        f"/admin/feature-requests/{req_id}/approve",
        json={"access_reason": "검토"},  # category/marker_* 누락
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "MAP_FEATURE_REQUEST_QUEUE_UNAVAILABLE"


async def test_approve_new_place_queue_outage_keeps_local_suggestion_pending(
    client: Any, session_factory: Any, auth_cookies: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    requester_id = await _create_user(session_factory, email="reporter@example.com")
    req_id = await _create_suggestion(session_factory, requester_id=requester_id)
    _override_feature_request_client(monkeypatch, _UnavailableFeatureRequestClient())
    resp = await client.post(
        f"/admin/feature-requests/{req_id}/approve",
        json={"access_reason": "검토"},
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "MAP_FEATURE_REQUEST_QUEUE_UNAVAILABLE"
    async with session_factory() as db:
        stored = await db.scalar(
            select(FeatureSuggestion).where(FeatureSuggestion.request_id == req_id)
        )
    assert stored is not None
    assert stored.status == "pending"
    assert stored.kor_travel_map_ref is None


async def test_approve_new_place_exact_conflict_commits_duplicate_receipt(
    client: Any, session_factory: Any, auth_cookies: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    requester_id = await _create_user(session_factory, email="reporter@example.com")
    req_id = await _create_suggestion(session_factory, requester_id=requester_id)
    _override_feature_request_client(
        monkeypatch,
        _FakeFeatureRequestClient(queue_status="exact_conflict"),
    )

    resp = await client.post(
        f"/admin/feature-requests/{req_id}/approve",
        json={"access_reason": "기존 동일 장소 확인"},
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "duplicate"
    async with session_factory() as db:
        stored = await db.scalar(
            select(FeatureSuggestion).where(FeatureSuggestion.request_id == req_id)
        )
    assert stored is not None
    assert stored.kor_travel_map_ref is not None
    assert stored.kor_travel_map_ref["state"] == "exact_conflict"
    assert stored.kor_travel_map_ref["feature_id"] == "01900000-0000-7000-8000-000000000001"


@pytest.mark.parametrize(
    ("map_status", "map_code"),
    [
        (409, "IDEMPOTENCY_PAYLOAD_CONFLICT"),
        (422, "FEATURE_REQUEST_VALIDATION"),
    ],
)
async def test_approve_new_place_rejected_by_map_keeps_local_suggestion_pending(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
    map_status: int,
    map_code: str,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    requester_id = await _create_user(session_factory, email="reporter@example.com")
    req_id = await _create_suggestion(session_factory, requester_id=requester_id)
    _override_feature_request_client(
        monkeypatch,
        _ProblemFeatureRequestClient(status_code=map_status, code=map_code),
    )

    resp = await client.post(
        f"/admin/feature-requests/{req_id}/approve",
        json={"access_reason": "큐 거절 확인"},
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == map_status, resp.text
    assert resp.json()["error"]["code"] == map_code
    async with session_factory() as db:
        stored = await db.scalar(
            select(FeatureSuggestion).where(FeatureSuggestion.request_id == req_id)
        )
        audit_count = await db.scalar(
            select(func.count(AdminAuditLog.log_id)).where(
                AdminAuditLog.action == "feature_request.approve",
                AdminAuditLog.resource_id == str(req_id),
            )
        )
    assert stored is not None
    assert stored.status == "pending"
    assert stored.kor_travel_map_ref is None
    assert audit_count == 0


@pytest.mark.parametrize(
    ("suggestion_type", "approval_body", "expected_method"),
    [
        ("correction", {"access_reason": "정보 수정", "name": "수정된 장소"}, "PATCH"),
        ("closure", {"access_reason": "폐업 확인"}, "DELETE"),
    ],
)
async def test_approve_existing_feature_changes_keep_map_outbound(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    suggestion_type: str,
    approval_body: dict[str, str],
    expected_method: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    requester_id = await _create_user(session_factory, email="reporter@example.com")
    req_id = await _create_suggestion(
        session_factory,
        requester_id=requester_id,
        suggestion_type=suggestion_type,
        target_feature_id="f_existing_1",
    )
    fake = _FakeAdminClient(state="applied")
    _override_admin_client(monkeypatch, fake)
    resp = await client.post(
        f"/admin/feature-requests/{req_id}/approve",
        json=approval_body,
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "added"
    assert len(fake.outbound_calls) == 1
    assert fake.outbound_calls[0]["method"] == expected_method
    assert fake.outbound_calls[0]["feature_id"] == "f_existing_1"


async def test_approve_correction_without_mutation_is_rejected_before_map_call(
    client: Any, session_factory: Any, auth_cookies: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    requester_id = await _create_user(session_factory, email="reporter@example.com")
    req_id = await _create_suggestion(
        session_factory,
        requester_id=requester_id,
        suggestion_type="correction",
        target_feature_id="f_existing_1",
    )
    fake = _FakeAdminClient()
    _override_admin_client(monkeypatch, fake)

    resp = await client.post(
        f"/admin/feature-requests/{req_id}/approve",
        json={"access_reason": "변경 필드 없음"},
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 422
    assert fake.outbound_calls == []


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
    client: Any, session_factory: Any, auth_cookies: Any, monkeypatch: pytest.MonkeyPatch
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
    _override_admin_client(monkeypatch, fake)
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

    assert resp.status_code == 409
    assert fake.outbound_calls == []


async def test_non_admin_is_hidden(client: Any, session_factory: Any, auth_cookies: Any) -> None:
    user_id = await _create_user(session_factory, email="plain@example.com")  # role=user
    resp = await client.get("/admin/feature-requests", cookies=auth_cookies(str(user_id)))
    assert resp.status_code == 404
