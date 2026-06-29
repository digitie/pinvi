"""Admin system summary API 통합 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.api.v1.admin import system as system_module
from app.models.user import User
from app.schemas.admin import AdminDockerContainerStatus, AdminSystemServiceStatus

pytestmark = pytest.mark.asyncio


async def _create_user(
    session_factory,  # type: ignore[no-untyped-def]
    *,
    roles: list[str],
    email_prefix: str,
) -> uuid.UUID:
    async with session_factory() as db:
        user = User(
            email=f"{email_prefix}_{uuid.uuid4().hex[:8]}@pinvi.test",
            password_hash="x",
            nickname="시스템",
            status="active",
            roles=roles,
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def test_admin_system_summary_reports_core_services_without_raw_urls(
    client,
    session_factory,
    auth_cookies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_probe_http(
        _client: Any,
        *,
        key: str,
        label: str,
        base_url: str,
        path: str,
    ) -> AdminSystemServiceStatus:
        del base_url, path
        status = "ok" if key != "kor_travel_map_api" else "degraded"
        message = "응답 정상" if status == "ok" else "HTTP 503"
        return AdminSystemServiceStatus(
            key=key,
            label=label,
            status=status,
            message=message,
            latency_ms=12,
        )

    monkeypatch.setattr(system_module, "_probe_http", fake_probe_http)
    admin_id = await _create_user(
        session_factory,
        roles=["user", "admin"],
        email_prefix="admin_system",
    )

    resp = await client.get(
        "/admin/system/summary",
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    assert "localhost" not in resp.text
    data = resp.json()["data"]
    assert data["generated_at"]
    services = {service["key"]: service for service in data["services"]}
    assert set(services) == {
        "pinvi_api",
        "postgres",
        "pinvi_web",
        "dagster",
        "kor_travel_map_api",
        "rustfs",
    }
    assert services["pinvi_api"]["status"] == "ok"
    assert services["postgres"]["status"] == "ok"
    assert services["kor_travel_map_api"]["status"] == "degraded"
    assert services["rustfs"]["latency_ms"] == 12


async def test_admin_system_detail_reports_dependencies_and_docker_containers(
    client,
    session_factory,
    auth_cookies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_probe_http(
        _client: Any,
        *,
        key: str,
        label: str,
        base_url: str,
        path: str,
    ) -> AdminSystemServiceStatus:
        del base_url, path
        return AdminSystemServiceStatus(
            key=key,
            label=label,
            status="ok",
            message="응답 정상",
            latency_ms=7,
        )

    async def fake_collect_docker_status() -> tuple[
        AdminSystemServiceStatus, list[AdminDockerContainerStatus]
    ]:
        return (
            AdminSystemServiceStatus(
                key="docker",
                label="Docker",
                status="ok",
                message="2개 container 수집",
                latency_ms=5,
            ),
            [
                AdminDockerContainerStatus(
                    container_id="abc123",
                    name="pinvi-api-latest",
                    image="pinvi-api:latest-main",
                    state="running",
                    status="Up 1 minute (healthy)",
                    health="healthy",
                    compose_project="kor-travel-docker-manager",
                    compose_service="pinvi-api",
                ),
                AdminDockerContainerStatus(
                    container_id="def456",
                    name="pinvi-web-latest",
                    image="pinvi-web:latest-main",
                    state="running",
                    status="Up 1 minute (healthy)",
                    health="healthy",
                    compose_project="kor-travel-docker-manager",
                    compose_service="pinvi-web",
                ),
            ],
        )

    monkeypatch.setattr(system_module, "_probe_http", fake_probe_http)
    monkeypatch.setattr(system_module, "_collect_docker_status", fake_collect_docker_status)
    admin_id = await _create_user(
        session_factory,
        roles=["user", "operator"],
        email_prefix="operator_system_detail",
    )

    resp = await client.get(
        "/admin/system/detail",
        cookies=auth_cookies(str(admin_id)),
    )

    assert resp.status_code == 200, resp.text
    assert "localhost" not in resp.text
    data = resp.json()["data"]
    assert data["generated_at"]
    assert data["docker"]["status"] == "ok"
    assert data["docker"]["message"] == "2개 container 수집"
    assert {service["key"] for service in data["dependencies"]} == {
        "pinvi_api",
        "postgres",
        "pinvi_web",
        "dagster",
        "kor_travel_map_api",
        "rustfs",
    }
    assert [container["name"] for container in data["containers"]] == [
        "pinvi-api-latest",
        "pinvi-web-latest",
    ]
    assert data["containers"][0]["health"] == "healthy"
    assert data["containers"][0]["compose_service"] == "pinvi-api"


async def test_admin_system_summary_requires_admin_or_operator(
    client,
    session_factory,
    auth_cookies,
) -> None:
    user_id = await _create_user(
        session_factory,
        roles=["user"],
        email_prefix="user_system",
    )

    resp = await client.get(
        "/admin/system/summary",
        cookies=auth_cookies(str(user_id)),
    )

    assert resp.status_code == 404

    detail_resp = await client.get(
        "/admin/system/detail",
        cookies=auth_cookies(str(user_id)),
    )
    assert detail_resp.status_code == 404
