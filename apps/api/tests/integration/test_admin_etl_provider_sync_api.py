"""Admin ETL/provider sync API 통합 테스트 (T-220)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.api.v1.admin import etl as etl_router
from app.clients.kor_travel_map import KorTravelMapUnavailable
from app.clients.kor_travel_map_admin import get_kor_travel_map_admin_client
from app.main import app
from app.models.email_queue import EmailQueue
from app.models.user import User
from app.services import admin_etl as admin_etl_service

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


async def _seed_email_queue(session_factory: Any) -> None:
    now = datetime.now(UTC)
    async with session_factory() as db:
        db.add_all(
            [
                EmailQueue(
                    to_email="due@example.com",
                    template="verify_email",
                    subject="Verify",
                    payload={},
                    status="pending",
                    attempts=0,
                    scheduled_at=now - timedelta(minutes=20),
                ),
                EmailQueue(
                    to_email="backoff@example.com",
                    template="verify_email",
                    subject="Verify retry",
                    payload={},
                    status="pending",
                    attempts=1,
                    scheduled_at=now + timedelta(minutes=5),
                ),
                EmailQueue(
                    to_email="failed@example.com",
                    template="verify_email",
                    subject="Verify failed",
                    payload={},
                    status="failed",
                    attempts=5,
                    last_error="provider down",
                    scheduled_at=now - timedelta(hours=1),
                ),
                EmailQueue(
                    to_email="invite@example.com",
                    template="trip_invite",
                    subject="Invite",
                    payload={},
                    status="bounced",
                    attempts=1,
                    bounce_type="hard",
                    scheduled_at=now - timedelta(hours=1),
                ),
            ]
        )
        await db.commit()


def _provider_item() -> dict[str, Any]:
    return {
        "provider": "kma",
        "dataset_key": "special_days",
        "sync_scope": "daily",
        "status": "healthy",
        "last_success_at": "2026-06-12T00:00:00+09:00",
        "last_failure_at": None,
        "consecutive_failures": 0,
        "next_run_after": "2026-06-13T03:30:00+09:00",
        "links": {"dagster": "/runs/kma"},
        "refresh_policy": {"enabled": True},
    }


def _import_job() -> dict[str, Any]:
    return {
        "job_id": "11111111-1111-4111-8111-111111111111",
        "kind": "provider_import",
        "payload": {"provider": "kma"},
        "status": "running",
        "progress": 0.5,
        "current_stage": "normalize",
        "error_message": None,
        "created_at": "2026-06-12T00:00:00+09:00",
        "started_at": "2026-06-12T00:01:00+09:00",
        "heartbeat_at": "2026-06-12T00:02:00+09:00",
        "finished_at": None,
        "load_batch_id": None,
        "parent_job_id": None,
        "source_checksum": None,
        "links": {},
        "status_url": "/v1/ops/import-jobs/11111111-1111-4111-8111-111111111111",
    }


class _FakeOpsClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.provider_key: str | None = None
        self.import_kwargs: dict[str, Any] | None = None

    async def get_ops_dagster_summary(self, *, page_size: int = 10) -> dict[str, Any]:
        if self.fail:
            raise KorTravelMapUnavailable("ops down")
        assert page_size == 10
        return {
            "status": "ok",
            "checked_at": "2026-06-12T00:00:00+09:00",
            "repository_count": 1,
            "job_count": 3,
            "asset_count": 8,
            "schedule_count": 2,
            "sensor_count": 0,
            "run_counts": {"STARTED": 1, "SUCCESS": 9},
            "repositories": [
                {
                    "name": "kor_travel_map",
                    "location_name": "etl",
                    "jobs": [{"name": "kma_special_days_job", "is_job": True}],
                    "schedules": [
                        {
                            "name": "kma_special_days_schedule",
                            "cron_schedule": "0 4 * * *",
                            "execution_timezone": "Asia/Seoul",
                            "status": "RUNNING",
                        }
                    ],
                    "sensors": [],
                    "asset_count": 8,
                    "asset_groups": ["kma"],
                }
            ],
            "recent_runs": [
                {
                    "run_id": "run-1",
                    "job_name": "kma_special_days_job",
                    "status": "STARTED",
                    "tags": {},
                    "start_time": 1781190000.0,
                    "end_time": None,
                    "update_time": 1781190010.0,
                }
            ],
        }

    async def get_ops_metrics(self) -> dict[str, Any]:
        if self.fail:
            raise KorTravelMapUnavailable("metrics down")
        return {
            "checked_at": "2026-06-12T00:00:00+09:00",
            "features_total": 42,
            "source_records_total": 77,
            "import_jobs_by_status": {"running": 1},
            "dedup_queue_by_status": {"pending": 2},
        }

    async def list_ops_providers(self, *, key: str | None = None) -> dict[str, Any]:
        if self.fail:
            raise KorTravelMapUnavailable("providers down")
        self.provider_key = key
        return {"items": [_provider_item()]}

    async def list_ops_import_jobs(self, **kwargs: Any) -> dict[str, Any]:
        if self.fail:
            raise KorTravelMapUnavailable("jobs down")
        self.import_kwargs = kwargs
        return {
            "data": {"items": [_import_job()]},
            "meta": {"page": {"next_cursor": "cursor-2"}},
        }


def _override(fake: Any) -> None:
    app.dependency_overrides[get_kor_travel_map_admin_client] = lambda: fake


def _clear() -> None:
    app.dependency_overrides.pop(get_kor_travel_map_admin_client, None)


async def test_admin_etl_summary_combines_pinvi_registry_and_upstream_ops(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_probe() -> tuple[str, str, int | None]:
        return "ok", "Dagster 응답 정상", 11

    monkeypatch.setattr(admin_etl_service, "_probe_pinvi_dagster", fake_probe)
    monkeypatch.setattr(
        etl_router, "build_admin_etl_summary", admin_etl_service.build_admin_etl_summary
    )
    admin_id = await _create_user(
        session_factory, email="admin-etl@example.com", roles=["user", "operator"]
    )
    await _seed_email_queue(session_factory)
    fake = _FakeOpsClient()
    _override(fake)
    try:
        resp = await client.get("/admin/etl/summary", cookies=auth_cookies(str(admin_id)))
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    assert "localhost" not in resp.text
    data = resp.json()["data"]
    assert data["pinvi"]["status"] == "ok"
    assert {job["name"] for job in data["pinvi"]["jobs"]} == {
        "kasi_special_days_job",
        "kasi_poi_rise_set_job",
        "pinvi_email_outbox_job",
    }
    assert data["pinvi"]["email_outbox"]["pending_due"] == 1
    assert data["pinvi"]["email_outbox"]["pending_backoff"] == 1
    assert data["pinvi"]["email_outbox"]["stuck_pending"] == 1
    assert data["pinvi"]["email_outbox"]["retry_exhausted"] == 1
    verify_stats = next(
        item
        for item in data["pinvi"]["email_outbox"]["template_stats"]
        if item["template"] == "verify_email"
    )
    assert verify_stats["total"] == 3
    assert verify_stats["failure_count"] == 1
    assert verify_stats["failure_rate"] == pytest.approx(1 / 3, abs=0.0001)
    assert data["kor_travel_map"]["dagster_status"] == "ok"
    assert data["kor_travel_map"]["job_count"] == 3
    assert data["kor_travel_map"]["features_total"] == 42
    assert data["kor_travel_map"]["provider_dataset_count"] == 1
    assert data["kor_travel_map"]["recent_import_jobs"][0]["status"] == "running"


async def test_admin_etl_summary_degrades_when_upstream_ops_is_unavailable(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_probe() -> tuple[str, str, int | None]:
        return "ok", "Dagster 응답 정상", 11

    monkeypatch.setattr(admin_etl_service, "_probe_pinvi_dagster", fake_probe)
    monkeypatch.setattr(
        etl_router, "build_admin_etl_summary", admin_etl_service.build_admin_etl_summary
    )
    admin_id = await _create_user(
        session_factory, email="admin-etl-down@example.com", roles=["user", "admin"]
    )
    fake = _FakeOpsClient(fail=True)
    _override(fake)
    try:
        resp = await client.get("/admin/etl/summary", cookies=auth_cookies(str(admin_id)))
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["pinvi"]["status"] == "ok"
    assert data["kor_travel_map"]["status"] == "down"
    assert data["kor_travel_map"]["dagster_status"] == "unavailable"
    assert len(data["kor_travel_map"]["errors"]) >= 1


async def test_admin_provider_sync_proxies_key_filter(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-provider@example.com", roles=["user", "operator"]
    )
    fake = _FakeOpsClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/provider-sync",
            params={"key": "kma"},
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert fake.provider_key == "kma"
    assert data["total"] == 1
    assert data["items"][0]["provider"] == "kma"
    assert data["items"][0]["dataset_key"] == "special_days"


async def test_admin_provider_import_jobs_proxies_filters_and_cursor(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    admin_id = await _create_user(
        session_factory, email="admin-provider-jobs@example.com", roles=["user", "operator"]
    )
    fake = _FakeOpsClient()
    _override(fake)
    try:
        resp = await client.get(
            "/admin/provider-sync/import-jobs",
            params={
                "status": "running",
                "kind": "provider_import",
                "page_size": "25",
                "cursor": "cursor-1",
            },
            cookies=auth_cookies(str(admin_id)),
        )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert fake.import_kwargs == {
        "status_filter": "running",
        "kind": "provider_import",
        "load_batch_id": None,
        "parent_job_id": None,
        "page_size": 25,
        "cursor": "cursor-1",
    }
    assert data["items"][0]["job_id"] == "11111111-1111-4111-8111-111111111111"
    assert data["next_cursor"] == "cursor-2"


async def test_non_admin_provider_sync_route_is_hidden(
    client: Any,
    session_factory: Any,
    auth_cookies: Any,
) -> None:
    user_id = await _create_user(session_factory, email="plain-provider@example.com")
    resp = await client.get("/admin/provider-sync", cookies=auth_cookies(str(user_id)))
    assert resp.status_code == 404
