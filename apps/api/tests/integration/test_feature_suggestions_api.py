"""사용자 feature 제안 큐 API 통합 테스트."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select

from app.models.feature_suggestion import FeatureSuggestion
from app.models.user import User

pytestmark = pytest.mark.asyncio

FEATURE_SUGGESTION_DAILY_LIMIT = 20


async def _create_user(session_factory, *, email_prefix: str) -> str:  # type: ignore[no-untyped-def]
    async with session_factory() as db:
        user = User(
            email=f"{email_prefix}_{uuid.uuid4().hex[:8]}@tripmate.test",
            password_hash=None,
            nickname="제안 사용자",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return str(user.user_id)


async def test_user_creates_and_reads_feature_suggestion(
    client: Any,
    session_factory: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
) -> None:
    user_id, _email = verified_user
    body = {
        "kind": "place",
        "title": "  새 카페  ",
        "coord": {"longitude": 127.1234564, "latitude": 37.1234564},
        "categories": ["카페", "카페", "  디저트  "],
        "note": "입구가 골목 안쪽에 있어요.",
    }

    resp = await client.post(
        "/features/requests",
        json=body,
        cookies=auth_cookies(user_id),
    )

    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["status"] == "pending"
    assert data["title"] == "새 카페"
    assert data["categories"] == ["카페", "디저트"]
    assert data["coord"] == {"longitude": 127.123456, "latitude": 37.123456}

    request_id = uuid.UUID(data["request_id"])
    async with session_factory() as db:
        row = await db.scalar(
            select(FeatureSuggestion).where(FeatureSuggestion.request_id == request_id)
        )
        assert row is not None
        assert row.requester_user_id == uuid.UUID(user_id)
        assert row.name == "새 카페"
        assert row.status == "pending"

    detail = await client.get(
        f"/features/requests/{request_id}",
        cookies=auth_cookies(user_id),
    )

    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["request_id"] == str(request_id)


async def test_feature_suggestion_detail_is_owner_only(
    client: Any,
    session_factory: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
) -> None:
    owner_id, _email = verified_user
    other_id = await _create_user(session_factory, email_prefix="feature_request_other")

    create = await client.post(
        "/features/requests",
        json={
            "kind": "event",
            "title": "동네 축제",
            "coord": {"longitude": 126.9, "latitude": 37.4},
        },
        cookies=auth_cookies(owner_id),
    )
    assert create.status_code == 201, create.text
    request_id = create.json()["data"]["request_id"]

    denied = await client.get(
        f"/features/requests/{request_id}",
        cookies=auth_cookies(other_id),
    )

    assert denied.status_code == 404


async def test_duplicate_feature_suggestion_returns_existing_row(
    client: Any,
    session_factory: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
) -> None:
    user_id, _email = verified_user
    body = {
        "kind": "place",
        "title": "해변 전망대",
        "coord": {"longitude": 129.118, "latitude": 35.155},
    }

    first = await client.post("/features/requests", json=body, cookies=auth_cookies(user_id))
    second = await client.post(
        "/features/requests",
        json={**body, "title": "  해변 전망대  ", "note": "중복 후보"},
        cookies=auth_cookies(user_id),
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json()["data"]["request_id"] == first.json()["data"]["request_id"]

    async with session_factory() as db:
        count = await db.scalar(select(func.count(FeatureSuggestion.request_id)))
    assert count == 1


async def test_feature_suggestion_rate_limit(
    client: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
) -> None:
    user_id, _email = verified_user
    for i in range(FEATURE_SUGGESTION_DAILY_LIMIT):
        resp = await client.post(
            "/features/requests",
            json={
                "kind": "place",
                "title": f"제안 장소 {i}",
                "coord": {"longitude": 127.0 + i * 0.0001, "latitude": 37.5},
            },
            cookies=auth_cookies(user_id),
        )
        assert resp.status_code == 201, resp.text

    limited = await client.post(
        "/features/requests",
        json={
            "kind": "place",
            "title": "제한 초과 장소",
            "coord": {"longitude": 128.0, "latitude": 37.5},
        },
        cookies=auth_cookies(user_id),
    )

    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "86400"


async def test_correction_suggestion_requires_target_and_dedup_separates_type(
    client: Any,
    session_factory: Any,
    verified_user: tuple[str, str],
    auth_cookies: Any,
) -> None:
    user_id, _email = verified_user
    base = {
        "kind": "place",
        "title": "정보 수정 요청",
        "coord": {"longitude": 127.5, "latitude": 37.5},
    }

    # correction인데 target_feature_id 누락 → 422
    missing = await client.post(
        "/features/requests",
        json={**base, "type": "correction"},
        cookies=auth_cookies(user_id),
    )
    assert missing.status_code == 422, missing.text

    # new_place인데 target_feature_id 지정 → 422
    forbidden = await client.post(
        "/features/requests",
        json={**base, "type": "new_place", "target_feature_id": "place:abc"},
        cookies=auth_cookies(user_id),
    )
    assert forbidden.status_code == 422, forbidden.text

    # correction + target → 201, 응답에 type/target_feature_id 노출
    created = await client.post(
        "/features/requests",
        json={**base, "type": "correction", "target_feature_id": "place:abc123"},
        cookies=auth_cookies(user_id),
    )
    assert created.status_code == 201, created.text
    correction = created.json()["data"]
    assert correction["type"] == "correction"
    assert correction["target_feature_id"] == "place:abc123"

    # 같은 이름/좌표라도 new_place는 correction과 별개로 등록(dedup이 type/target을 구분).
    new_place = await client.post(
        "/features/requests",
        json={**base, "type": "new_place"},
        cookies=auth_cookies(user_id),
    )
    assert new_place.status_code == 201, new_place.text
    assert new_place.json()["data"]["type"] == "new_place"
    assert new_place.json()["data"]["request_id"] != correction["request_id"]
