"""Admin audit hash-chain serialization regression tests."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.audit import AdminAuditLog
from app.models.user import User
from app.services.admin_audit import append_admin_audit
from app.services.hash_chain import GENESIS_HASH

pytestmark = pytest.mark.asyncio


async def _make_admin_user(session_factory) -> uuid.UUID:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        user = User(
            email=f"admin_audit_{uuid.uuid4().hex[:8]}@pinvi.test",
            password_hash="x",
            nickname="감사 관리자",
            status="active",
            roles=["admin"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.user_id


async def _append_test_audit(
    session_factory,  # type: ignore[no-untyped-def]
    *,
    actor_user_id: uuid.UUID,
    action: str,
) -> None:
    async with session_factory() as db:
        await append_admin_audit(
            db,
            actor_user_id=actor_user_id,
            action=action,
            resource_type="user",
            resource_id=str(actor_user_id),
            before_state=None,
            after_state={"action": action},
            access_reason="동시성 회귀 테스트",
            target_pii_fields=None,
            ip_hash_input="127.0.0.1",
            user_agent="pytest",
            request_id=uuid.uuid4(),
        )
        await db.commit()


async def test_admin_audit_append_serializes_chain_head(session_factory) -> None:
    actor_id = await _make_admin_user(session_factory)

    async with session_factory() as first_db:
        await append_admin_audit(
            first_db,
            actor_user_id=actor_id,
            action="user.first",
            resource_type="user",
            resource_id=str(actor_id),
            before_state=None,
            after_state={"action": "user.first"},
            access_reason="첫 번째 감사",
            target_pii_fields=None,
            ip_hash_input="127.0.0.1",
            user_agent="pytest",
            request_id=uuid.uuid4(),
        )

        second_started = asyncio.Event()

        async def _append_second() -> None:
            second_started.set()
            await _append_test_audit(
                session_factory,
                actor_user_id=actor_id,
                action="user.second",
            )

        second_task = asyncio.create_task(_append_second())
        await second_started.wait()
        await asyncio.sleep(0.1)

        assert not second_task.done()
        await first_db.commit()
        await asyncio.wait_for(second_task, timeout=3.0)

    async with session_factory() as db:
        rows = list(
            (await db.execute(select(AdminAuditLog).order_by(AdminAuditLog.log_id))).scalars()
        )

    assert len(rows) == 2
    assert rows[0].prev_hash == GENESIS_HASH
    assert rows[1].prev_hash == rows[0].content_hash
    assert len({row.prev_hash for row in rows}) == 2


async def test_admin_audit_prev_hash_unique_constraint_rejects_fork(session_factory) -> None:
    actor_id = await _make_admin_user(session_factory)
    await _append_test_audit(
        session_factory,
        actor_user_id=actor_id,
        action="user.first",
    )

    async with session_factory() as db:
        db.add(
            AdminAuditLog(
                actor_user_id=actor_id,
                action="user.fork",
                resource_type="user",
                resource_id=str(actor_id),
                before_state=None,
                after_state={"action": "user.fork"},
                access_reason="fork 삽입 차단 테스트",
                target_pii_fields=None,
                ip_hash="0" * 64,
                user_agent="pytest",
                request_id=uuid.uuid4(),
                prev_hash=GENESIS_HASH,
                content_hash="f" * 64,
                occurred_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
