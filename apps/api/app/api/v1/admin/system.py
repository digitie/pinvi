"""`/admin/system/*` — 운영 의존 서비스 read-only 상태 요약."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
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
from app.schemas.admin import AdminSystemServiceStatus, AdminSystemSummary
from app.schemas.envelope import Envelope

router = APIRouter(prefix="/admin/system", tags=["admin"])

SYSTEM_PROBE_TIMEOUT_SECONDS = 2.0


@router.get("/summary", response_model=Envelope[AdminSystemSummary])
async def get_admin_system_summary(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
) -> Envelope[AdminSystemSummary]:
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

    return Envelope.of(
        AdminSystemSummary(
            generated_at=datetime.now(UTC),
            services=services,
        )
    )


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
