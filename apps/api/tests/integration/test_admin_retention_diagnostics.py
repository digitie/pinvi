"""`pg_stat_activity`로 실행 중인 retention execute를 찾을 수 있는지 (T-344).

runbook §5.2는 "`executing`이 오래 남아 있으면 살아 있는지 확인한다"고 적었지만, `run_id`와 DB
백엔드를 잇는 수단이 없어 그 확인을 실제로 수행할 방법이 없었다. `application_name`에 run_id를
싣는 것이 그 수단이다.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def test_application_name_carries_the_run_id_while_executing(session_factory, monkeypatch):  # type: ignore[no-untyped-def]
    """실행 중인 트랜잭션을 `pg_stat_activity.application_name`으로 찾을 수 있어야 한다."""
    from app.core.config import get_settings
    from app.models.user import User
    from app.services import admin_retention

    settings = get_settings()
    monkeypatch.setattr(settings, "pinvi_retention_execute_enabled", True, raising=False)

    async with session_factory() as db:
        actor = User(
            email=f"diag_{uuid.uuid4().hex[:8]}@pinvi.test", status="active", roles=["user", "cpo"]
        )
        db.add(actor)
        await db.commit()
        await db.refresh(actor)
        actor_id = actor.user_id

    reached = asyncio.Event()
    release = asyncio.Event()

    async def _paused_archive(*args: object, **kwargs: object) -> dict[str, int]:
        reached.set()
        await release.wait()
        return {}

    monkeypatch.setattr(admin_retention, "_execute_location_archive", _paused_archive)

    async def _run() -> None:
        async with session_factory() as db:
            await admin_retention.execute_retention(
                db,
                actor_user_id=actor_id,
                scope="location",
                access_reason="T-344 diagnostics test",
                confirm_phrase=settings.pinvi_retention_execute_confirm_phrase,
            )

    task = asyncio.create_task(_run())
    try:
        await asyncio.wait_for(reached.wait(), timeout=10)

        async with session_factory() as db:
            row = await db.scalar(
                text(
                    "SELECT application_name FROM pg_stat_activity "
                    "WHERE application_name LIKE 'pinvi-retention-execute:%'"
                )
            )
        assert row is not None, "실행 중인 세션을 pg_stat_activity에서 찾지 못했다"
        prefix, _, run_id_part = row.partition(":")
        assert prefix == "pinvi-retention-execute"
        assert uuid.UUID(run_id_part), "이름 뒷부분이 유효한 UUID가 아니다 — 잘렸을 수 있다"
    finally:
        release.set()
        await asyncio.wait_for(task, timeout=10)


async def test_application_name_is_63_bytes_or_fewer(session_factory):  # type: ignore[no-untyped-def]
    """PostgreSQL의 `application_name` 길이 한도(NAMEDATALEN 기반 63바이트)를 넘지 않아야 한다.

    넘으면 조용히 잘려 run_id 뒷부분이 사라진다 — `pg_stat_activity` 조회가 정확한 run을 찾지
    못하게 된다.
    """
    name = f"pinvi-retention-execute:{uuid.uuid4()}"
    async with session_factory() as db:
        await db.execute(text("SELECT set_config('application_name', :name, true)"), {"name": name})
        stored = await db.scalar(text("SHOW application_name"))
        await db.rollback()
    assert stored == name, f"application_name이 잘렸다: {stored!r} (원본 길이 {len(name)})"
