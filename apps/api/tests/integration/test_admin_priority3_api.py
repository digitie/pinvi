"""Admin priority-3 조회 API 통합 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.api_call_log import ApiCallLog
from app.models.attachment import CuratedPlanAttachment
from app.models.email_queue import EmailQueue
from app.models.poi import TripDayPoi
from app.models.storage_settings import StorageSettings
from app.models.trip import Trip
from app.models.trip_day import TripDay
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _create_admin_user(
    session_factory,  # type: ignore[no-untyped-def]
    *,
    roles: list[str],
    email_prefix: str,
) -> uuid.UUID:
    async with session_factory() as db:
        user = User(
            email=f"{email_prefix}_{uuid.uuid4().hex[:8]}@pinvi.test",
            password_hash="x",
            nickname="관리자",
            status="active",
            roles=roles,
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def test_cpo_lists_location_audit_with_masked_coords(
    client,
    session_factory,
    auth_cookies,
) -> None:
    from app.middleware.location_audit import _append_log

    cpo_id = await _create_admin_user(
        session_factory,
        roles=["user", "cpo"],
        email_prefix="cpo_location",
    )
    admin_id = await _create_admin_user(
        session_factory,
        roles=["user", "admin"],
        email_prefix="admin_location",
    )
    request_id = uuid.uuid4()
    async with session_factory() as db:
        await _append_log(
            db,
            user_id=admin_id,
            endpoint="/features/in-bounds",
            purpose="viewport_query",
            lat=Decimal("37.566567"),
            lng=Decimal("126.978123"),
            request_id=request_id,
            ip_hash="a" * 64,
        )

    denied = await client.get(
        "/admin/audit/location",
        cookies=auth_cookies(str(admin_id)),
    )
    assert denied.status_code == 404

    resp = await client.get(
        f"/admin/audit/location?user_id={admin_id}&limit=10",
        cookies=auth_cookies(str(cpo_id)),
    )

    assert resp.status_code == 200, resp.text
    assert resp.headers.get("X-Chain-Broken") is None
    rows = resp.json()["data"]
    assert len(rows) == 1
    assert rows[0]["request_id"] == str(request_id)
    assert rows[0]["lat_masked"] == "37.5666"
    assert rows[0]["lng_masked"] == "126.9781"
    assert "37.566567" not in resp.text
    assert "126.978123" not in resp.text


async def test_admin_lists_api_call_log_with_filters(
    client,
    session_factory,
    auth_cookies,
) -> None:
    admin_id = await _create_admin_user(
        session_factory,
        roles=["user", "admin"],
        email_prefix="admin_api_calls",
    )
    request_id = uuid.uuid4()
    async with session_factory() as db:
        db.add_all(
            [
                ApiCallLog(
                    provider="kma",
                    endpoint="/weather/current",
                    status_code=200,
                    latency_ms=42,
                    request_id=request_id,
                    occurred_at=datetime.now(UTC),
                ),
                ApiCallLog(
                    provider="resend",
                    endpoint="/emails",
                    status_code=503,
                    latency_ms=1200,
                    error_class="ServiceUnavailable",
                    error_message="upstream unavailable",
                    request_id=uuid.uuid4(),
                    occurred_at=datetime.now(UTC),
                ),
            ]
        )
        await db.commit()

    resp = await client.get(
        "/admin/api-calls?provider=kma&status_code=200",
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    rows = resp.json()["data"]
    assert len(rows) == 1
    assert rows[0]["provider"] == "kma"
    assert rows[0]["latency_ms"] == 42
    assert rows[0]["request_id"] == str(request_id)


async def test_admin_stats_overview_counts_app_owned_tables(
    client,
    session_factory,
    auth_cookies,
) -> None:
    now = datetime.now(UTC)
    admin_id = await _create_admin_user(
        session_factory,
        roles=["user", "admin"],
        email_prefix="admin_stats",
    )
    owner_id = await _create_admin_user(
        session_factory,
        roles=["user"],
        email_prefix="owner_stats",
    )
    async with session_factory() as db:
        owner = await db.get(User, owner_id)
        assert owner is not None
        owner.user_attachment_quota_bytes_override = 2_147_483_648
        db.add(
            User(
                email=f"pending_{uuid.uuid4().hex[:8]}@pinvi.test",
                password_hash="x",
                nickname="가입대기",
                status="pending_verification",
                roles=["user"],
            )
        )
        trip = Trip(
            owner_user_id=owner_id,
            title="운영 지표 여행",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 2),
            status="planned",
            visibility="private",
        )
        completed_trip = Trip(
            owner_user_id=owner_id,
            title="완료 여행",
            status="completed",
            visibility="private",
        )
        db.add_all([trip, completed_trip])
        await db.flush()
        db.add(
            TripDay(
                trip_id=trip.trip_id,
                day_index=1,
                date=date(2026, 8, 1),
                title="1일차",
            )
        )
        await db.flush()
        db.add_all(
            [
                TripDayPoi(
                    trip_id=trip.trip_id,
                    day_index=1,
                    sort_order="a0",
                    feature_id="place-admin-stat",
                    feature_snapshot={"name": "통계 POI"},
                    added_by_user_id=owner_id,
                ),
                StorageSettings(
                    settings_id=1,
                    avatar_max_upload_bytes=1_048_576,
                    attachment_max_upload_bytes=5_242_880,
                    trip_attachment_quota_bytes=52_428_800,
                    user_attachment_quota_bytes=536_870_912,
                ),
                CuratedPlanAttachment(
                    trip_id=trip.trip_id,
                    bucket="pinvi-media",
                    storage_key=f"tests/{uuid.uuid4().hex}.pdf",
                    original_filename="stats.pdf",
                    content_type="application/pdf",
                    byte_size=12_345,
                    uploaded_by_user_id=owner_id,
                ),
                EmailQueue(
                    user_id=owner_id,
                    to_email="owner@example.com",
                    template="verify_email",
                    subject="인증",
                    status="pending",
                    scheduled_at=now,
                ),
                EmailQueue(
                    user_id=owner_id,
                    to_email="owner@example.com",
                    template="welcome",
                    subject="환영",
                    status="sent",
                    scheduled_at=now,
                    sent_at=now,
                ),
                ApiCallLog(
                    provider="resend",
                    endpoint="/emails",
                    status_code=202,
                    latency_ms=80,
                    occurred_at=now,
                ),
                ApiCallLog(
                    provider="gemini",
                    endpoint="/models",
                    status_code=502,
                    latency_ms=320,
                    error_class="BadGateway",
                    occurred_at=now,
                ),
                ApiCallLog(
                    provider="old",
                    endpoint="/stale",
                    status_code=500,
                    error_class="OldFailure",
                    occurred_at=now - timedelta(days=2),
                ),
            ]
        )
        await db.commit()

    resp = await client.get(
        "/admin/stats/overview",
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["users_total"] == 3
    assert data["users_24h"] == 3
    assert data["users_pending_verification"] == 1
    assert data["trips_total"] == 2
    assert data["trips_active"] == 1
    assert data["pois_total"] == 1
    assert data["email_queue_pending"] == 1
    assert data["api_calls_24h"] == 2
    assert data["api_calls_failed_24h"] == 1
    assert data["api_failure_rate_pct"] == 50.0
    assert data["api_latency_p95_ms"] == 308
    assert len(data["series_24h"]) == 24
    assert sum(bucket["api_calls"] for bucket in data["series_24h"]) == 2
    assert sum(bucket["api_failures"] for bucket in data["series_24h"]) == 1
    assert sum(bucket["users_created"] for bucket in data["series_24h"]) == 3
    assert sum(bucket["trips_created"] for bucket in data["series_24h"]) == 2
    assert data["load"]["cpu_count"] is None or data["load"]["cpu_count"] > 0
    assert data["capacity"]["attachments_total_bytes"] == 12_345
    assert data["capacity"]["attachments_count"] == 1
    assert data["capacity"]["attachment_max_upload_bytes"] == 5_242_880
    assert data["capacity"]["avatar_max_upload_bytes"] == 1_048_576
    assert data["capacity"]["trip_attachment_quota_bytes"] == 52_428_800
    assert data["capacity"]["user_attachment_quota_bytes"] == 536_870_912
    assert data["capacity"]["users_with_quota_override"] == 1
    assert data["capacity"]["disk_total_bytes"] is None or data["capacity"]["disk_total_bytes"] > 0
    assert data["features_by_kind"] == {}
    assert data["etl_last_24h"] == {"success": 0, "failed": 0}
