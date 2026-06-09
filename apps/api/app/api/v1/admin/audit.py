"""`/admin/audit/*` — admin_audit_log read-only + chain 검증."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.audit import AdminAuditLog, LocationAccessLog
from app.models.user import User
from app.schemas.admin import AdminAuditEntry, AdminLocationAuditEntry
from app.schemas.envelope import Envelope
from app.services.hash_chain import GENESIS_HASH, compute_content_hash

router = APIRouter(prefix="/admin/audit", tags=["admin"])


@router.get("", response_model=Envelope[list[AdminAuditEntry]])
async def list_audit_log(
    _admin: Annotated[User, Depends(require_role("admin", "cpo"))],
    db: DbSession,
    limit: int = 50,
) -> Envelope[list[AdminAuditEntry]]:
    result = await db.execute(
        select(AdminAuditLog).order_by(AdminAuditLog.log_id.desc()).limit(limit)
    )
    rows = list(result.scalars())
    return Envelope.of([_to_entry(r) for r in rows])


@router.get("/verify-chain", response_model=Envelope[dict[str, Any]])
async def verify_chain(
    _admin: Annotated[User, Depends(require_role("cpo"))],
    db: DbSession,
) -> Envelope[dict[str, Any]]:
    """admin_audit_log chain 검증 — 깨진 row가 있으면 첫 위치 반환."""
    result = await db.execute(select(AdminAuditLog).order_by(AdminAuditLog.log_id))
    rows = list(result.scalars())
    prev = GENESIS_HASH
    broken_at: int | None = None
    for row in rows:
        expected = compute_content_hash(
            prev,
            {
                "actor_user_id": str(row.actor_user_id),
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "before_state": row.before_state,
                "after_state": row.after_state,
                "access_reason": row.access_reason,
                "target_pii_fields": row.target_pii_fields,
                "ip_hash": row.ip_hash,
                "user_agent": row.user_agent,
                "request_id": str(row.request_id),
                "occurred_at": row.occurred_at.isoformat(),
            },
        )
        if row.prev_hash != prev or row.content_hash != expected:
            broken_at = row.log_id
            break
        prev = row.content_hash
    return Envelope.of(
        {"valid": broken_at is None, "broken_at": broken_at, "rows_checked": len(rows)}
    )


@router.get("/location", response_model=Envelope[list[AdminLocationAuditEntry]])
async def list_location_audit_log(
    _cpo: Annotated[User, Depends(require_role("cpo"))],
    db: DbSession,
    response: Response,
    user_id: uuid.UUID | None = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Envelope[list[AdminLocationAuditEntry]]:
    filters: list[Any] = []
    if user_id is not None:
        filters.append(LocationAccessLog.user_id == user_id)
    if from_ is not None:
        filters.append(LocationAccessLog.occurred_at >= from_)
    if to is not None:
        filters.append(LocationAccessLog.occurred_at <= to)

    stmt = (
        select(LocationAccessLog)
        .where(*filters)
        .order_by(LocationAccessLog.log_id.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = list(result.scalars())
    if await _is_location_chain_broken(db):
        response.headers["X-Chain-Broken"] = "true"
    return Envelope.of([_to_location_entry(row) for row in rows])


def _to_entry(r: AdminAuditLog) -> AdminAuditEntry:
    return AdminAuditEntry(
        log_id=r.log_id,
        actor_user_id=r.actor_user_id,
        action=r.action,
        resource_type=r.resource_type,
        resource_id=r.resource_id,
        access_reason=r.access_reason,
        target_pii_fields=r.target_pii_fields,
        prev_hash=r.prev_hash,
        content_hash=r.content_hash,
        occurred_at=r.occurred_at,
    )


def _to_location_entry(r: LocationAccessLog) -> AdminLocationAuditEntry:
    return AdminLocationAuditEntry(
        log_id=r.log_id,
        user_id=r.user_id,
        occurred_at=r.occurred_at,
        endpoint=r.endpoint,
        purpose=r.purpose,
        lat_masked=_mask_coord(r.lat),
        lng_masked=_mask_coord(r.lng),
        request_id=r.request_id,
        ip_hash=r.ip_hash,
        prev_hash=r.prev_hash,
        content_hash=r.content_hash,
    )


async def _is_location_chain_broken(db: AsyncSession) -> bool:
    result = await db.execute(select(LocationAccessLog).order_by(LocationAccessLog.log_id))
    prev = GENESIS_HASH
    for row in result.scalars():
        expected = compute_content_hash(
            prev,
            {
                "user_id": str(row.user_id),
                "occurred_at": row.occurred_at.isoformat(),
                "endpoint": row.endpoint,
                "purpose": row.purpose,
                "lat": _coord_str(row.lat),
                "lng": _coord_str(row.lng),
                "request_id": str(row.request_id),
                "ip_hash": row.ip_hash,
            },
        )
        if row.prev_hash != prev or row.content_hash != expected:
            return True
        prev = row.content_hash
    return False


def _coord_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value.quantize(Decimal("0.000001")))


def _mask_coord(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value.quantize(Decimal("0.0001")))
