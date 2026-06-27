"""Admin feature read proxy 통합 테스트 (T-209)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.clients.kor_travel_map import KorTravelMapFeatureNotFound
from app.clients.kor_travel_map_admin import get_kor_travel_map_admin_client
from app.main import app
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
        "overrides": [],
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
    def __init__(self, *, not_found: bool = False) -> None:
        self.list_kwargs: dict[str, Any] | None = None
        self.detail_id: str | None = None
        self.not_found = not_found

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


def _override(fake: Any) -> None:
    app.dependency_overrides[get_kor_travel_map_admin_client] = lambda: fake


def _clear() -> None:
    app.dependency_overrides.pop(get_kor_travel_map_admin_client, None)


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


async def test_non_admin_features_route_is_hidden(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    user_id = await _create_user(session_factory, email="plain@example.com")
    resp = await client.get("/admin/features", cookies=auth_cookies(str(user_id)))
    assert resp.status_code == 404
