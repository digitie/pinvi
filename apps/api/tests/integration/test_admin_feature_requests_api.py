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
    actor = "pinvi-admin"

    def __init__(self, state: str = "applied") -> None:
        self.outbound_calls: list[dict[str, Any]] = []

    async def get_feature_revision_etag(self, feature_id: str) -> str:
        return '"7"'

    async def patch_feature(
        self,
        feature_id: str,
        payload: dict[str, Any],
        *,
        expected_revision: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self.outbound_calls.append(
            {
                "method": "PATCH",
                "feature_id": feature_id,
                "payload": dict(payload),
                "if_match": expected_revision,
                "idempotency_key": idempotency_key,
            }
        )
        return {
            "feature_id": feature_id,
            "row_revision": 8,
            "command_id": 12,
            "applied_field_count": 1,
        }

    async def delete_feature(
        self,
        feature_id: str,
        *,
        reason: str,
        expected_revision: str,
        idempotency_key: str,
        operator: str | None = None,
    ) -> dict[str, Any]:
        self.outbound_calls.append(
            {
                "method": "DELETE",
                "feature_id": feature_id,
                "reason": reason,
                "operator": operator,
                "if_match": expected_revision,
                "idempotency_key": idempotency_key,
            }
        )
        return {
            "feature_id": feature_id,
            "row_revision": 8,
            "audit_transition_id": 13,
            "lifecycle_state": "retired",
            "publication_state": "published",
            "quality_state": "valid",
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


async def test_dry_run_has_no_map_or_local_mutation(
    client: Any, session_factory: Any, auth_cookies: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin_id = await _create_user(session_factory, email="admin@example.com", roles=["admin"])
    req_id = await _create_suggestion(session_factory, requester_id=admin_id)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("dry-run must not construct a Map client")

    monkeypatch.setattr(feature_request_router, "get_feature_request_service_client", forbidden)
    monkeypatch.setattr(feature_request_router, "get_kor_travel_map_admin_client", forbidden)
    response = await client.post(
        f"/admin/feature-requests/{req_id}/approve?dry_run=1",
        json={"access_reason": "형식 검사"},
        cookies=auth_cookies(str(admin_id)),
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["dry_run"] is True
    assert response.json()["data"]["status"] == "pending"
    async with session_factory() as db:
        row = await db.get(FeatureSuggestion, req_id)
        assert row is not None and row.status == "pending"
        assert row.kor_travel_map_ref is None and row.resolved_at is None
        assert await db.scalar(select(func.count()).select_from(AdminAuditLog)) == 0


@pytest.mark.parametrize("terminal_status", ["rejected", "added", "duplicate"])
async def test_delete_completed_request_preserves_audit(
    client: Any, session_factory: Any, auth_cookies: Any, terminal_status: str
) -> None:
    admin_id = await _create_user(session_factory, email="admin@example.com", roles=["admin"])
    req_id = await _create_suggestion(session_factory, requester_id=admin_id)
    async with session_factory() as db:
        row = await db.get(FeatureSuggestion, req_id)
        assert row is not None
        row.status = terminal_status
        row.kor_travel_map_ref = {"feature_id": "f_preserved", "command_id": 123}
        await db.commit()
    response = await client.request(
        "DELETE",
        f"/admin/feature-requests/{req_id}",
        json={"access_reason": "처리 이력 정리"},
        cookies=auth_cookies(str(admin_id)),
    )
    assert response.status_code == 204, response.text
    async with session_factory() as db:
        assert await db.get(FeatureSuggestion, req_id) is None
        audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.action == "feature_request.delete")
        )
        assert audit is not None
        assert audit.before_state["status"] == terminal_status
        assert audit.before_state["kor_travel_map_ref"]["command_id"] == 123
    again = await client.request(
        "DELETE",
        f"/admin/feature-requests/{req_id}",
        json={"access_reason": "다시 정리"},
        cookies=auth_cookies(str(admin_id)),
    )
    assert again.status_code == 404


@pytest.mark.parametrize("request_status", ["pending", "approved"])
async def test_delete_inflight_request_is_rejected(
    client: Any, session_factory: Any, auth_cookies: Any, request_status: str
) -> None:
    admin_id = await _create_user(session_factory, email="admin@example.com", roles=["admin"])
    req_id = await _create_suggestion(session_factory, requester_id=admin_id)
    async with session_factory() as db:
        row = await db.get(FeatureSuggestion, req_id)
        assert row is not None
        row.status = request_status
        await db.commit()
    response = await client.request(
        "DELETE",
        f"/admin/feature-requests/{req_id}",
        json={"access_reason": "삭제 시도"},
        cookies=auth_cookies(str(admin_id)),
    )
    assert response.status_code == 409


async def test_uncertain_direct_command_replays_original_revision_and_key(
    client: Any, session_factory: Any, auth_cookies: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.clients.kor_travel_map import KorTravelMapUnavailable

    admin_id = await _create_user(session_factory, email="admin@example.com", roles=["admin"])
    req_id = await _create_suggestion(
        session_factory,
        requester_id=admin_id,
        suggestion_type="correction",
        target_feature_id="f_existing",
    )

    class Uncertain(_FakeAdminClient):
        revision_reads = 0

        async def get_feature_revision_etag(self, feature_id: str) -> str:
            self.revision_reads += 1
            return '"7"' if self.revision_reads == 1 else '"8"'

        async def patch_feature(
            self,
            feature_id: str,
            payload: dict[str, Any],
            *,
            expected_revision: str,
            idempotency_key: str,
        ) -> dict[str, Any]:
            result = await super().patch_feature(
                feature_id,
                payload,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
            )
            if len(self.outbound_calls) == 1:
                raise KorTravelMapUnavailable("response lost after commit")
            return result

    fake = Uncertain()
    _override_admin_client(monkeypatch, fake)
    body = {"access_reason": "현장 확인", "name": "새 이름"}
    response = await client.post(
        f"/admin/feature-requests/{req_id}/approve", json=body, cookies=auth_cookies(str(admin_id))
    )
    assert response.status_code == 503, response.text
    async with session_factory() as db:
        row = await db.get(FeatureSuggestion, req_id)
        assert row is not None and row.status == "pending"
        assert row.kor_travel_map_ref["dispatch"]["expected_revision"] == '"7"'
    reject = await client.post(
        f"/admin/feature-requests/{req_id}/reject",
        json={"access_reason": "취소"},
        cookies=auth_cookies(str(admin_id)),
    )
    assert reject.status_code == 409
    changed = await client.post(
        f"/admin/feature-requests/{req_id}/approve",
        json={**body, "name": "다른 이름"},
        cookies=auth_cookies(str(admin_id)),
    )
    assert changed.status_code == 409
    retry = await client.post(
        f"/admin/feature-requests/{req_id}/approve", json=body, cookies=auth_cookies(str(admin_id))
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["data"]["status"] == "added"
    assert fake.revision_reads == 1
    assert fake.outbound_calls[0] == fake.outbound_calls[1]
    assert fake.outbound_calls[1]["if_match"] == '"7"'
    assert fake.outbound_calls[1]["idempotency_key"] == str(req_id)


async def test_non_admin_new_admin_operations_remain_hidden(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    user_id = await _create_user(session_factory, email="plain@example.com")
    req_id = await _create_suggestion(session_factory, requester_id=user_id)
    for method, path in [
        ("POST", f"/admin/feature-requests/{req_id}/approve?dry_run=1"),
        ("DELETE", f"/admin/feature-requests/{req_id}"),
    ]:
        response = await client.request(
            method, path, json={"access_reason": "권한 확인"}, cookies=auth_cookies(str(user_id))
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


async def test_auth_failure_after_uncertain_commit_never_clears_dispatch(
    client: Any, session_factory: Any, auth_cookies: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from app.clients.kor_travel_map_admin import KorTravelMapAdminClient

    admin_id = await _create_user(session_factory, email="admin@example.com", roles=["admin"])
    req_id = await _create_suggestion(
        session_factory,
        requester_id=admin_id,
        suggestion_type="correction",
        target_feature_id="f_existing",
    )
    mutation_calls = 0

    def transport(request: httpx.Request) -> httpx.Response:
        nonlocal mutation_calls
        if request.method == "GET":
            return httpx.Response(200, headers={"ETag": '"7"'}, json={"data": {"row_revision": 7}})
        mutation_calls += 1
        if mutation_calls == 1:
            raise httpx.ReadError("committed response lost", request=request)
        return httpx.Response(403, json={"code": "FORBIDDEN"})

    async with httpx.AsyncClient(
        base_url="http://map.test", transport=httpx.MockTransport(transport)
    ) as http:
        actual = KorTravelMapAdminClient(http, max_attempts=1)
        monkeypatch.setattr(
            feature_request_router, "get_kor_travel_map_admin_client", lambda request: actual
        )
        for _ in range(2):
            response = await client.post(
                f"/admin/feature-requests/{req_id}/approve",
                json={"access_reason": "확인", "name": "새 이름"},
                cookies=auth_cookies(str(admin_id)),
            )
            assert response.status_code == 503, response.text
        async with session_factory() as db:
            row = await db.get(FeatureSuggestion, req_id)
            assert row is not None and row.status == "pending"
            assert row.kor_travel_map_ref["dispatch"]["expected_revision"] == '"7"'
        reject = await client.post(
            f"/admin/feature-requests/{req_id}/reject",
            json={"access_reason": "거절"},
            cookies=auth_cookies(str(admin_id)),
        )
        assert reject.status_code == 409


async def test_relock_cannot_send_or_clear_a_replaced_dispatch(
    client: Any, session_factory: Any, auth_cookies: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio
    from contextvars import ContextVar

    from app.clients.kor_travel_map import KorTravelMapPreconditionFailed, KorTravelMapUnavailable

    admin_id = await _create_user(session_factory, email="admin@example.com", roles=["admin"])
    req_id = await _create_suggestion(
        session_factory,
        requester_id=admin_id,
        suggestion_type="correction",
        target_feature_id="f_existing",
    )
    a_waiting, c_waiting = asyncio.Event(), asyncio.Event()
    release_a, release_c = asyncio.Event(), asyncio.Event()
    original_load = feature_request_router._load_pending
    counts: dict[str, int] = {}
    race_label: ContextVar[str] = ContextVar("race_label", default="B")

    async def controlled_load(db: Any, request_id: uuid.UUID) -> FeatureSuggestion:
        name = race_label.get()
        counts[name] = counts.get(name, 0) + 1
        if counts[name] == 2 and name in {"stale-A", "fresh-C"}:
            waiting, release = (
                (a_waiting, release_a) if name == "stale-A" else (c_waiting, release_c)
            )
            waiting.set()
            await asyncio.wait_for(release.wait(), timeout=10)
        return await original_load(db, request_id)

    monkeypatch.setattr(feature_request_router, "_load_pending", controlled_load)

    class Racing(_FakeAdminClient):
        revisions = 0

        async def get_feature_revision_etag(self, feature_id: str) -> str:
            self.revisions += 1
            return '"7"' if self.revisions == 1 else '"8"'

        async def patch_feature(
            self,
            feature_id: str,
            payload: dict[str, Any],
            *,
            expected_revision: str,
            idempotency_key: str,
        ) -> dict[str, Any]:
            await super().patch_feature(
                feature_id,
                payload,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
            )
            if expected_revision == '"7"':
                raise KorTravelMapPreconditionFailed("stale", code="PRECONDITION_FAILED")
            raise KorTravelMapUnavailable("new command committed but response lost")

    fake = Racing()
    _override_admin_client(monkeypatch, fake)

    async def approve(label: str = "B") -> Any:
        race_label.set(label)
        async with session_factory() as db:
            current = await db.get(FeatureSuggestion, req_id)
            ref = current.kor_travel_map_ref or {}
            key = (
                (ref.get("dispatch") or {}).get("command_key")
                or ref.get("next_command_key")
                or str(req_id)
            )
        return await client.post(
            f"/admin/feature-requests/{req_id}/approve",
            json={"access_reason": "검수", "name": "새 이름", "expected_command_key": key},
            cookies=auth_cookies(str(admin_id)),
        )

    a = asyncio.create_task(approve("stale-A"), name="stale-A")
    c: asyncio.Task[Any] | None = None
    try:
        await asyncio.wait_for(a_waiting.wait(), timeout=10)
        b = await approve()
        assert b.status_code == 412
        c = asyncio.create_task(approve("fresh-C"), name="fresh-C")
        await asyncio.wait_for(c_waiting.wait(), timeout=10)
        release_a.set()
        stale = await a
        assert stale.status_code == 409
        assert len(fake.outbound_calls) == 1
        release_c.set()
        fresh = await c
        assert fresh.status_code == 503
        async with session_factory() as db:
            row = await db.get(FeatureSuggestion, req_id)
            assert row is not None and row.status == "pending"
            assert row.kor_travel_map_ref["dispatch"]["expected_revision"] == '"8"'
    finally:
        release_a.set()
        release_c.set()
        await asyncio.gather(a, *([c] if c else []), return_exceptions=True)
