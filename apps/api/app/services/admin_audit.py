"""admin_audit_log chain 적재 — `docs/compliance/pipa.md` §6 / SPEC V8 O-6."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AdminAuditLog
from app.services.hash_chain import GENESIS_HASH, compute_content_hash, sha256_hex


async def append_admin_audit(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    action: str,
    resource_type: str,
    resource_id: str | None,
    before_state: dict[str, Any] | None,
    after_state: dict[str, Any] | None,
    access_reason: str | None,
    target_pii_fields: list[str] | None,
    ip_hash_input: str,
    user_agent: str | None,
    request_id: uuid.UUID,
) -> AdminAuditLog:
    """audit row append (append-only trigger 보장)."""
    last = await db.scalar(select(AdminAuditLog).order_by(AdminAuditLog.log_id.desc()).limit(1))
    prev_hash = last.content_hash if last else GENESIS_HASH
    now = datetime.now(UTC)
    ip_hash = sha256_hex(ip_hash_input or "")
    payload = {
        "actor_user_id": str(actor_user_id),
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "before_state": before_state,
        "after_state": after_state,
        "access_reason": access_reason,
        "target_pii_fields": target_pii_fields,
        "ip_hash": ip_hash,
        "user_agent": user_agent,
        "request_id": str(request_id),
        "occurred_at": now.isoformat(),
    }
    content_hash = compute_content_hash(prev_hash, payload)
    row = AdminAuditLog(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before_state=before_state,
        after_state=after_state,
        access_reason=access_reason,
        target_pii_fields=target_pii_fields,
        ip_hash=ip_hash,
        user_agent=user_agent,
        request_id=request_id,
        prev_hash=prev_hash,
        content_hash=content_hash,
        occurred_at=now,
    )
    db.add(row)
    await db.commit()
    return row
