"""trip ↔ Telegram 대상 연결 API 통합 테스트 — T-106 §6.5/6.6."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

pytestmark = pytest.mark.asyncio


async def _seed_target(session_factory: Any, *, user_id: str, chat_id: str) -> str:
    from app.models.telegram_target import TelegramTarget

    async with session_factory() as db:
        target = TelegramTarget(
            user_id=uuid.UUID(user_id),
            telegram_chat_id=chat_id,
            last_verified_at=datetime.now(UTC),
        )
        db.add(target)
        await db.commit()
        await db.refresh(target)
        return str(target.id)


async def _make_trip(client: Any, cookies: Any, title: str) -> str:
    created = await client.post("/trips", json={"title": title}, cookies=cookies)
    assert created.status_code == 201, created.text
    return created.json()["data"]["trip_id"]


async def test_link_list_unlink(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    session_factory: Any,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies, "링크 테스트 여행")
    target_id = await _seed_target(session_factory, user_id=user_id, chat_id="-100111")

    linked = await client.post(
        f"/trips/{trip_id}/telegram-targets",
        json={"telegram_target_id": target_id},
        cookies=cookies,
    )
    assert linked.status_code == 201, linked.text
    assert linked.json()["data"]["id"] == target_id

    listed = await client.get(f"/trips/{trip_id}/telegram-targets", cookies=cookies)
    assert [t["id"] for t in listed.json()["data"]] == [target_id]

    unlinked = await client.delete(
        f"/trips/{trip_id}/telegram-targets/{target_id}", cookies=cookies
    )
    assert unlinked.status_code == 204

    after = await client.get(f"/trips/{trip_id}/telegram-targets", cookies=cookies)
    assert after.json()["data"] == []


async def test_duplicate_link_conflicts(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    session_factory: Any,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies, "중복 링크")
    target_id = await _seed_target(session_factory, user_id=user_id, chat_id="-100222")

    first = await client.post(
        f"/trips/{trip_id}/telegram-targets",
        json={"telegram_target_id": target_id},
        cookies=cookies,
    )
    assert first.status_code == 201
    again = await client.post(
        f"/trips/{trip_id}/telegram-targets",
        json={"telegram_target_id": target_id},
        cookies=cookies,
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "ALREADY_LINKED"


async def test_fourth_link_exceeds_limit(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    session_factory: Any,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies, "한도 테스트")

    for i in range(3):
        tid = await _seed_target(session_factory, user_id=user_id, chat_id=f"-10033{i}")
        ok = await client.post(
            f"/trips/{trip_id}/telegram-targets",
            json={"telegram_target_id": tid},
            cookies=cookies,
        )
        assert ok.status_code == 201, ok.text

    fourth = await _seed_target(session_factory, user_id=user_id, chat_id="-100999")
    over = await client.post(
        f"/trips/{trip_id}/telegram-targets",
        json={"telegram_target_id": fourth},
        cookies=cookies,
    )
    assert over.status_code == 422
    body = over.json()["error"]
    assert body["code"] == "MAX_TARGETS_REACHED"
    assert body["reason"] == "max_targets_reached"


async def test_link_unknown_target_404(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies, "없는 타겟")
    missing = await client.post(
        f"/trips/{trip_id}/telegram-targets",
        json={"telegram_target_id": "00000000-0000-4000-8000-000000000000"},
        cookies=cookies,
    )
    assert missing.status_code == 404


async def test_other_users_trip_is_not_found(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
    session_factory: Any,
) -> None:
    from app.models.user import User

    owner_id, _ = verified_user
    owner_cookies = auth_cookies(owner_id)
    trip_id = await _make_trip(client, owner_cookies, "남의 여행")

    async with session_factory() as db:
        other = User(
            email="other@example.com",
            password_hash="x",
            nickname="타인",
            status="active",
            roles=["user"],
            email_verified_at=datetime.now(UTC),
        )
        db.add(other)
        await db.commit()
        await db.refresh(other)
        other_id = str(other.user_id)
    other_target = await _seed_target(session_factory, user_id=other_id, chat_id="-100444")

    # 다른 사용자가 owner의 trip에 연결 시도 → 소유자 아님 → 404(존재 숨김 아님, 여기선 owner-only 403/404).
    resp = await client.post(
        f"/trips/{trip_id}/telegram-targets",
        json={"telegram_target_id": other_target},
        cookies=auth_cookies(other_id),
    )
    assert resp.status_code in (403, 404)
