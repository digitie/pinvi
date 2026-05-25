"""`/health*` — `docs/api/health.md`."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.schemas.health import HealthDbResponse, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/health/db", response_model=HealthDbResponse)
async def health_db(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HealthDbResponse:
    start = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DB_UNAVAILABLE",
                "message": "DB 연결에 실패했습니다.",
                "details": {"reason": str(exc)},
            },
        ) from exc
    latency_ms = int((time.perf_counter() - start) * 1000)
    return HealthDbResponse(latency_ms=latency_ms)
