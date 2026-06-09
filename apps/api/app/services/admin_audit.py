"""admin_audit_log chain 적재 — `docs/compliance/pipa.md` §6 / SPEC V8 O-6."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AdminAuditLog
from app.services.hash_chain import GENESIS_HASH, compute_content_hash, sha256_hex

_ADMIN_AUDIT_CHAIN_LOCK_NAMESPACE = 0x54524D54  # "TRMT"
_ADMIN_AUDIT_CHAIN_LOCK_RESOURCE = 0x41414454  # "AADT"
_SAFE_SCHEMA_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


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
    """audit row append (append-only trigger 보장).

    호출자는 업무 상태 변경과 audit append를 같은 트랜잭션에 묶은 뒤 commit한다.
    """
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :resource)"),
        {
            "namespace": _ADMIN_AUDIT_CHAIN_LOCK_NAMESPACE,
            "resource": _ADMIN_AUDIT_CHAIN_LOCK_RESOURCE,
        },
    )
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
    await db.flush()
    return row


async def append_admin_audit_to_schema(
    db: AsyncSession,
    *,
    schema: str,
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
) -> None:
    """append an admin audit row to a known-safe schema.

    Schema-swap restore moves the live `app` schema to `app_previous_*`. The
    post-cutover reflection must land in that previous schema so the live
    pre-restore chain remains forensics-complete instead of trying to append to
    the newly restored `app` schema, where the triggering admin may not exist.
    """
    if _SAFE_SCHEMA_RE.fullmatch(schema) is None:
        raise ValueError(f"unsafe audit schema: {schema}")

    await db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :resource)"),
        {
            "namespace": _ADMIN_AUDIT_CHAIN_LOCK_NAMESPACE,
            "resource": _ADMIN_AUDIT_CHAIN_LOCK_RESOURCE,
        },
    )
    last_hash_sql = f"""
        SELECT content_hash
        FROM {schema}.admin_audit_log
        ORDER BY log_id DESC
        LIMIT 1
        """  # noqa: S608 - schema is validated by _SAFE_SCHEMA_RE above.
    last_hash = await db.scalar(text(last_hash_sql))
    prev_hash = str(last_hash) if last_hash else GENESIS_HASH
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
    insert_sql = f"""
        INSERT INTO {schema}.admin_audit_log (
            actor_user_id,
            action,
            resource_type,
            resource_id,
            before_state,
            after_state,
            access_reason,
            target_pii_fields,
            ip_hash,
            user_agent,
            request_id,
            prev_hash,
            content_hash,
            occurred_at
        )
        VALUES (
            :actor_user_id,
            :action,
            :resource_type,
            :resource_id,
            CAST(:before_state AS jsonb),
            CAST(:after_state AS jsonb),
            :access_reason,
            CAST(:target_pii_fields AS varchar[]),
            :ip_hash,
            :user_agent,
            :request_id,
            :prev_hash,
            :content_hash,
            :occurred_at
        )
        """  # noqa: S608 - schema is validated by _SAFE_SCHEMA_RE above.
    await db.execute(
        text(insert_sql),
        {
            "actor_user_id": actor_user_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "before_state": json.dumps(before_state) if before_state is not None else None,
            "after_state": json.dumps(after_state) if after_state is not None else None,
            "access_reason": access_reason,
            "target_pii_fields": target_pii_fields,
            "ip_hash": ip_hash,
            "user_agent": user_agent,
            "request_id": request_id,
            "prev_hash": prev_hash,
            "content_hash": content_hash,
            "occurred_at": now,
        },
    )
