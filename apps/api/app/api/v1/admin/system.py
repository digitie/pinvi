"""`/admin/system/*` — 운영 의존 서비스 read-only 상태 요약."""

from __future__ import annotations

import asyncio
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urljoin

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import (
    AdminDockerContainerStatus,
    AdminSystemDetail,
    AdminSystemServiceStatus,
    AdminSystemSummary,
)
from app.schemas.envelope import Envelope

router = APIRouter(prefix="/admin/system", tags=["admin"])

SYSTEM_PROBE_TIMEOUT_SECONDS = 2.0
_DOCKER_HEALTH_RE = re.compile(r"\((healthy|unhealthy|health: starting|starting)\)")


@router.get("/summary", response_model=Envelope[AdminSystemSummary])
async def get_admin_system_summary(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
) -> Envelope[AdminSystemSummary]:
    return Envelope.of(
        AdminSystemSummary(
            generated_at=datetime.now(UTC),
            services=await _probe_dependency_services(db),
        )
    )


@router.get("/detail", response_model=Envelope[AdminSystemDetail])
async def get_admin_system_detail(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
) -> Envelope[AdminSystemDetail]:
    dependencies, docker_result = await asyncio.gather(
        _probe_dependency_services(db),
        _collect_docker_status(),
    )
    docker, containers = docker_result
    return Envelope.of(
        AdminSystemDetail(
            generated_at=datetime.now(UTC),
            dependencies=dependencies,
            docker=docker,
            containers=containers,
        )
    )


async def _probe_dependency_services(db: AsyncSession) -> list[AdminSystemServiceStatus]:
    services: list[AdminSystemServiceStatus] = [
        AdminSystemServiceStatus(
            key="pinvi_api",
            label="Pinvi API",
            status="ok",
            message="admin route 응답 정상",
            latency_ms=0,
        ),
        await _probe_db(db),
    ]

    timeout = httpx.Timeout(SYSTEM_PROBE_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout) as client:
        services.extend(
            await asyncio.gather(
                _probe_http(
                    client,
                    key="pinvi_web",
                    label="Web",
                    base_url=settings.pinvi_web_base_url,
                    path="/",
                ),
                _probe_http(
                    client,
                    key="dagster",
                    label="Dagster",
                    base_url=settings.pinvi_dagster_base_url,
                    path="/",
                ),
                _probe_http(
                    client,
                    key="kor_travel_map_api",
                    label="kor-travel-map API",
                    base_url=settings.pinvi_kor_travel_map_api_base_url,
                    path="/health",
                ),
                _probe_http(
                    client,
                    key="rustfs",
                    label="RustFS",
                    base_url=settings.pinvi_rustfs_endpoint_url,
                    path="/health/live",
                ),
            )
        )

    return services


async def _probe_db(db: AsyncSession) -> AdminSystemServiceStatus:
    start = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        return AdminSystemServiceStatus(
            key="postgres",
            label="DB",
            status="down",
            message="연결 실패",
            latency_ms=_elapsed_ms(start),
        )
    return AdminSystemServiceStatus(
        key="postgres",
        label="DB",
        status="ok",
        message="SELECT 1 정상",
        latency_ms=_elapsed_ms(start),
    )


async def _probe_http(
    client: httpx.AsyncClient,
    *,
    key: str,
    label: str,
    base_url: str,
    path: str,
) -> AdminSystemServiceStatus:
    if not base_url.strip():
        return AdminSystemServiceStatus(
            key=key,
            label=label,
            status="unknown",
            message="base URL 미설정",
        )

    start = time.perf_counter()
    try:
        response = await client.get(_join_url(base_url, path))
    except httpx.HTTPError:
        return AdminSystemServiceStatus(
            key=key,
            label=label,
            status="down",
            message="연결 실패",
            latency_ms=_elapsed_ms(start),
        )

    ok = 200 <= response.status_code < 400
    return AdminSystemServiceStatus(
        key=key,
        label=label,
        status="ok" if ok else "degraded",
        message="응답 정상" if ok else f"HTTP {response.status_code}",
        latency_ms=_elapsed_ms(start),
    )


def _join_url(base_url: str, path: str) -> str:
    return urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))


def _elapsed_ms(start: float) -> int:
    return max(0, int((time.perf_counter() - start) * 1000))


async def _collect_docker_status() -> tuple[
    AdminSystemServiceStatus, list[AdminDockerContainerStatus]
]:
    socket_path = Path(settings.pinvi_docker_socket_path)
    if not await asyncio.to_thread(socket_path.exists):
        return (
            AdminSystemServiceStatus(
                key="docker",
                label="Docker",
                status="unknown",
                message="Docker socket 미설정",
            ),
            [],
        )

    start = time.perf_counter()
    timeout = httpx.Timeout(settings.pinvi_docker_status_timeout_seconds)
    transport = httpx.AsyncHTTPTransport(uds=str(socket_path))
    try:
        async with httpx.AsyncClient(
            base_url="http://docker",
            transport=transport,
            timeout=timeout,
        ) as client:
            response = await client.get(
                "/containers/json",
                params={
                    "all": "1",
                    "limit": str(_docker_container_limit()),
                },
            )
    except (OSError, httpx.HTTPError):
        return (
            AdminSystemServiceStatus(
                key="docker",
                label="Docker",
                status="down",
                message="Docker 상태 수집 실패",
                latency_ms=_elapsed_ms(start),
            ),
            [],
        )

    if response.status_code >= 400:
        return (
            AdminSystemServiceStatus(
                key="docker",
                label="Docker",
                status="degraded",
                message=f"Docker API HTTP {response.status_code}",
                latency_ms=_elapsed_ms(start),
            ),
            [],
        )

    try:
        payload = response.json()
    except ValueError:
        return (
            AdminSystemServiceStatus(
                key="docker",
                label="Docker",
                status="degraded",
                message="Docker API 응답 파싱 실패",
                latency_ms=_elapsed_ms(start),
            ),
            [],
        )

    if not isinstance(payload, list):
        return (
            AdminSystemServiceStatus(
                key="docker",
                label="Docker",
                status="degraded",
                message="Docker API 응답 형식 불일치",
                latency_ms=_elapsed_ms(start),
            ),
            [],
        )

    containers = [
        _container_from_docker_payload(item)
        for item in payload[: _docker_container_limit()]
        if isinstance(item, dict)
    ]
    return (
        AdminSystemServiceStatus(
            key="docker",
            label="Docker",
            status="ok",
            message=f"{len(containers)}개 container 수집",
            latency_ms=_elapsed_ms(start),
        ),
        containers,
    )


def _docker_container_limit() -> int:
    return max(1, min(settings.pinvi_docker_status_container_limit, 200))


def _container_from_docker_payload(payload: dict[str, object]) -> AdminDockerContainerStatus:
    names = payload.get("Names")
    primary_name = ""
    if isinstance(names, list) and names:
        primary_name = str(names[0]).lstrip("/")
    labels = payload.get("Labels")
    label_map = labels if isinstance(labels, dict) else {}
    status = str(payload.get("Status") or payload.get("State") or "unknown")
    return AdminDockerContainerStatus(
        container_id=str(payload.get("Id") or "")[:12],
        name=primary_name or str(payload.get("Id") or "")[:12],
        image=str(payload.get("Image") or ""),
        state=str(payload.get("State") or "unknown"),
        status=status,
        health=_health_from_status(status),
        compose_project=_label_value(label_map, "com.docker.compose.project"),
        compose_service=_label_value(label_map, "com.docker.compose.service"),
    )


def _label_value(labels: dict[object, object], key: str) -> str | None:
    value = labels.get(key)
    return str(value) if value is not None else None


def _health_from_status(status: str) -> str | None:
    match = _DOCKER_HEALTH_RE.search(status)
    if match is None:
        return None
    return match.group(1).replace("health: ", "")
