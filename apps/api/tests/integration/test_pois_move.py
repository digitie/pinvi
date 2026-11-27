"""POI 한 곳 이동 — 같은 일자 안·다른 일자로(`POST /trips/{id}/pois/{poi_id}/move`, 2026-11-27)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from tests.integration.test_pois_reorder import _add_poi
from tests.integration.test_trips_api import _create_verified_user

pytestmark = pytest.mark.asyncio


async def _make_trip(client, cookies, *, days: int = 3) -> str:  # type: ignore[no-untyped-def]
    resp = await client.post(
        "/trips",
        json={
            "title": "일자 이동 여행",
            "start_date": "2026-12-01",
            "end_date": f"2026-12-{days:02d}",
        },
        cookies=cookies,
    )
    assert resp.status_code == 201, resp.text
    trip_id: str = resp.json()["data"]["trip_id"]
    detail = await client.get(f"/trips/{trip_id}", cookies=cookies)
    assert [d["day_index"] for d in detail.json()["data"]["days"]] == list(range(1, days + 1))
    return trip_id


async def _day_orders(client, cookies, trip_id) -> dict[int, list[str]]:  # type: ignore[no-untyped-def]
    detail = await client.get(f"/trips/{trip_id}", cookies=cookies)
    assert detail.status_code == 200, detail.text
    return {
        day["day_index"]: [p["poi_id"] for p in day["pois"]]
        for day in detail.json()["data"]["days"]
    }


async def _move(  # type: ignore[no-untyped-def]
    client, cookies, trip_id, poi, *, day_index, before=None, version=None
):
    return await client.post(
        f"/trips/{trip_id}/pois/{poi['attachment_id']}/move",
        json={
            "day_index": day_index,
            "before_poi_id": before["attachment_id"] if before else None,
        },
        headers={"If-Match": str(version if version is not None else poi["version"])},
        cookies=cookies,
    )


async def _seed(client, cookies, trip_id) -> dict[str, dict[str, Any]]:  # type: ignore[no-untyped-def]
    """1일차 [a, b], 2일차 [c, d], 3일차 비어 있음."""
    return {
        "a": await _add_poi(client, cookies, trip_id, sort_order="a0", feature_id=None),
        "b": await _add_poi(client, cookies, trip_id, sort_order="a1", feature_id=None),
        "c": await _add_poi(
            client, cookies, trip_id, sort_order="a0", feature_id=None, day_index=2
        ),
        "d": await _add_poi(
            client, cookies, trip_id, sort_order="a1", feature_id=None, day_index=2
        ),
    }


def _ids(*pois: dict[str, Any]) -> list[str]:
    return [p["attachment_id"] for p in pois]


async def test_move_to_another_day_before_anchor_writes_only_the_moved_row(
    client, verified_user, auth_cookies, monkeypatch
) -> None:
    from app.api.v1 import pois as pois_router

    events: list[dict[str, Any]] = []
    monkeypatch.setattr(
        pois_router.realtime_broker,
        "publish_event_nowait",
        lambda **kwargs: events.append(kwargs),
    )
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    p = await _seed(client, cookies, trip_id)

    resp = await _move(client, cookies, trip_id, p["a"], day_index=2, before=p["d"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["from_day_index"] == 1
    assert data["poi"]["attachment_id"] == p["a"]["attachment_id"]
    assert data["poi"]["day_index"] == 2
    assert data["poi"]["version"] == 2
    # 이웃 키(c=a0, d=a1) 사이의 새 키로 옮긴 장소 한 행만 쓴다 — 다른 장소의 version은 그대로.
    assert data["poi"]["sort_order"] == "a0i"
    assert _ids(*data["changed"]) == _ids(p["a"])

    orders = await _day_orders(client, cookies, trip_id)
    assert orders[1] == _ids(p["b"])
    assert orders[2] == _ids(p["c"], p["a"], p["d"])
    assert orders[3] == []

    # 출발 일자(1일차)의 남은 장소와 도착 일자의 이웃은 손대지 않는다.
    detail = await client.get(f"/trips/{trip_id}", cookies=cookies)
    rows = {p["poi_id"]: p for day in detail.json()["data"]["days"] for p in day["pois"]}
    for key, rank in (("b", "a1"), ("c", "a0"), ("d", "a1")):
        row = rows[p[key]["attachment_id"]]
        assert (row["sort_order"], row["version"]) == (rank, 1), key

    moved_events = [
        e for e in events if e["event_type"].startswith("poi.") and e["event_type"] != "poi.created"
    ]
    assert [e["event_type"] for e in moved_events] == ["poi.moved"]
    event = moved_events[0]
    assert event["version"] == 2
    payload = event["payload"]
    assert payload["poi_id"] == p["a"]["attachment_id"]
    assert payload["from_day_index"] == 1 and payload["to_day_index"] == 2
    assert payload["before_poi_id"] == p["d"]["attachment_id"]
    assert payload["moves"] == [
        {
            "poi_id": p["a"]["attachment_id"],
            "day_index": 2,
            "new_sort_order": "a0i",
            "version": 2,
        }
    ]


async def test_move_renumbers_target_day_only_when_neighbours_leave_no_gap(
    client, verified_user, auth_cookies
) -> None:
    """클라이언트 키 `p`와 `p0` 사이에는 키가 없다 — 그때만 도착 일자를 균등 키로 다시 매긴다."""
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies, days=2)
    x = await _add_poi(client, cookies, trip_id, sort_order="p", feature_id=None, day_index=2)
    y = await _add_poi(client, cookies, trip_id, sort_order="p0", feature_id=None, day_index=2)
    z = await _add_poi(client, cookies, trip_id, sort_order="a0", feature_id=None)

    resp = await _move(client, cookies, trip_id, z, day_index=2, before=y)
    assert resp.status_code == 200, resp.text
    changed = resp.json()["data"]["changed"]
    assert [(c["attachment_id"], c["sort_order"]) for c in changed] == [
        (x["attachment_id"], "002s"),
        (z["attachment_id"], "005k"),
        (y["attachment_id"], "008c"),
    ]
    assert all(c["version"] == 2 for c in changed)
    assert (await _day_orders(client, cookies, trip_id))[2] == _ids(x, z, y)


async def test_cross_day_move_carries_poi_comments(
    client, verified_user, auth_cookies, session_factory
) -> None:
    from sqlalchemy import select

    from app.models.comment import TripComment

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    p = await _seed(client, cookies, trip_id)
    async with session_factory() as db:
        db.add(
            TripComment(
                trip_id=uuid.UUID(trip_id),
                author_user_id=uuid.UUID(user_id),
                body="이 장소 메모",
                target_type="poi",
                target_id=uuid.UUID(p["a"]["attachment_id"]),
                day_index=1,
            )
        )
        await db.commit()

    resp = await _move(client, cookies, trip_id, p["a"], day_index=3)
    assert resp.status_code == 200, resp.text
    async with session_factory() as db:
        days = (
            await db.scalars(
                select(TripComment.day_index).where(
                    TripComment.target_id == uuid.UUID(p["a"]["attachment_id"])
                )
            )
        ).all()
    assert days == [3]


async def test_move_into_empty_day_and_append_to_end(client, verified_user, auth_cookies) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    p = await _seed(client, cookies, trip_id)

    empty = await _move(client, cookies, trip_id, p["b"], day_index=3)
    assert empty.status_code == 200, empty.text
    assert empty.json()["data"]["poi"]["sort_order"] == "002s"

    append = await _move(client, cookies, trip_id, p["c"], day_index=3)
    assert append.status_code == 200, append.text
    orders = await _day_orders(client, cookies, trip_id)
    assert orders == {1: _ids(p["a"]), 2: _ids(p["d"]), 3: _ids(p["b"], p["c"])}


async def test_same_day_move_and_noop_keeps_versions(
    client, verified_user, auth_cookies, monkeypatch
) -> None:
    from app.api.v1 import pois as pois_router

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    a = await _add_poi(client, cookies, trip_id, sort_order="a0", feature_id=None)
    b = await _add_poi(client, cookies, trip_id, sort_order="a1", feature_id=None)
    c = await _add_poi(client, cookies, trip_id, sort_order="a2", feature_id=None)
    events: list[str] = []
    monkeypatch.setattr(
        pois_router.realtime_broker,
        "publish_event_nowait",
        lambda **kwargs: events.append(kwargs["event_type"]),
    )

    # 제자리(바로 다음 장소 앞) — 키가 고르지 않아도 다시 매기지 않고, 알릴 변경도 없다.
    noop = await _move(client, cookies, trip_id, b, day_index=1, before=c)
    assert noop.status_code == 200, noop.text
    assert noop.json()["data"]["changed"] == []
    assert noop.json()["data"]["poi"]["version"] == 1
    assert noop.json()["data"]["poi"]["sort_order"] == "a1"
    assert events == []

    moved = await _move(client, cookies, trip_id, c, day_index=1, before=a)
    assert moved.status_code == 200, moved.text
    assert (await _day_orders(client, cookies, trip_id))[1] == _ids(c, a, b)
    # 옮긴 c 한 행만 쓴다 — a·b는 version 1 그대로라 그 version으로 다시 옮길 수 있다.
    assert _ids(*moved.json()["data"]["changed"]) == _ids(c)

    # 두 번째 이동도 새 키 위에서 충돌 없이(#652 회귀 방지).
    to_end = await _move(client, cookies, trip_id, a, day_index=1)
    assert to_end.status_code == 200, to_end.text
    assert (await _day_orders(client, cookies, trip_id))[1] == _ids(c, b, a)


async def test_move_rejects_stale_version_and_bad_targets(
    client, verified_user, auth_cookies
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies, days=2)
    p = await _seed(client, cookies, trip_id)

    stale = await _move(client, cookies, trip_id, p["a"], day_index=2, version=7)
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"

    no_day = await _move(client, cookies, trip_id, p["a"], day_index=9)
    assert no_day.status_code == 404, no_day.text

    # 기준 장소가 도착 일자에 없다(그 사이 다른 일자로 옮겨졌거나 잘못된 요청) → 409, 아무것도 바뀌지 않음.
    wrong_anchor = await _move(client, cookies, trip_id, p["a"], day_index=2, before=p["b"])
    assert wrong_anchor.status_code == 409, wrong_anchor.text
    assert wrong_anchor.json()["error"]["code"] == "SORT_ORDER_CONFLICT"

    self_anchor = await _move(client, cookies, trip_id, p["a"], day_index=1, before=p["a"])
    assert self_anchor.status_code == 422, self_anchor.text

    bad_index = await _move(client, cookies, trip_id, p["a"], day_index=0)
    assert bad_index.status_code == 422, bad_index.text

    missing_header = await client.post(
        f"/trips/{trip_id}/pois/{p['a']['attachment_id']}/move",
        json={"day_index": 2, "before_poi_id": None},
        cookies=cookies,
    )
    assert missing_header.status_code == 422, missing_header.text

    unknown = await client.post(
        f"/trips/{trip_id}/pois/{uuid.uuid4()}/move",
        json={"day_index": 2, "before_poi_id": None},
        headers={"If-Match": "1"},
        cookies=cookies,
    )
    assert unknown.status_code == 404, unknown.text

    # 다른 여행의 장소는 옮길 수도, 기준 장소가 될 수도 없다.
    other_trip = await _make_trip(client, cookies, days=2)
    foreign = await _add_poi(client, cookies, other_trip, sort_order="a0", feature_id=None)
    foreign_move = await _move(client, cookies, trip_id, foreign, day_index=1)
    assert foreign_move.status_code == 404, foreign_move.text
    foreign_anchor = await _move(client, cookies, trip_id, p["a"], day_index=2, before=foreign)
    assert foreign_anchor.status_code == 409, foreign_anchor.text

    deleted = await client.delete(
        f"/trips/{trip_id}/pois/{p['b']['attachment_id']}", cookies=cookies
    )
    assert deleted.status_code == 204, deleted.text
    gone = await _move(client, cookies, trip_id, p["b"], day_index=2)
    assert gone.status_code == 404, gone.text
    # 지워진 장소는 기준 장소도 될 수 없다.
    gone_anchor = await _move(client, cookies, trip_id, p["c"], day_index=1, before=p["b"])
    assert gone_anchor.status_code == 409, gone_anchor.text

    assert await _day_orders(client, cookies, trip_id) == {
        1: _ids(p["a"]),
        2: _ids(p["c"], p["d"]),
    }


async def test_move_permissions_viewer_denied_editor_allowed_outsider_hidden(
    client, verified_user, auth_cookies, session_factory
) -> None:
    from app.models.companion import TripCompanion

    user_id, _ = verified_user
    owner = auth_cookies(user_id)
    trip_id = await _make_trip(client, owner, days=2)
    p = await _seed(client, owner, trip_id)
    viewer_id = await _create_verified_user(
        session_factory, f"viewer-{uuid.uuid4().hex[:6]}@pinvi.test"
    )
    editor_id = await _create_verified_user(
        session_factory, f"editor-{uuid.uuid4().hex[:6]}@pinvi.test"
    )
    outsider_id = await _create_verified_user(
        session_factory, f"outsider-{uuid.uuid4().hex[:6]}@pinvi.test"
    )
    async with session_factory() as db:
        for companion_id, role in ((viewer_id, "viewer"), (editor_id, "editor")):
            db.add(
                TripCompanion(
                    trip_id=uuid.UUID(trip_id),
                    user_id=uuid.UUID(companion_id),
                    role=role,
                    invited_at=datetime.now(UTC),
                    joined_at=datetime.now(UTC),
                )
            )
        await db.commit()

    viewer = await _move(client, auth_cookies(viewer_id), trip_id, p["a"], day_index=2)
    assert viewer.status_code == 403, viewer.text
    outsider = await _move(client, auth_cookies(outsider_id), trip_id, p["a"], day_index=2)
    assert outsider.status_code == 403, outsider.text
    assert (await _day_orders(client, owner, trip_id))[1] == _ids(p["a"], p["b"])

    editor = await _move(client, auth_cookies(editor_id), trip_id, p["a"], day_index=2)
    assert editor.status_code == 200, editor.text
    assert (await _day_orders(client, owner, trip_id))[2] == _ids(p["c"], p["d"], p["a"])


async def test_concurrent_moves_of_same_version_serialize_one_conflict(
    client, verified_user, auth_cookies, session_factory
) -> None:
    from app.services.poi import PoiVersionConflictError, get_poi, move_poi

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    p = await _seed(client, cookies, trip_id)
    poi_id = uuid.UUID(p["a"]["attachment_id"])
    trip_uuid = uuid.UUID(trip_id)

    async def attempt(day_index: int):  # type: ignore[no-untyped-def]
        async with session_factory() as db:
            row = await get_poi(db, attachment_id=poi_id, trip_id=trip_uuid)
            return await move_poi(
                db, poi=row, expected_version=1, day_index=day_index, before_poi_id=None
            )

    results = await asyncio.gather(attempt(2), attempt(3), return_exceptions=True)
    conflicts = [r for r in results if isinstance(r, PoiVersionConflictError)]
    successes = [r for r in results if not isinstance(r, BaseException)]
    assert len(conflicts) == 1 and len(successes) == 1, results
    winner = successes[0].poi.day_index
    orders = await _day_orders(client, cookies, trip_id)
    assert p["a"]["attachment_id"] in orders[winner]
    assert sum(p["a"]["attachment_id"] in ids for ids in orders.values()) == 1


async def test_concurrent_moves_into_same_day_keep_both(
    client, verified_user, auth_cookies, session_factory
) -> None:
    """서로 다른 장소를 같은 일자 같은 자리로 동시에 옮겨도 둘 다 남는다(Trip 잠금으로 직렬화)."""
    from app.services.poi import get_poi, move_poi

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    p = await _seed(client, cookies, trip_id)
    trip_uuid = uuid.UUID(trip_id)

    async def attempt(key: str):  # type: ignore[no-untyped-def]
        async with session_factory() as db:
            row = await get_poi(
                db, attachment_id=uuid.UUID(p[key]["attachment_id"]), trip_id=trip_uuid
            )
            return await move_poi(db, poi=row, expected_version=1, day_index=3, before_poi_id=None)

    await asyncio.gather(attempt("a"), attempt("c"))
    orders = await _day_orders(client, cookies, trip_id)
    assert sorted(orders[3]) == sorted(_ids(p["a"], p["c"]))
    assert orders[1] == _ids(p["b"]) and orders[2] == _ids(p["d"])
