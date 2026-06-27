"""Admin dedup/integrity/debug ops proxy 통합 테스트 (T-212)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

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

    async def list_dedup_reviews(self, **kwargs: Any) -> dict[str, Any]:
        self.dedup_kwargs = kwargs
        return {
            "data": {"items": [_dedup_item()]},
            "meta": {"page": {"next_cursor": "dedup-next"}},
        }

    async def list_integrity_issues(self, **kwargs: Any) -> dict[str, Any]:
        self.issue_kwargs = kwargs
        return {
            "data": {"items": [_issue_item()]},
            "meta": {"page": {"next_cursor": "issue-next"}},
        }

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
                        "request_id": "req-1",
                        "created_at": "2026-06-12T00:00:00+09:00",
                    }
                ]
            },
            "meta": {"page": {"next_cursor": "log-next"}},
        }

    async def list_ops_api_call_logs(self, **kwargs: Any) -> dict[str, Any]:
        self.api_log_kwargs = kwargs
        return {
            "data": {
                "items": [
                    {
                        "log_id": "api-1",
                        "method": "GET",
                        "path": "/v1/features",
                        "status_code": 503,
                        "duration_ms": 1200,
                        "request_id": "req-1",
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
    assert reports.json()["data"]["items"][0]["report_id"] == "rep-1"
    assert fake.issue_kwargs is not None
    assert fake.issue_kwargs["status_filter"] == "open"
    assert fake.issue_kwargs["severity"] == "error"
    assert fake.issue_kwargs["provider"] == "kma"
    assert fake.report_kwargs == {"severity_max": "WARN", "page_size": 50, "cursor": None}


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
            params={"level": "error", "source": "api", "q": "timeout"},
            cookies=auth_cookies(str(admin_id)),
        )
        api_logs = await client.get(
            "/admin/debug/logs/api-calls",
            params={"method": "GET", "min_status": "500", "path": "/v1/features"},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert system_logs.status_code == 200, system_logs.text
    assert api_logs.status_code == 200, api_logs.text
    assert system_logs.json()["data"]["items"][0]["log_id"] == "log-1"
    assert api_logs.json()["data"]["items"][0]["status_code"] == 503
    assert fake.system_log_kwargs is not None
    assert fake.system_log_kwargs["level"] == "error"
    assert fake.system_log_kwargs["source"] == "api"
    assert fake.system_log_kwargs["q"] == "timeout"
    assert fake.api_log_kwargs is not None
    assert fake.api_log_kwargs["method"] == "GET"
    assert fake.api_log_kwargs["min_status"] == 500
    assert fake.api_log_kwargs["path"] == "/v1/features"


async def test_non_admin_dedup_route_is_hidden(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    user_id = await _create_user(session_factory, email="plain-dedup@example.com")
    resp = await client.get("/admin/dedup-review", cookies=auth_cookies(str(user_id)))
    assert resp.status_code == 404
