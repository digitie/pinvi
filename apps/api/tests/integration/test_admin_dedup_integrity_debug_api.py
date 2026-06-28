"""Admin dedup/integrity/debug ops proxy 통합 테스트 (T-212)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.clients.kor_travel_map import KorTravelMapUnavailable
from app.clients.kor_travel_map_admin import get_kor_travel_map_admin_client
from app.main import app
from app.models.api_call_log import ApiCallLog
from app.models.attachment import CuratedPlanAttachment
from app.models.audit import AdminAuditLog, LocationAccessLog
from app.models.curated_plan import CuratedPlanPoi, CuratedTripPlan
from app.models.data_integrity import DataIntegrityViolation
from app.models.email_queue import EmailQueue
from app.models.poi import TripDayPoi
from app.models.trip import Trip
from app.models.trip_day import TripDay
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


def _dedup_item() -> dict[str, Any]:
    return {
        "review_id": "dedup-1",
        "status": "pending",
        "total_score": 88,
        "name_score": 90,
        "spatial_score": 80,
        "category_score": 95,
        "distance_m": 12.5,
        "feature_a": {
            "feature_id": "f_a",
            "name": "해운대 카페",
            "kind": "place",
            "category": "01010100",
            "lon": 129.1,
            "lat": 35.1,
            "provider": "kma",
            "dataset_key": "places",
        },
        "feature_b": {
            "feature_id": "f_b",
            "name": "해운대 까페",
            "kind": "place",
            "category": "01010100",
            "lon": 129.1001,
            "lat": 35.1001,
            "provider": "visitkorea",
            "dataset_key": "places",
        },
        "created_at": "2026-06-12T00:00:00+09:00",
    }


def _issue_item() -> dict[str, Any]:
    return {
        "issue_id": "iss-1",
        "violation_type": "missing_coord",
        "severity": "error",
        "message": "좌표 없음",
        "payload": {"field": "coord"},
        "status": "open",
        "detected_at": "2026-06-12T00:00:00+09:00",
        "provider": "kma",
        "dataset_key": "places",
        "feature_id": "f_a",
        "source_record_key": "kma:places:1",
        "resolved_at": None,
    }


class _FakeOpsClient:
    def __init__(self) -> None:
        self.dedup_kwargs: dict[str, Any] | None = None
        self.issue_kwargs: dict[str, Any] | None = None
        self.report_kwargs: dict[str, Any] | None = None
        self.system_log_kwargs: dict[str, Any] | None = None
        self.api_log_kwargs: dict[str, Any] | None = None
        self.decision_args: tuple[str, dict[str, Any]] | None = None
        self.issue_action_args: tuple[str, dict[str, Any]] | None = None

    async def list_dedup_reviews(self, **kwargs: Any) -> dict[str, Any]:
        self.dedup_kwargs = kwargs
        return {
            "data": {"items": [_dedup_item()]},
            "meta": {"page": {"next_cursor": "dedup-next"}},
        }

    async def decide_dedup_review(self, review_id: str, **kwargs: Any) -> dict[str, Any]:
        self.decision_args = (review_id, kwargs)
        return {
            "review_id": review_id,
            "decision": kwargs["decision"],
            "changed": True,
            "master_feature_id": kwargs.get("master_feature_id"),
            "loser_feature_id": "f_b",
            "merge_id": "merge-1",
            "source_links_moved": 2,
            "source_links_dropped": 0,
        }

    async def list_integrity_issues(self, **kwargs: Any) -> dict[str, Any]:
        self.issue_kwargs = kwargs
        return {
            "data": {"items": [_issue_item()]},
            "meta": {"page": {"next_cursor": "issue-next"}},
        }

    async def patch_admin_issue(self, issue_id: str, **kwargs: Any) -> dict[str, Any]:
        self.issue_action_args = (issue_id, kwargs)
        issue = _issue_item()
        issue["status"] = "resolved"
        issue["resolved_at"] = "2026-06-12T00:03:00+09:00"
        return {"data": {"issue": issue}, "meta": {}}

    async def list_consistency_reports(self, **kwargs: Any) -> dict[str, Any]:
        self.report_kwargs = kwargs
        return {
            "data": {
                "items": [
                    {
                        "report_id": "rep-1",
                        "batch_id": "batch-1",
                        "started_at": "2026-06-12T00:00:00+09:00",
                        "finished_at": None,
                        "severity_max": "WARN",
                        "cases": [{"name": "coverage"}],
                        "summary": {"issues": 1},
                    }
                ]
            },
            "meta": {"page": {"next_cursor": "report-next"}},
        }

    async def list_system_logs(self, **kwargs: Any) -> dict[str, Any]:
        self.system_log_kwargs = kwargs
        request_id = kwargs.get("request_id", "req-1")
        return {
            "data": {
                "items": [
                    {
                        "log_id": "log-1",
                        "level": "error",
                        "source": "api",
                        "event": "provider.timeout",
                        "message": "provider timeout",
                        "detail": {"provider": "kma"},
                        "request_id": request_id,
                        "created_at": "2026-06-12T00:00:00+09:00",
                    }
                ]
            },
            "meta": {"page": {"next_cursor": "log-next"}},
        }

    async def list_ops_api_call_logs(self, **kwargs: Any) -> dict[str, Any]:
        self.api_log_kwargs = kwargs
        request_id = kwargs.get("request_id", "req-1")
        return {
            "data": {
                "items": [
                    {
                        "log_id": "api-1",
                        "method": "GET",
                        "path": "/v1/features",
                        "status_code": 503,
                        "duration_ms": 1200,
                        "request_id": request_id,
                        "error_code": "UPSTREAM_TIMEOUT",
                        "created_at": "2026-06-12T00:00:00+09:00",
                    }
                ]
            },
            "meta": {"page": {"next_cursor": "api-next"}},
        }


def _override(fake: Any) -> None:
    app.dependency_overrides[get_kor_travel_map_admin_client] = lambda: fake


def _clear() -> None:
    app.dependency_overrides.pop(get_kor_travel_map_admin_client, None)


async def test_admin_dedup_review_proxies_filters(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-dedup@example.com", roles=["user", "operator"]
    )
    fake = _FakeOpsClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/dedup-review",
            params=[
                ("status", "pending"),
                ("provider", "kma"),
                ("dataset_key", "places"),
                ("min_score", "70"),
                ("q", "해운대"),
                ("page_size", "20"),
            ],
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["items"][0]["review_id"] == "dedup-1"
    assert data["next_cursor"] == "dedup-next"
    assert fake.dedup_kwargs is not None
    assert fake.dedup_kwargs["statuses"] == ["pending"]
    assert fake.dedup_kwargs["providers"] == ["kma"]
    assert fake.dedup_kwargs["dataset_keys"] == ["places"]
    assert fake.dedup_kwargs["min_score"] == 70
    assert fake.dedup_kwargs["q"] == "해운대"


async def test_admin_dedup_verdict_proxies_decision_and_writes_audit(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-dedup-verdict@example.com", roles=["user", "admin"]
    )
    request_id = uuid.uuid4()
    fake = _FakeOpsClient()
    _override(fake)
    try:
        resp = await client.post(
            "/admin/dedup-review/dedup-1/verdict",
            json={
                "decision": "merged",
                "master_feature_id": "f_a",
                "access_reason": "중복 후보 병합",
                "kor_travel_map_reason": "동일 장소 확인",
            },
            headers={"X-Request-Id": str(request_id)},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["decision"] == "merged"
    assert data["master_feature_id"] == "f_a"
    assert fake.decision_args is not None
    assert fake.decision_args[0] == "dedup-1"
    assert fake.decision_args[1] == {
        "decision": "merged",
        "decision_reason": "동일 장소 확인",
        "master_feature_id": "f_a",
        "reviewed_by": "pinvi-admin",
    }

    async with session_factory() as db:
        audit = await db.scalar(select(AdminAuditLog).where(AdminAuditLog.request_id == request_id))

    assert audit is not None
    assert audit.actor_user_id == admin_id
    assert audit.action == "dedup_review.decide"
    assert audit.resource_type == "dedup_review"
    assert audit.resource_id == "dedup-1"
    assert audit.access_reason == "중복 후보 병합"
    assert audit.after_state == {
        "decision": "merged",
        "changed": True,
        "master_feature_id": "f_a",
        "loser_feature_id": "f_b",
        "merge_id": "merge-1",
    }


async def test_admin_dedup_verdict_requires_master_for_merge(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-dedup-verdict-invalid@example.com", roles=["user", "admin"]
    )
    fake = _FakeOpsClient()
    _override(fake)
    try:
        resp = await client.post(
            "/admin/dedup-review/dedup-1/verdict",
            json={"decision": "merged", "access_reason": "중복 후보 병합"},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()
    assert resp.status_code == 422
    assert fake.decision_args is None


async def test_admin_integrity_routes_proxy_issues_and_reports(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-integrity@example.com", roles=["user", "admin"]
    )
    fake = _FakeOpsClient()
    _override(fake)
    try:
        issues = await client.get(
            "/admin/integrity/issues",
            params={"status": "open", "severity": "error", "provider": "kma"},
            cookies=auth_cookies(str(admin_id)),
        )
        reports = await client.get(
            "/admin/integrity/reports",
            params={"severity_max": "WARN"},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert issues.status_code == 200, issues.text
    assert reports.status_code == 200, reports.text
    assert issues.json()["data"]["items"][0]["issue_id"] == "iss-1"
    assert issues.json()["data"]["items"][0]["source"] == "kor_travel_map"
    assert reports.json()["data"]["items"][0]["report_id"] == "rep-1"
    assert fake.issue_kwargs is not None
    assert fake.issue_kwargs["status_filter"] == "open"
    assert fake.issue_kwargs["severity"] == "error"
    assert fake.issue_kwargs["provider"] == "kma"
    assert fake.report_kwargs == {"severity_max": "WARN", "page_size": 50, "cursor": None}


async def test_admin_integrity_pinvi_app_source_lists_known_violations(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-integrity-app@example.com", roles=["user", "admin"]
    )
    trip_id = uuid.uuid4()
    broken_poi_id = uuid.uuid4()
    invalid_marker_poi_id = uuid.uuid4()
    deleted_poi_id = uuid.uuid4()
    curated_plan_id = uuid.uuid4()
    curated_poi_id = uuid.uuid4()
    now = datetime.now(UTC)
    async with session_factory() as db:
        db.add(
            Trip(
                trip_id=trip_id,
                owner_user_id=admin_id,
                title="정합성 테스트 여행",
                status="planned",
            )
        )
        await db.flush()
        db.add(TripDay(trip_id=trip_id, day_index=1))
        await db.flush()
        db.add_all(
            [
                TripDayPoi(
                    attachment_id=broken_poi_id,
                    trip_id=trip_id,
                    day_index=1,
                    sort_order="a0",
                    feature_id="feature-broken",
                    feature_link_broken_at=now,
                    added_by_user_id=admin_id,
                ),
                TripDayPoi(
                    attachment_id=invalid_marker_poi_id,
                    trip_id=trip_id,
                    day_index=1,
                    sort_order="a1",
                    feature_id="feature-invalid-marker",
                    custom_marker_color="P-99",
                    added_by_user_id=admin_id,
                ),
                TripDayPoi(
                    attachment_id=deleted_poi_id,
                    trip_id=trip_id,
                    day_index=1,
                    sort_order="a2",
                    feature_id="feature-deleted",
                    deleted_at=now,
                    added_by_user_id=admin_id,
                ),
                CuratedTripPlan(
                    curated_plan_id=curated_plan_id,
                    slug=f"integrity-{uuid.uuid4().hex[:8]}",
                    title="정합성 테스트 큐레이션",
                    category="recommended",
                    source_system="kor-travel-map",
                    source_curated_feature_id="curated-feature-plan",
                    created_by_admin_id=admin_id,
                    updated_by_admin_id=admin_id,
                ),
                DataIntegrityViolation(
                    rule_key="manual_quota_orphan",
                    entity_kind="user_quota",
                    entity_id=str(admin_id),
                    severity="critical",
                    message="사용자 quota override 점검 필요",
                    details={"feature_id": "feature-persisted", "quota_scope": "trip"},
                    detected_at=now,
                ),
            ]
        )
        await db.flush()
        db.add_all(
            [
                CuratedPlanPoi(
                    curated_poi_id=curated_poi_id,
                    curated_plan_id=curated_plan_id,
                    day_index=1,
                    sort_order="a0",
                    feature_id="feature-curated",
                    source_curated_feature_id="curated-feature-other",
                    source_curated_feature_item_id="curated-item-1",
                ),
                CuratedPlanAttachment(
                    trip_poi_id=deleted_poi_id,
                    bucket="pinvi-test",
                    storage_key="integrity/deleted-poi.jpg",
                    original_filename="deleted-poi.jpg",
                    content_type="image/jpeg",
                    byte_size=1024,
                    uploaded_by_user_id=admin_id,
                ),
            ]
        )
        await db.commit()

    fake = _FakeOpsClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/integrity/issues",
            params={"source": "pinvi_app", "status": "open", "page_size": "20"},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    assert {item["source"] for item in items} == {"pinvi_app"}
    assert {item["violation_type"] for item in items} >= {
        "manual_quota_orphan",
        "broken_poi_feature_link",
        "invalid_trip_day_poi_marker_color",
        "curated_import_source_drift",
        "active_attachment_deleted_target",
    }
    assert any(item["feature_id"] == "feature-broken" for item in items)
    assert fake.issue_kwargs is None


async def test_admin_integrity_issue_action_proxies_and_writes_audit(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-integrity-action@example.com", roles=["user", "admin"]
    )
    request_id = uuid.uuid4()
    fake = _FakeOpsClient()
    _override(fake)
    try:
        resp = await client.post(
            "/admin/integrity/issues/iss-1/action",
            json={
                "action": "resolve",
                "access_reason": "운영자가 원천 데이터를 확인함",
                "kor_travel_map_reason": "source verified",
            },
            headers={"X-Request-Id": str(request_id)},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["action"] == "resolve"
    assert data["issue"]["issue_id"] == "iss-1"
    assert data["issue"]["status"] == "resolved"
    assert fake.issue_action_args == (
        "iss-1",
        {
            "action": "resolve",
            "reason": "source verified",
            "operator": "pinvi-admin",
        },
    )

    async with session_factory() as db:
        audit = await db.scalar(select(AdminAuditLog).where(AdminAuditLog.request_id == request_id))

    assert audit is not None
    assert audit.actor_user_id == admin_id
    assert audit.action == "integrity_issue.action"
    assert audit.resource_type == "integrity_issue"
    assert audit.resource_id == "iss-1"
    assert audit.access_reason == "운영자가 원천 데이터를 확인함"
    assert audit.after_state == {
        "action": "resolve",
        "status": "resolved",
        "feature_id": "f_a",
        "provider": "kma",
        "dataset_key": "places",
        "violation_type": "missing_coord",
    }


async def test_admin_integrity_pinvi_app_issue_action_is_read_only(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-integrity-action-app@example.com", roles=["user", "admin"]
    )
    fake = _FakeOpsClient()
    _override(fake)
    try:
        resp = await client.post(
            "/admin/integrity/issues/pinvi_app:broken_poi_feature_link:poi-1/action",
            json={"action": "resolve", "access_reason": "운영자가 앱 정합성 issue를 확인함"},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "PINVI_APP_INTEGRITY_ACTION_UNSUPPORTED"
    assert fake.issue_action_args is None


async def test_admin_debug_logs_routes_proxy_system_and_api_logs(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-debug@example.com", roles=["user", "operator"]
    )
    fake = _FakeOpsClient()
    _override(fake)
    try:
        system_logs = await client.get(
            "/admin/debug/logs/system",
            params={"level": "error", "source": "api", "q": "timeout", "request_id": "req-1"},
            cookies=auth_cookies(str(admin_id)),
        )
        api_logs = await client.get(
            "/admin/debug/logs/api-calls",
            params={
                "method": "GET",
                "min_status": "500",
                "path": "/v1/features",
                "request_id": "req-1",
            },
            cookies=auth_cookies(str(admin_id)),
        )
        live_status = await client.get(
            "/admin/debug/logs/stream/status",
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert system_logs.status_code == 200, system_logs.text
    assert api_logs.status_code == 200, api_logs.text
    assert live_status.status_code == 200, live_status.text
    assert live_status.json()["data"] == {
        "mode": "polling",
        "status": "ok",
        "poll_interval_ms": 5000,
        "sources": ["kor_travel_map_system_logs", "kor_travel_map_api_call_logs"],
        "loki_enabled": False,
        "sse_enabled": False,
        "message": "sanitized polling fallback",
    }
    assert system_logs.json()["data"]["items"][0]["log_id"] == "log-1"
    assert api_logs.json()["data"]["items"][0]["status_code"] == 503
    assert fake.system_log_kwargs is not None
    assert fake.system_log_kwargs["level"] == "error"
    assert fake.system_log_kwargs["source"] == "api"
    assert fake.system_log_kwargs["q"] == "timeout"
    assert fake.system_log_kwargs["request_id"] == "req-1"
    assert fake.api_log_kwargs is not None
    assert fake.api_log_kwargs["method"] == "GET"
    assert fake.api_log_kwargs["min_status"] == 500
    assert fake.api_log_kwargs["path"] == "/v1/features"
    assert fake.api_log_kwargs["request_id"] == "req-1"


async def test_admin_request_timeline_collects_sanitized_events(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-timeline@example.com", roles=["user", "operator"]
    )
    request_id = uuid.uuid4()
    occurred_at = datetime(2026, 6, 12, 0, 0, tzinfo=UTC)
    async with session_factory() as db:
        db.add_all(
            [
                ApiCallLog(
                    provider="kor_travel_map",
                    endpoint="https://internal.example.test/v1/features?token=secret&safe=ok",
                    status_code=503,
                    latency_ms=321,
                    error_class="UPSTREAM_TIMEOUT",
                    error_message="token=secret leaked text",
                    request_id=request_id,
                    occurred_at=occurred_at,
                ),
                AdminAuditLog(
                    actor_user_id=admin_id,
                    action="backup.snapshot",
                    resource_type="backup_snapshot",
                    resource_id="snap-1",
                    before_state={"token": "secret"},
                    after_state={"status": "created"},
                    access_reason="operator secret note",
                    target_pii_fields=["email"],
                    ip_hash="hash",
                    user_agent="agent",
                    request_id=request_id,
                    prev_hash="a" * 64,
                    content_hash="b" * 64,
                    occurred_at=occurred_at + timedelta(milliseconds=10),
                ),
                LocationAccessLog(
                    user_id=admin_id,
                    endpoint="/nearby?api_key=secret",
                    purpose="nearby_attractions",
                    lat=None,
                    lng=None,
                    request_id=request_id,
                    ip_hash="raw-ip-hash",
                    prev_hash="c" * 64,
                    content_hash="d" * 64,
                    occurred_at=occurred_at + timedelta(milliseconds=20),
                ),
                EmailQueue(
                    user_id=admin_id,
                    to_email="private@example.com",
                    template="verify_email",
                    subject="secret subject",
                    payload={"request_id": str(request_id), "token": "secret"},
                    status="pending",
                    attempts=1,
                    last_error="smtp secret",
                    scheduled_at=occurred_at + timedelta(minutes=1),
                    created_at=occurred_at + timedelta(milliseconds=30),
                ),
            ]
        )
        await db.commit()

    fake = _FakeOpsClient()
    _override(fake)
    try:
        resp = await client.get(
            f"/admin/debug/request/{request_id}",
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["request_id"] == str(request_id)
    assert data["status"] == "ok"
    assert len(data["events"]) == 6
    assert fake.system_log_kwargs is not None
    assert fake.system_log_kwargs["request_id"] == str(request_id)
    assert fake.api_log_kwargs is not None
    assert fake.api_log_kwargs["request_id"] == str(request_id)

    event_sources = {item["source"] for item in data["events"]}
    assert "pinvi_api_call_log" in event_sources
    assert "pinvi_admin_audit_log" in event_sources
    assert "pinvi_location_audit" in event_sources
    assert "pinvi_email_queue" in event_sources
    assert "kor_travel_map_system_logs" in event_sources
    assert "kor_travel_map_api_call_logs" in event_sources

    body = json.dumps(data, ensure_ascii=False)
    assert "private@example.com" not in body
    assert "secret subject" not in body
    assert "smtp secret" not in body
    assert "token=secret" not in body
    api_event = next(item for item in data["events"] if item["source"] == "pinvi_api_call_log")
    assert api_event["detail"]["endpoint"] == "/v1/features?token=%5Bmasked%5D&safe=ok"


class _FailingSystemLogClient(_FakeOpsClient):
    async def list_system_logs(self, **kwargs: Any) -> dict[str, Any]:
        self.system_log_kwargs = kwargs
        raise KorTravelMapUnavailable("down")


async def test_admin_request_timeline_returns_partial_on_upstream_failure(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-timeline-partial@example.com", roles=["user", "operator"]
    )
    request_id = uuid.uuid4()
    async with session_factory() as db:
        db.add(
            ApiCallLog(
                provider="resend",
                endpoint="https://api.resend.test/emails",
                status_code=200,
                latency_ms=42,
                request_id=request_id,
                occurred_at=datetime(2026, 6, 12, 0, 0, tzinfo=UTC),
            )
        )
        await db.commit()

    fake = _FailingSystemLogClient()
    _override(fake)
    try:
        resp = await client.get(
            f"/admin/debug/request/{request_id}",
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "partial"
    degraded = [item for item in data["sources"] if item["status"] == "degraded"]
    assert degraded
    assert degraded[0]["source"] == "kor_travel_map_system_logs"


class _EmptyOpsClient(_FakeOpsClient):
    async def list_system_logs(self, **kwargs: Any) -> dict[str, Any]:
        self.system_log_kwargs = kwargs
        return {"data": {"items": []}, "meta": {"page": {"next_cursor": None}}}

    async def list_ops_api_call_logs(self, **kwargs: Any) -> dict[str, Any]:
        self.api_log_kwargs = kwargs
        return {"data": {"items": []}, "meta": {"page": {"next_cursor": None}}}


async def test_admin_request_timeline_not_found_and_invalid_id(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-timeline-missing@example.com", roles=["user", "operator"]
    )
    fake = _EmptyOpsClient()
    _override(fake)
    try:
        missing = await client.get(
            f"/admin/debug/request/{uuid.uuid4()}",
            cookies=auth_cookies(str(admin_id)),
        )
        invalid = await client.get(
            "/admin/debug/request/not-a-uuid",
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert invalid.status_code == 422


async def test_non_admin_dedup_route_is_hidden(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    user_id = await _create_user(session_factory, email="plain-dedup@example.com")
    resp = await client.get("/admin/dedup-review", cookies=auth_cookies(str(user_id)))
    assert resp.status_code == 404
