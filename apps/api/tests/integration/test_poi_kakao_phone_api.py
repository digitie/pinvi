"""`GET /trips/{trip_id}/pois/{poi_id}/place-details/kakao-phone` — Kakao 전화 라이브 조회(미저장).

- 확실히 맞는 Kakao 장소(이름·300 m)의 전화와 카카오맵 back-link만 돌려준다.
- 저장된 전화(공공데이터)가 있으면 Kakao를 부르지 않는다.
- 결과를 DB에 쓰지 않고 메모리 캐시만 쓴다. 장애는 조용히 `matched=false`이고 캐시하지 않는다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select

from app.clients.kakao_local import KakaoLocalUnavailable, get_kakao_local_client
from app.main import app
from app.models.poi_place_detail import TripPoiPlaceDetail
from app.services.poi_kakao_phone import clear_cache
from tests.integration.test_pois_reorder import _make_trip

pytestmark = pytest.mark.asyncio

_LAT, _LON = 36.5397, 128.5181


class _FakeKakao:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents
        self.calls: list[dict[str, Any]] = []
        self.fail = False

    async def search_keyword(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.fail:
            raise KakaoLocalUnavailable("down")
        return {"documents": self.documents}


def _doc(name: str, *, lat: float = _LAT, lon: float = _LON) -> dict[str, Any]:
    return {
        "id": "8146617",
        "place_name": name,
        "x": str(lon),
        "y": str(lat),
        "phone": "054-852-3588",
        "place_url": "http://place.map.kakao.com/8146617",
        "address_name": "경북 안동시 풍천면 하회리",
    }


@pytest.fixture(autouse=True)
def _reset_cache() -> Any:
    clear_cache()
    yield
    clear_cache()
    app.dependency_overrides.pop(get_kakao_local_client, None)


async def _add_poi(client: Any, cookies: Any, trip_id: str, **body: Any) -> dict[str, Any]:
    resp = await client.post(
        f"/trips/{trip_id}/pois",
        json={
            "day_index": 1,
            "sort_order": body.pop("sort_order", "a0"),
            "feature_snapshot": {"name": "안동하회마을", "coord": {"lon": _LON, "lat": _LAT}},
            **body,
        },
        cookies=cookies,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_live_phone_matches_caches_in_memory_and_never_persists(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, session_factory: Any
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    poi = await _add_poi(client, cookies, trip_id, feature_id=None, source="manual")
    kakao = _FakeKakao([_doc("하회마을 주차장", lat=36.6), _doc("안동하회마을")])
    app.dependency_overrides[get_kakao_local_client] = lambda: kakao
    url = f"/trips/{trip_id}/pois/{poi['attachment_id']}/place-details/kakao-phone"

    first = await client.get(url, cookies=cookies)
    second = await client.get(url, cookies=cookies)

    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert data["provider"] == "kakao"
    assert data["matched"] is True
    assert data["phone"] == "054-852-3588"
    assert data["provider_url"].startswith("http")
    assert second.json()["data"] == data
    assert len(kakao.calls) == 1  # 두 번째는 메모리 캐시
    assert kakao.calls[0]["query"] == "안동하회마을"
    async with session_factory() as db:
        count = await db.scalar(select(func.count()).select_from(TripPoiPlaceDetail))
    assert count == 0  # 저장하지 않는다


async def test_stored_phone_skips_kakao_and_far_or_failed_results_are_unmatched(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, session_factory: Any
) -> None:
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    stored = await _add_poi(client, cookies, trip_id, feature_id=None, source="manual")
    async with session_factory() as db:
        db.add(
            TripPoiPlaceDetail(
                poi_id=uuid.UUID(stored["attachment_id"]),
                status="ready",
                opening_hours=[],
                phone="054-853-0109",
                sources={"phone": "kor_travel_map"},
                fetched_at=datetime.now(UTC),
            )
        )
        await db.commit()
    far = await _add_poi(
        client,
        cookies,
        trip_id,
        feature_id=None,
        source="manual",
        sort_order="a1",
        feature_snapshot={"name": "안동하회마을", "coord": {"lon": 127.0, "lat": 37.5}},
    )
    kakao = _FakeKakao([_doc("안동하회마을")])
    app.dependency_overrides[get_kakao_local_client] = lambda: kakao
    base = f"/trips/{trip_id}/pois"

    skipped = await client.get(
        f"{base}/{stored['attachment_id']}/place-details/kakao-phone", cookies=cookies
    )
    assert skipped.json()["data"]["matched"] is False
    assert kakao.calls == []

    too_far = await client.get(
        f"{base}/{far['attachment_id']}/place-details/kakao-phone", cookies=cookies
    )
    assert too_far.json()["data"]["matched"] is False
    assert too_far.json()["data"]["phone"] is None

    clear_cache()
    kakao.fail = True
    failed = await client.get(
        f"{base}/{far['attachment_id']}/place-details/kakao-phone", cookies=cookies
    )
    assert failed.status_code == 200
    assert failed.json()["data"]["matched"] is False
    kakao.fail = False
    kakao.documents = [_doc("안동하회마을", lat=37.5, lon=127.0)]
    recovered = await client.get(
        f"{base}/{far['attachment_id']}/place-details/kakao-phone", cookies=cookies
    )
    assert recovered.json()["data"]["matched"] is True  # 장애는 캐시하지 않았다


async def test_live_phone_requires_membership(
    client: Any, verified_user: tuple[str, str], auth_cookies: Any, session_factory: Any
) -> None:
    from app.models.user import User

    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    trip_id = await _make_trip(client, cookies)
    poi = await _add_poi(client, cookies, trip_id, feature_id=None, source="manual")
    async with session_factory() as db:
        stranger = User(
            email=f"stranger_{uuid.uuid4().hex[:8]}@pinvi.test",
            password_hash=None,
            nickname="남",
            status="active",
            email_verified_at=datetime.now(UTC),
        )
        db.add(stranger)
        await db.commit()
        await db.refresh(stranger)
    kakao = _FakeKakao([_doc("안동하회마을")])
    app.dependency_overrides[get_kakao_local_client] = lambda: kakao
    resp = await client.get(
        f"/trips/{trip_id}/pois/{poi['attachment_id']}/place-details/kakao-phone",
        cookies=auth_cookies(str(stranger.user_id)),
    )
    assert resp.status_code == 403
    assert kakao.calls == []
