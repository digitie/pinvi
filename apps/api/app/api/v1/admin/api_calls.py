"""`/admin/api-calls` — app.api_call_log read-only."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.api_call_log import ApiCallLog
from app.models.user import User
from app.schemas.admin import AdminApiCallEntry
from app.schemas.envelope import Envelope

router = APIRouter(prefix="/admin/api-calls", tags=["admin"])


@router.get("", response_model=Envelope[list[AdminApiCallEntry]])
async def list_api_calls(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    db: DbSession,
    provider: Annotated[str | None, Query(max_length=64)] = None,
    status_code: Annotated[int | None, Query(ge=100, le=599)] = None,
    error_class: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Envelope[list[AdminApiCallEntry]]:
    filters: list[Any] = []
    if provider:
        filters.append(ApiCallLog.provider == provider)
    if status_code is not None:
        filters.append(ApiCallLog.status_code == status_code)
    if error_class:
        filters.append(ApiCallLog.error_class == error_class)
    result = await db.execute(
        select(ApiCallLog)
        .where(*filters)
        .order_by(ApiCallLog.occurred_at.desc(), ApiCallLog.log_id.desc())
        .limit(limit)
    )
    return Envelope.of([_to_entry(row) for row in result.scalars()])


def _to_entry(row: ApiCallLog) -> AdminApiCallEntry:
    return AdminApiCallEntry(
        log_id=row.log_id,
        provider=row.provider,
        endpoint=row.endpoint,
        status_code=row.status_code,
        latency_ms=row.latency_ms,
        error_class=row.error_class,
        error_message=row.error_message,
        request_id=row.request_id,
        occurred_at=row.occurred_at,
    )
