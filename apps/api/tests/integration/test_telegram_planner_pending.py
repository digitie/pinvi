"""예약 planner 할 일 점검 — Dagster가 매분 빈 run을 띄우지 않게 하는 읽기 전용 경계.

점검은 planner 조건의 상위집합이어야 한다: planner가 적재하는 분에는 반드시 due이고,
적재가 끝나 발생키가 생기면 다시 due가 아니어야 run이 줄어든다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.models.telegram_notification import TelegramPreferences
from app.models.telegram_target import TelegramTarget
from app.models.trip_telegram_target import TripTelegramTarget
from app.models.user import User

pytestmark = pytest.mark.asyncio

PREFERENCES = "/users/me/telegram-notification-preferences"
PENDING = "/internal/telegram/plan/pending"
KEY = "owned-planner-test-key"
# 한국 2026-11-05(목) 08:00 = UTC 11-04 23:00.
KST_0800_NOV5 = datetime(2026, 11, 4, 23, 0, tzinfo=UTC)


async def _trip_with_target(
    client: Any, user_id: str, cookies: Any, session_factory: Any, *, link: bool = True
) -> tuple[str, str]:
    response = await client.post(
        "/trips",
        json={"title": "부산 점검", "start_date": "2026-11-05", "end_date": "2026-11-06"},
        cookies=cookies,
    )
    assert response.status_code == 201, response.text
    trip_id = response.json()["data"]["trip_id"]
    async with session_factory() as db:
        target = TelegramTarget(
            user_id=uuid.UUID(user_id),
            telegram_chat_id="-100700",
            last_verified_at=datetime.now(UTC),
        )
        db.add(target)
        await db.flush()
        if link:
            db.add(TripTelegramTarget(trip_id=uuid.UUID(trip_id), telegram_target_id=target.id))
        await db.commit()
        return trip_id, str(target.id)


async def test_no_opt_in_means_nothing_pending(session_factory: Any) -> None:
    from app.services.telegram_planner import pending_work

    result = await pending_work(now=KST_0800_NOV5)
    assert result == {"due": False, "users": 0, "weather": 0, "daily": 0, "weekly": 0}


async def test_daily_and_weekly_pending_follow_send_time_and_clear_after_planning(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any
) -> None:
    from app.services.telegram_planner import pending_work, plan_due

    user_id = verified_user[0]
    cookies = auth_cookies(user_id)
    _, target_id = await _trip_with_target(client, user_id, cookies, session_factory)
    body = {
        "daily_enabled": True,
        "weekly_enabled": True,
        "weekly_target_id": target_id,
        "weekly_day": 3,
        "send_time": "08:00",
    }
    assert (await client.put(PREFERENCES, json=body, cookies=cookies)).status_code == 200

    # send_time 1분 전: planner도 아무것도 만들지 않는다.
    before = KST_0800_NOV5 - timedelta(minutes=1)
    assert (await pending_work(now=before))["due"] is False
    assert (await plan_due(now=before))["enqueued"] == 0

    pending = await pending_work(now=KST_0800_NOV5)
    assert pending == {"due": True, "users": 1, "weather": 0, "daily": 1, "weekly": 1}
    planned = await plan_due(now=KST_0800_NOV5)
    assert planned["enqueued"] == 3  # 오늘·내일 일간 2 + 주간 1

    # 발생키가 생겼으니 같은 날 남은 분에는 run을 띄우지 않는다.
    after = await pending_work(now=KST_0800_NOV5 + timedelta(minutes=1))
    assert after["due"] is False and after["users"] == 1
    assert (await plan_due(now=KST_0800_NOV5 + timedelta(minutes=1)))["enqueued"] == 0


async def test_daily_without_linked_target_is_not_pending(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any
) -> None:
    from app.services.telegram_planner import pending_work, plan_due

    user_id = verified_user[0]
    cookies = auth_cookies(user_id)
    await _trip_with_target(client, user_id, cookies, session_factory, link=False)
    body = {"daily_enabled": True, "send_time": "08:00"}
    assert (await client.put(PREFERENCES, json=body, cookies=cookies)).status_code == 200
    assert (await pending_work(now=KST_0800_NOV5))["due"] is False
    assert (await plan_due(now=KST_0800_NOV5))["enqueued"] == 0


async def test_weather_pending_only_while_a_trip_is_in_progress(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any
) -> None:
    from app.services.telegram_planner import pending_work

    user_id = verified_user[0]
    cookies = auth_cookies(user_id)
    await _trip_with_target(client, user_id, cookies, session_factory)
    body = {"weather_enabled": True, "send_time": "23:59"}
    assert (await client.put(PREFERENCES, json=body, cookies=cookies)).status_code == 200

    # 여행 전날(KST 11-04)에는 특보 대상 여행이 없다.
    assert (await pending_work(now=KST_0800_NOV5 - timedelta(days=1)))["due"] is False
    # 여행 기간에는 새 발표 여부를 weather에 물어야 하므로 매분 대상이다.
    during = await pending_work(now=KST_0800_NOV5)
    assert during["due"] is True and during["weather"] == 1
    # 여행 종료 다음 날(KST 11-07)에는 다시 대상이 아니다.
    assert (await pending_work(now=KST_0800_NOV5 + timedelta(days=2)))["due"] is False


async def test_inactive_user_is_not_pending(
    client: Any, verified_user: Any, auth_cookies: Any, session_factory: Any
) -> None:
    from app.services.telegram_planner import pending_work

    user_id = verified_user[0]
    cookies = auth_cookies(user_id)
    await _trip_with_target(client, user_id, cookies, session_factory)
    body = {"weather_enabled": True, "daily_enabled": True, "send_time": "08:00"}
    assert (await client.put(PREFERENCES, json=body, cookies=cookies)).status_code == 200
    assert (await pending_work(now=KST_0800_NOV5))["due"] is True
    async with session_factory() as db:
        user = await db.get(User, uuid.UUID(user_id))
        assert user is not None
        user.deleted_at = datetime.now(UTC)
        await db.commit()
        assert await db.scalar(select(TelegramPreferences.user_id)) is not None
    result = await pending_work(now=KST_0800_NOV5)
    assert result["due"] is False and result["users"] == 1


async def test_pending_route_uses_the_planner_key_only(
    client: Any, verified_user: Any, auth_cookies: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "pinvi_telegram_planner_key", KEY)
    cookies = auth_cookies(verified_user[0])
    assert (await client.get(PENDING, cookies=cookies)).status_code == 404
    assert (
        await client.get(PENDING, headers={"X-Pinvi-Notification-Planner-Key": "wrong"})
    ).status_code == 404
    good = await client.get(PENDING, headers={"X-Pinvi-Notification-Planner-Key": KEY})
    assert good.status_code == 200
    assert good.json()["data"] == {
        "due": False,
        "users": 0,
        "weather": 0,
        "daily": 0,
        "weekly": 0,
    }
