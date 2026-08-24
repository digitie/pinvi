"""4 분리 동의 흐름 통합 — record / list / withdraw + 부작용 (SPRINT-2 DoD)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

FOUR_CONSENTS = [
    {"consent_type": "tos", "version": "v1.0"},
    {"consent_type": "privacy", "version": "v1.0"},
    {"consent_type": "lbs_tos", "version": "v1.0"},
    {"consent_type": "location_collection", "version": "v1.0"},
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
        json=[{"consent_type": "demographic_use", "version": "v1.0"}],
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
        json=[{"consent_type": "not_a_real_consent", "version": "v1.0"}],
        cookies=cookies,
    )
    assert resp.status_code == 422


async def _events(session_factory, user_id, consent_type):  # type: ignore[no-untyped-def]
    """해당 동의의 이벤트 이력을 시간순으로 돌려준다."""
    import uuid as _uuid

    from sqlalchemy import select

    from app.models.user_consent_event import UserConsentEvent

    async with session_factory() as db:
        rows = list(
            (
                await db.execute(
                    select(UserConsentEvent)
                    .where(
                        UserConsentEvent.user_id == _uuid.UUID(str(user_id)),
                        UserConsentEvent.consent_type == consent_type,
                    )
                    .order_by(UserConsentEvent.occurred_at, UserConsentEvent.event)
                )
            ).scalars()
        )
    return [(row.event, row.source) for row in rows]


async def test_withdrawal_history_survives_reconsent(  # type: ignore[no-untyped-def]
    client, verified_user, auth_cookies, session_factory
) -> None:
    """철회 후 재동의해도 **철회 사실이 남는다** (T-326).

    현재 상태 row는 type+version당 하나라 재동의가 그 row를 되살린다. 그래서
    `docs/legal/terms-of-service.md` 제4조가 고지하는 "시점·버전과 함께 기록된 동의 이력"은
    이벤트 테이블이 없으면 성립하지 않는다.
    """
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    item = [{"consent_type": "location_collection", "version": "v1.0"}]

    await client.put("/users/me/consents", json=item, cookies=cookies)
    assert await _events(session_factory, user_id, "location_collection") == [
        ("agreed", "settings")
    ]

    resp = await client.delete("/users/me/consents/location_collection", cookies=cookies)
    assert resp.status_code == 204, resp.text

    # 재동의 — 현재 상태 row는 되살아나지만 이력은 세 사건을 모두 갖는다.
    await client.put("/users/me/consents", json=item, cookies=cookies)
    assert await _events(session_factory, user_id, "location_collection") == [
        ("agreed", "settings"),
        ("withdrawn", "settings"),
        ("agreed", "settings"),
    ]

    got = await client.get("/users/me/consents", cookies=cookies)
    rows = [c for c in got.json()["data"] if c["consent_type"] == "location_collection"]
    assert len(rows) == 1
    assert rows[0]["withdrawn_at"] is None


async def test_repeated_consent_does_not_rewrite_agreed_at(  # type: ignore[no-untyped-def]
    client, verified_user, auth_cookies, session_factory
) -> None:
    """이미 유효한 동의를 다시 PUT해도 시점이 바뀌지 않고 이벤트도 늘지 않는다 (T-326).

    예전에는 매 PUT이 `agreed_at`을 현재 시각으로 덮어써, 가입 때 받은 동의가 방금 받은 것처럼
    보였다 — 동의 시점이 법적 증빙이므로 조용히 갱신되면 안 된다.
    """
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    item = [{"consent_type": "marketing", "version": "v1.0"}]

    first = await client.put("/users/me/consents", json=item, cookies=cookies)
    agreed_at = next(c for c in first.json()["data"] if c["consent_type"] == "marketing")[
        "agreed_at"
    ]

    second = await client.put("/users/me/consents", json=item, cookies=cookies)
    again = next(c for c in second.json()["data"] if c["consent_type"] == "marketing")["agreed_at"]

    assert again == agreed_at
    assert await _events(session_factory, user_id, "marketing") == [("agreed", "settings")]


async def test_unknown_consent_version_is_rejected(client, verified_user, auth_cookies) -> None:  # type: ignore[no-untyped-def]
    """서버가 약관 버전 정본을 갖는다 (T-327).

    허용 목록 대조가 없으면 "무엇에 동의했는가"라는 법적 증빙이 클라이언트 입력에 달린다.
    """
    user_id, _ = verified_user
    resp = await client.put(
        "/users/me/consents",
        json=[{"consent_type": "marketing", "version": "made-up-9.9"}],
        cookies=auth_cookies(user_id),
    )
    assert resp.status_code == 422, resp.text


async def test_nearby_requires_location_consent(client, verified_user, auth_cookies) -> None:  # type: ignore[no-untyped-def]
    """동의 없이 좌표를 받지 않는다 (T-327).

    `docs/api/users.md` §3.3의 "`location_collection` 철회 → 사용자 좌표 응답 차단"이 지금까지
    미구현이라, 클라이언트를 우회하면 철회한 사용자의 좌표도 서버가 그대로 받았다.
    """
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    params = {"lon": 126.978, "lat": 37.5665, "radius_m": 1000}

    denied = await client.get("/features/nearby", params=params, cookies=cookies)
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "LOCATION_CONSENT_REQUIRED"

    # 두 동의가 모두 있어야 통과한다 — 하나만으로는 열리지 않는다.
    await client.put(
        "/users/me/consents",
        json=[{"consent_type": "lbs_tos", "version": "v1.0"}],
        cookies=cookies,
    )
    still_denied = await client.get("/features/nearby", params=params, cookies=cookies)
    assert still_denied.status_code == 403, still_denied.text

    await client.put(
        "/users/me/consents",
        json=[{"consent_type": "location_collection", "version": "v1.0"}],
        cookies=cookies,
    )
    allowed = await client.get("/features/nearby", params=params, cookies=cookies)
    assert allowed.status_code != 403, allowed.text

    # 철회하면 다음 요청부터 다시 막힌다(`user-location.md` §2).
    await client.delete("/users/me/consents/location_collection", cookies=cookies)
    after_withdraw = await client.get("/features/nearby", params=params, cookies=cookies)
    assert after_withdraw.status_code == 403, after_withdraw.text


async def test_keyword_search_works_without_location_consent(  # type: ignore[no-untyped-def]
    client, verified_user, auth_cookies
) -> None:
    """좌표 없는 키워드 검색은 동의와 무관하다 (T-327).

    `/search`를 dependency로 걸면 이 경로까지 막힌다 — near-me 분기 안에서만 검사하는 이유다.
    """
    user_id, _ = verified_user
    resp = await client.get("/search", params={"q": "광안리"}, cookies=auth_cookies(user_id))
    assert resp.status_code != 403, resp.text
