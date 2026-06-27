"""Admin seed/reset dev-only safety tests (T-214)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.audit import AdminAuditLog
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _create_admin(session_factory: Any) -> str:
    async with session_factory() as db:
        user = User(
            email=f"seed-admin-{uuid.uuid4()}@example.com",
            password_hash="x",
            status="active",
            roles=["user", "admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return str(user.user_id)


async def test_seed_scenario_dry_run_writes_audit(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    user_id = await _create_admin(session_factory)
    request_id = uuid.uuid4()

    list_resp = await client.get("/admin/seed/scenarios", cookies=auth_cookies(user_id))
    assert list_resp.status_code == 200, list_resp.text
    scenarios = list_resp.json()["data"]["scenarios"]
    assert len(scenarios) == 8
    scenario = scenarios[0]

    resp = await client.post(
        f"/admin/seed/scenarios/{scenario['key']}",
        json={
            "confirm": scenario["confirm_phrase"],
            "access_reason": "dev smoke dry-run",
            "dry_run": True,
        },
        headers={"X-Request-Id": str(request_id)},
        cookies=auth_cookies(user_id),
    )

    assert resp.status_code == 202, resp.text
    data = resp.json()["data"]
    assert data["action"] == "dev_seed.dry_run"
    assert data["target"] == scenario["key"]
    assert data["status"] == "dry_run"

    async with session_factory() as db:
        audit = await db.scalar(select(AdminAuditLog).where(AdminAuditLog.request_id == request_id))
    assert audit is not None
    assert audit.action == "dev_seed.dry_run"
    assert audit.resource_type == "seed_scenario"
    assert audit.resource_id == scenario["key"]
    assert audit.access_reason == "dev smoke dry-run"


async def test_seed_scenario_requires_confirmation(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    user_id = await _create_admin(session_factory)
    resp = await client.post(
        "/admin/seed/scenarios/new_user_first_trip",
        json={"confirm": "RUN wrong", "access_reason": "dev smoke dry-run", "dry_run": True},
        cookies=auth_cookies(user_id),
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "CONFIRMATION_MISMATCH"


async def test_reset_dry_run_writes_audit(
    client: Any, session_factory: Any, auth_cookies: Any
) -> None:
    user_id = await _create_admin(session_factory)
    request_id = uuid.uuid4()

    status_resp = await client.get("/admin/reset/status", cookies=auth_cookies(user_id))
    assert status_resp.status_code == 200, status_resp.text
    assert status_resp.json()["data"]["confirm_phrase"] == "RESET"

    resp = await client.post(
        "/admin/reset",
        json={
            "confirm": "RESET",
            "access_reason": "reset rehearsal",
            "dry_run": True,
            "include_seed": False,
        },
        headers={"X-Request-Id": str(request_id)},
        cookies=auth_cookies(user_id),
    )

    assert resp.status_code == 202, resp.text
    data = resp.json()["data"]
    assert data["action"] == "dev_reset.dry_run"
    assert data["target"] == "app"
    assert all("seed" not in step for step in data["would_execute"])

    async with session_factory() as db:
        audit = await db.scalar(select(AdminAuditLog).where(AdminAuditLog.request_id == request_id))
    assert audit is not None
    assert audit.action == "dev_reset.dry_run"
    assert audit.resource_type == "reset"
    assert audit.resource_id == "app"
    assert audit.after_state["include_seed"] is False


async def test_seed_reset_routes_are_hidden_in_production(
    client: Any, session_factory: Any, auth_cookies: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = await _create_admin(session_factory)
    monkeypatch.setattr(settings, "pinvi_environment", "production")
    try:
        seed_resp = await client.get("/admin/seed/scenarios", cookies=auth_cookies(user_id))
        reset_resp = await client.get("/admin/reset/status", cookies=auth_cookies(user_id))
    finally:
        monkeypatch.setattr(settings, "pinvi_environment", "development")

    assert seed_resp.status_code == 404
    assert reset_resp.status_code == 404
