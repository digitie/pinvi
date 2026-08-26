"""동시 retention execute 방지 (T-343).

"실행 중인 run이 있는지 조회 후 없으면 진행"은 그 자체로 경합 조건이다 — 두 요청이 거의 동시에
조회하면 둘 다 통과한다. 파괴 SQL이 서로 다른 두 실행에서 같은 행을 대상으로 겹치면 데이터가
꼬이고, `append_admin_audit`의 전역 advisory lock과 얽혀 대기 순서가 어긋날 수 있다.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.models.user import User
from app.services import admin_retention

pytestmark = pytest.mark.asyncio


async def _make_actor(session_factory) -> uuid.UUID:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        actor = User(
            email=f"conc_{uuid.uuid4().hex[:8]}@pinvi.test", status="active", roles=["user", "cpo"]
        )
        db.add(actor)
        await db.commit()
        await db.refresh(actor)
        return actor.user_id


async def test_already_executing_run_blocks_a_new_one(session_factory, monkeypatch):  # type: ignore[no-untyped-def]
    """`executing` 행이 이미 있으면 새 요청은 즉시 거절돼야 한다."""
    settings = get_settings()
    monkeypatch.setattr(settings, "pinvi_retention_execute_enabled", True, raising=False)
    actor_id = await _make_actor(session_factory)

    async with session_factory() as db:
        await db.execute(
            text(
                "INSERT INTO app.retention_runs "
                "(run_id, status, mode, access_reason, actor_user_id) "
                "VALUES (:run_id, 'executing', 'execute', :reason, :actor)"
            ),
            {"run_id": uuid.uuid4(), "reason": "T-343 setup", "actor": actor_id},
        )
        await db.commit()

    async with session_factory() as db:
        with pytest.raises(admin_retention.RetentionPrecheckError, match="already in progress"):
            await admin_retention.execute_retention(
                db,
                actor_user_id=actor_id,
                scope="location",
                access_reason="T-343 blocked test",
                confirm_phrase=settings.pinvi_retention_execute_confirm_phrase,
            )


async def test_two_simultaneous_executes_only_one_wins(session_factory, monkeypatch):  # type: ignore[no-untyped-def]
    """진짜 동시에 들어온 두 요청 중 정확히 하나만 통과해야 한다.

    체크 후 삽입 사이의 경합 조건을 실제로 재현한다 — 두 개의 독립 세션으로 `execute_retention`을
    `asyncio.gather`로 동시에 호출한다. advisory lock이 없으면 이 테스트는 두 요청 모두 성공하는
    형태로 낡을 수 있다(경합 조건이라 항상 재현되는 것은 아니지만, 반복 시 통계적으로 드러난다).
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "pinvi_retention_execute_enabled", True, raising=False)
    actor_id = await _make_actor(session_factory)

    async def _attempt() -> Exception | None:
        async with session_factory() as db:
            try:
                await admin_retention.execute_retention(
                    db,
                    actor_user_id=actor_id,
                    scope="location",
                    access_reason="T-343 race test",
                    confirm_phrase=settings.pinvi_retention_execute_confirm_phrase,
                )
            except Exception as exc:  # 결과를 모아 아래서 정확히 하나만 골라낸다
                return exc
            return None

    results = await asyncio.gather(_attempt(), _attempt())
    successes = [r for r in results if r is None]
    failures = [r for r in results if r is not None]

    assert len(successes) == 1, f"정확히 하나만 성공해야 한다: {results}"
    assert len(failures) == 1
    assert isinstance(failures[0], admin_retention.RetentionPrecheckError)

    async with session_factory() as db:
        count = await db.scalar(
            text("SELECT count(*) FROM app.retention_runs WHERE actor_user_id = :actor"),
            {"actor": actor_id},
        )
        assert count == 1, "진 쪽이 영수증까지 남겼다면 안전장치가 이중으로 새고 있는 것이다"


async def test_db_rejects_second_executing_row_bypassing_advisory_lock(session_factory):  # type: ignore[no-untyped-def]
    """`_assert_no_concurrent_execution`을 거치지 않는 직접 INSERT도 DB가 막아야 한다(T-349).

    advisory lock 규율은 애플리케이션 코드 경로에서만 강제된다 — 다른 코드 경로나 수동 SQL이
    같은 함수를 거치지 않고 INSERT하면 그 규율은 무력하다. `uq_retention_runs_single_executing`
    partial unique index가 이 경우의 마지막 보루다.
    """
    actor_id = await _make_actor(session_factory)

    async with session_factory() as db:
        await db.execute(
            text(
                "INSERT INTO app.retention_runs "
                "(run_id, status, mode, access_reason, actor_user_id) "
                "VALUES (:run_id, 'executing', 'execute', :reason, :actor)"
            ),
            {"run_id": uuid.uuid4(), "reason": "T-349 first row", "actor": actor_id},
        )
        await db.commit()

    async with session_factory() as db:
        with pytest.raises(IntegrityError, match="uq_retention_runs_single_executing"):
            await db.execute(
                text(
                    "INSERT INTO app.retention_runs "
                    "(run_id, status, mode, access_reason, actor_user_id) "
                    "VALUES (:run_id, 'executing', 'execute', :reason, :actor)"
                ),
                {"run_id": uuid.uuid4(), "reason": "T-349 second row", "actor": actor_id},
            )
            await db.commit()
