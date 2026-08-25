"""세션 GUC 타임아웃이 실제로 적용되는지 (T-341).

`connect_args={"server_settings": ...}`은 오타 하나로 조용히 무시될 수 있다 — asyncpg가 알 수 없는
GUC 이름을 받으면 연결 자체를 거부하지만, 이름이 맞고 값 형식만 틀리면 연결은 되고 설정만 안 먹는
경우가 있다. 그래서 값을 주장이 아니라 `SHOW`로 직접 확인하고, `lock_timeout`은 실제로 락 대기를
끊는지까지 본다 — 이것이 T-339의 hang을 막는 방어선이다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db.session import SESSION_TIMEOUT_SERVER_SETTINGS

pytestmark = pytest.mark.asyncio


async def test_server_settings_are_actually_applied(session_factory):  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        for guc, expected_ms in SESSION_TIMEOUT_SERVER_SETTINGS.items():
            # `SHOW`/`current_setting()`은 "30s"처럼 보기 좋게 단위를 바꿔 돌려준다. `pg_settings.setting`은
            # 그 정규화 이전의 원시 숫자(ms)라 값 자체를 정확히 비교할 수 있다.
            value = await db.scalar(
                text("SELECT setting FROM pg_settings WHERE name = :guc"), {"guc": guc}
            )
            assert value == expected_ms, f"{guc} 설정이 반영되지 않았다: {value!r}"


async def test_lock_timeout_fails_fast_instead_of_hanging(session_factory):  # type: ignore[no-untyped-def]
    """다른 세션이 쥔 행 락을 기다리다 `lock_timeout` 안에 실패해야 한다.

    T-339의 hang이 정확히 이 창이었다 — 이 설정이 있었다면 무기한 대기가 아니라 몇 초 안에 에러로
    끝나 재시도할 수 있었다.
    """
    import asyncio
    import uuid

    from sqlalchemy.exc import DBAPIError

    from app.models.user import User

    async with session_factory() as db:
        user = User(email=f"lock_{uuid.uuid4().hex[:8]}@pinvi.test", status="active")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.user_id

    holder = session_factory()
    await holder.execute(
        text("SELECT 1 FROM app.users WHERE user_id = :uid FOR UPDATE"), {"uid": user_id}
    )

    try:
        waiter = session_factory()
        try:
            # `wait_for`는 `lock_timeout`(30s)보다 **넉넉히 길게** 둔다 — 짧으면 DB가 먼저 끊기 전에
            # 이쪽이 먼저 타임아웃돼 `lock_timeout`이 실제로 동작하는지를 증명하지 못한다. 이 값은
            # 그 반대 실패(설정이 안 먹어 진짜로 hang하는 경우)에 대한 백스톱이다.
            with pytest.raises(DBAPIError):
                await asyncio.wait_for(
                    waiter.execute(
                        text("UPDATE app.users SET nickname = 'x' WHERE user_id = :uid"),
                        {"uid": user_id},
                    ),
                    timeout=45,
                )
        finally:
            await waiter.rollback()
            await waiter.close()
    finally:
        await holder.rollback()
        await holder.close()
