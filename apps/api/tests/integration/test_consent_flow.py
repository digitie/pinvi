"""4 분리 동의 흐름 통합 — record / list / withdraw + 부작용 (SPRINT-2 DoD)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

FOUR_CONSENTS = [
    {"consent_type": "tos", "version": "2026-01"},
    {"consent_type": "privacy", "version": "2026-01"},
    {"consent_type": "lbs_tos", "version": "2026-01"},
    {"consent_type": "location_collection", "version": "2026-01"},
]


async def test_record_four_consents(client, verified_user, auth_cookies) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)

    resp = await client.put("/users/me/consents", json=FOUR_CONSENTS, cookies=cookies)
    assert resp.status_code == 200, resp.text
    recorded = {c["consent_type"] for c in resp.json()["data"]}
    assert recorded == {"tos", "privacy", "lbs_tos", "location_collection"}

    got = await client.get("/users/me/consents", cookies=cookies)
    assert got.status_code == 200
    assert len(got.json()["data"]) == 4


async def test_record_is_idempotent(client, verified_user, auth_cookies) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    await client.put("/users/me/consents", json=FOUR_CONSENTS, cookies=cookies)
    # 같은 동의 재기록 → 중복 행 생기지 않음
    await client.put("/users/me/consents", json=FOUR_CONSENTS, cookies=cookies)
    got = await client.get("/users/me/consents", cookies=cookies)
    assert len(got.json()["data"]) == 4


async def test_withdraw_consent(client, verified_user, auth_cookies) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    await client.put("/users/me/consents", json=FOUR_CONSENTS, cookies=cookies)

    resp = await client.delete("/users/me/consents/location_collection", cookies=cookies)
    assert resp.status_code == 204

    got = await client.get("/users/me/consents", cookies=cookies)
    by_type = {c["consent_type"]: c for c in got.json()["data"]}
    assert by_type["location_collection"]["withdrawn_at"] is not None


async def test_withdraw_demographic_clears_fields(
    client, verified_user, auth_cookies, session_factory
) -> None:
    """demographic_use 철회 → 인구통계 컬럼 NULL 부작용."""
    import uuid

    from sqlalchemy import select

    from app.models.user import User

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)

    # 인구통계 정보 + 동의 기록
    async with session_factory() as db:
        user = await db.scalar(select(User).where(User.user_id == uuid.UUID(user_id)))
        assert user is not None
        user.gender = "female"
        user.birth_year_month = "199001"
        user.residence_sigungu_code = "11110"
        await db.commit()

    await client.put(
        "/users/me/consents",
        json=[{"consent_type": "demographic_use", "version": "2026-01"}],
        cookies=cookies,
    )
    resp = await client.delete("/users/me/consents/demographic_use", cookies=cookies)
    assert resp.status_code == 204

    async with session_factory() as db:
        user = await db.scalar(select(User).where(User.user_id == uuid.UUID(user_id)))
        assert user is not None
        assert user.gender is None
        assert user.birth_year_month is None
        assert user.residence_sigungu_code is None


async def test_invalid_consent_type_rejected(client, verified_user, auth_cookies) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    resp = await client.put(
        "/users/me/consents",
        json=[{"consent_type": "not_a_real_consent", "version": "2026-01"}],
        cookies=cookies,
    )
    assert resp.status_code == 422
