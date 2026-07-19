"""Admin feature read proxy 통합 테스트 (T-209)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from app.clients.kor_travel_map import (
    KorTravelMapConflict,
    KorTravelMapFeatureNotFound,
    KorTravelMapPreconditionFailed,
    KorTravelMapUnavailable,
    get_kor_travel_map_client,
)
from app.clients.kor_travel_map_admin import get_kor_travel_map_admin_client
from app.main import app
from app.models.audit import AdminAuditLog
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


def _feature_record() -> dict[str, Any]:
    return {
        "feature_id": "f_place_1",
        "kind": "place",
        "name": "해운대 카페",
        "category": "01070100",
        "status": "active",
        "lon": 129.163,
        "lat": 35.158,
        "address_label": "부산 해운대구",
        "primary_provider": "visitkorea",
        "primary_dataset_key": "places",
        "issue_count": 1,
        "issues": [
            {
                "issue_id": "iss-1",
                "violation_type": "missing_source",
                "severity": "warning",
                "message": "source 보강 필요",
                "detected_at": "2026-06-12T00:00:00+09:00",
            }
        ],
        "created_at": "2026-06-11T00:00:00+09:00",
        "updated_at": "2026-06-12T00:00:00+09:00",
    }


def _detail() -> dict[str, Any]:
    return {
        "feature": {
            "feature_id": "f_place_1",
            "kind": "place",
            "name": "해운대 카페",
            "category": "01070100",
            "status": "active",
            "lon": 129.163,
            "lat": 35.158,
            "address": {"road": "해운대해변로"},
            "detail": {"phone": "051-000-0000"},
            "urls": {"homepage": "https://example.com/place"},
            "raw_refs": [{"provider": "visitkorea"}],
            "sido_code": "26",
            "sigungu_code": "26350",
            "marker_icon": "cafe",
            "marker_color": "P-07",
            "data_origin": "provider",
            "data_version": 3,
            "created_at": "2026-06-11T00:00:00+09:00",
            "updated_at": "2026-06-12T00:00:00+09:00",
        },
        "sources": [
            {
                "source_record_key": "visitkorea:places:1",
                "provider": "visitkorea",
                "dataset_key": "places",
                "source_entity_type": "content",
                "source_entity_id": "1",
                "source_role": "primary",
                "match_method": "natural_key",
                "confidence": 100,
                "is_primary_source": True,
                "raw_payload_hash": "sha256:abc",
                "raw_data": {"name": "해운대 카페"},
                "fetched_at": "2026-06-11T00:00:00+09:00",
                "imported_at": "2026-06-11T00:01:00+09:00",
                "linked_at": "2026-06-11T00:02:00+09:00",
            }
        ],
        "issues": [],
        "overrides": [
            {
                "override_id": "ovr-1",
                "source_record_key": "visitkorea:places:1",
                "field_path": "detail.phone",
                "source_value": "051-111-1111",
                "override_value": "051-000-0000",
                "prevent_provider_reactivation": True,
                "status": "active",
                "reason": "운영 검수",
                "created_by": "pinvi-admin",
                "created_at": "2026-06-12T00:10:00+09:00",
            }
        ],
        "versions": [
            {
                "feature_id": "f_place_1",
                "version": 3,
                "origin": "provider",
                "change_kind": "upsert",
                "payload": {"name": "해운대 카페"},
                "created_at": "2026-06-12T00:00:00+09:00",
            }
        ],
        "change_requests": [],
        "files": [],
    }


class _FakeAdminClient:
    def __init__(
        self,
        *,
        not_found: bool = False,
        approve_conflict: bool = False,
        approve_precondition: bool = False,
    ) -> None:
        self.list_kwargs: dict[str, Any] | None = None
        self.detail_id: str | None = None
        self.change_request_kwargs: dict[str, Any] | None = None
        self.approved: dict[str, str | None] | None = None
        self.rejected: dict[str, str | None] | None = None
        self.not_found = not_found
        self.approve_conflict = approve_conflict
        self.approve_precondition = approve_precondition

    async def list_features(self, **kwargs: Any) -> dict[str, Any]:
        self.list_kwargs = kwargs
        return {
            "data": {"items": [_feature_record()]},
            "meta": {"page": {"next_cursor": "cursor-2"}, "duration_ms": 7},
        }

    async def get_feature_detail(self, feature_id: str) -> dict[str, Any]:
        self.detail_id = feature_id
        if self.not_found:
            raise KorTravelMapFeatureNotFound("not found")
        return _detail()

    async def list_change_requests(self, **kwargs: Any) -> dict[str, Any]:
        self.change_request_kwargs = kwargs
        return {
            "items": [
                {
                    "request_id": "krq-1",
                    "feature_id": "f_place_1",
                    "action": "add",
                    "status": "pending",
                    "review_mode": "require_review",
                    "payload": {"name": "해운대 카페"},
                    "reason": "사용자 제안",
                    "requested_by": "pinvi-admin",
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "applied_at": None,
                    "created_at": "2026-06-12T00:00:00+09:00",
                }
            ],
            "review_mode": "require_review",
        }

    async def approve_change_request(
        self, request_id: str, *, operator: str | None = None, reason: str | None = None
    ) -> dict[str, Any]:
        if self.approve_conflict:
            raise KorTravelMapConflict("already reviewed", code="INVALID_STATE")
        if self.approve_precondition:
            raise KorTravelMapPreconditionFailed(
                "stale feature",
                code="PRECONDITION_FAILED",
            )
        self.approved = {"request_id": request_id, "operator": operator, "reason": reason}
        return {
            "request_id": request_id,
            "feature_id": "f_place_1",
            "action": "add",
            "status": "applied",
            "review_mode": "require_review",
            "payload": {"name": "해운대 카페"},
            "reason": reason,
            "requested_by": "pinvi-admin",
            "reviewed_by": operator,
            "reviewed_at": "2026-06-12T01:00:00+09:00",
            "applied_at": "2026-06-12T01:00:01+09:00",
            "created_at": "2026-06-12T00:00:00+09:00",
        }

    async def reject_change_request(
        self, request_id: str, *, operator: str | None = None, reason: str | None = None
    ) -> dict[str, Any]:
        self.rejected = {"request_id": request_id, "operator": operator, "reason": reason}
        return {
            "request_id": request_id,
            "feature_id": "f_place_1",
            "action": "update",
            "status": "rejected",
            "review_mode": "require_review",
            "payload": {"name": "해운대 카페"},
            "reason": reason,
            "requested_by": "pinvi-admin",
            "reviewed_by": operator,
            "reviewed_at": "2026-06-12T01:00:00+09:00",
            "applied_at": None,
            "created_at": "2026-06-12T00:00:00+09:00",
        }


class _FakeWeatherClient:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.calls: dict[str, Any] = {}
        self.unavailable = unavailable

    async def feature_weather(self, feature_id: str, *, asof: Any = None) -> dict[str, Any]:
        self.calls["feature_weather"] = {"feature_id": feature_id, "asof": asof}
        if self.unavailable:
            raise KorTravelMapUnavailable("kor-travel-map weather down")
        return {
            "feature_id": feature_id,
            "asof": "2026-06-12T10:00:00+09:00",
            "latest_at": "2026-06-12T09:30:00+09:00",
            "is_stale": False,
            "source_styles": ["nowcast", "short"],
            "metrics": [
                {
                    "metric_key": "T1H",
                    "metric_name": "기온",
                    "forecast_style": "nowcast",
                    "timeline_bucket": "current",
                    "valid_at": "2026-06-12T10:00:00+09:00",
                    "value_number": 24.5,
                    "unit": "℃",
                }
            ],
        }


def _override(fake: Any) -> None:
    app.dependency_overrides[get_kor_travel_map_admin_client] = lambda: fake


def _override_weather(fake: Any) -> None:
    app.dependency_overrides[get_kor_travel_map_client] = lambda: fake


def _clear() -> None:
    app.dependency_overrides.pop(get_kor_travel_map_admin_client, None)
    app.dependency_overrides.pop(get_kor_travel_map_client, None)


async def test_list_admin_features_proxies_filters(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "operator"]
    )
    fake = _FakeAdminClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/features",
            params=[
                ("q", "해운대"),
                ("kind", "place"),
                ("kind", "event"),
                ("status", "active"),
                ("provider", "visitkorea"),
                ("category", "01070100"),
                ("has_issue", "true"),
                ("page_size", "100"),
                ("cursor", "cursor-1"),
                ("sort", "updated_at"),
                ("order", "desc"),
            ],
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["items"][0]["feature_id"] == "f_place_1"
    assert data["items"][0]["issues"][0]["violation_type"] == "missing_source"
    assert data["next_cursor"] == "cursor-2"
    assert data["duration_ms"] == 7
    assert fake.list_kwargs is not None
    assert fake.list_kwargs["q"] == "해운대"
    assert fake.list_kwargs["kinds"] == ["place", "event"]
    assert fake.list_kwargs["statuses"] == ["active"]
    assert fake.list_kwargs["providers"] == ["visitkorea"]
    assert fake.list_kwargs["categories"] == ["01070100"]
    assert fake.list_kwargs["has_issue"] is True
    assert fake.list_kwargs["page_size"] == 100
    assert fake.list_kwargs["cursor"] == "cursor-1"
    assert fake.list_kwargs["sort"] == "updated_at"
    assert fake.list_kwargs["order"] == "desc"


async def test_get_admin_feature_returns_detail(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    fake = _FakeAdminClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/features/f_place_1",
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert fake.detail_id == "f_place_1"
    assert data["feature"]["name"] == "해운대 카페"
    assert data["sources"][0]["provider"] == "visitkorea"
    assert data["versions"][0]["version"] == 3


async def test_get_admin_feature_sources_and_overrides_return_projections(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "operator"]
    )
    fake = _FakeAdminClient()
    _override(fake)
    try:
        sources_resp = await client.get(
            "/admin/features/f_place_1/sources",
            cookies=auth_cookies(str(admin_id)),
        )
        overrides_resp = await client.get(
            "/admin/features/f_place_1/overrides",
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert sources_resp.status_code == 200, sources_resp.text
    assert overrides_resp.status_code == 200, overrides_resp.text
    sources = sources_resp.json()["data"]
    overrides = overrides_resp.json()["data"]
    assert sources["feature_id"] == "f_place_1"
    assert sources["items"][0]["source_record_key"] == "visitkorea:places:1"
    assert overrides["feature_id"] == "f_place_1"
    assert overrides["items"][0]["field_path"] == "detail.phone"
    assert overrides["items"][0]["prevent_provider_reactivation"] is True


async def test_get_admin_feature_weather_values_proxies_weather_card(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    fake = _FakeWeatherClient()
    _override_weather(fake)
    try:
        resp = await client.get(
            "/admin/features/f_weather_1/weather-values",
            params={"asof": "2026-06-12T10:00:00+09:00"},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert fake.calls["feature_weather"]["feature_id"] == "f_weather_1"
    assert fake.calls["feature_weather"]["asof"] == datetime.fromisoformat(
        "2026-06-12T10:00:00+09:00"
    )
    assert data["feature_id"] == "f_weather_1"
    assert data["source_styles"] == ["nowcast", "short"]
    assert data["items"][0]["metric_key"] == "T1H"


async def test_get_admin_feature_weather_values_maps_upstream_unavailable(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "operator"]
    )
    fake = _FakeWeatherClient(unavailable=True)
    _override_weather(fake)
    try:
        resp = await client.get(
            "/admin/features/f_weather_1/weather-values",
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "FEATURE_SERVICE_UNAVAILABLE"


async def test_get_admin_feature_maps_upstream_404(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    fake = _FakeAdminClient(not_found=True)
    _override(fake)
    try:
        resp = await client.get(
            "/admin/features/missing",
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


async def test_list_admin_feature_change_requests_proxies_filters(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "operator"]
    )
    fake = _FakeAdminClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/features/change-requests",
            params=[
                ("status", "pending"),
                ("status", "applied"),
                ("action", "add"),
                ("q", "해운대"),
                ("page_size", "10"),
            ],
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["items"][0]["request_id"] == "krq-1"
    assert data["items"][0]["payload"] == {"name": "해운대 카페"}
    assert data["review_mode"] == "require_review"
    assert data["page_size"] == 10
    assert fake.change_request_kwargs == {
        "statuses": ["pending", "applied"],
        "actions": ["add"],
        "q": "해운대",
        "page_size": 10,
    }


async def test_approve_admin_feature_change_request_appends_audit(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    fake = _FakeAdminClient()
    _override(fake)
    try:
        resp = await client.post(
            "/admin/features/change-requests/krq-1/approve",
            json={
                "access_reason": "Pinvi 운영 검수 완료",
                "kor_travel_map_reason": "원천 검수 완료",
            },
            headers={"X-Request-Id": str(uuid.uuid4())},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "applied"
    assert fake.approved == {
        "request_id": "krq-1",
        "operator": "pinvi-admin",
        "reason": "원천 검수 완료",
    }
    async with session_factory() as db:
        audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.action == "feature_change_request.approve")
        )
    assert audit is not None
    assert audit.resource_id == "krq-1"
    assert audit.access_reason == "Pinvi 운영 검수 완료"


async def test_reject_admin_feature_change_request_appends_audit(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    fake = _FakeAdminClient()
    _override(fake)
    try:
        resp = await client.post(
            "/admin/features/change-requests/krq-2/reject",
            json={"access_reason": "중복 변경 요청"},
            headers={"X-Request-Id": str(uuid.uuid4())},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "rejected"
    assert fake.rejected == {
        "request_id": "krq-2",
        "operator": "pinvi-admin",
        "reason": "중복 변경 요청",
    }
    async with session_factory() as db:
        audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.action == "feature_change_request.reject")
        )
    assert audit is not None
    assert audit.resource_id == "krq-2"


async def test_change_request_conflict_maps_409_without_audit(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin@example.com", roles=["user", "admin"]
    )
    fake = _FakeAdminClient(approve_conflict=True)
    _override(fake)
    try:
        resp = await client.post(
            "/admin/features/change-requests/krq-1/approve",
            json={"access_reason": "재승인 시도"},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_STATE"
    async with session_factory() as db:
        audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.action == "feature_change_request.approve")
        )
    assert audit is None


async def test_change_request_stale_revision_maps_412_without_audit(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-stale@example.com", roles=["user", "admin"]
    )
    fake = _FakeAdminClient(approve_precondition=True)
    _override(fake)
    try:
        resp = await client.post(
            "/admin/features/change-requests/krq-stale/approve",
            json={"access_reason": "stale 승인 시도"},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 412
    assert resp.json()["error"]["code"] == "PRECONDITION_FAILED"
    async with session_factory() as db:
        audit = await db.scalar(
            select(AdminAuditLog).where(AdminAuditLog.action == "feature_change_request.approve")
        )
    assert audit is None


async def test_non_admin_features_route_is_hidden(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    user_id = await _create_user(session_factory, email="plain@example.com")
    resp = await client.get("/admin/features", cookies=auth_cookies(str(user_id)))
    assert resp.status_code == 404
