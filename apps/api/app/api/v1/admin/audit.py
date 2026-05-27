"""`/admin/audit/*` — admin_audit_log read-only + chain 검증."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.audit import AdminAuditLog
from app.models.user import User
from app.schemas.admin import AdminAuditEntry
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


@router.get("/verify-chain", response_model=Envelope[dict])
async def verify_chain(
    _admin: Annotated[User, Depends(require_role("cpo"))],
    db: DbSession,
) -> Envelope[dict]:
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
