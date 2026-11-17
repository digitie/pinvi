"""장소 시도 역지오코딩(`services/poi_region`) — 순수 판정과 geo 장애 처리."""

from __future__ import annotations

from typing import Any

import pytest

from app.clients.kor_travel_geo import KorTravelGeoBadRequest, KorTravelGeoUnavailable
from app.services.korea_regions import sido_from_snapshot
from app.services.poi_region import (
    Coord,
    carry_geo_region,
    lookup_region,
    needs_region_lookup,
    region_from_reverse,
    snapshot_coord,
)

GANGNEUNG = {"lon": 128.9, "lat": 37.8}


class FakeGeo:
    def __init__(self, result: dict[str, Any] | Exception) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def reverse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_snapshot_coord_requires_numeric_korean_coordinates() -> None:
    assert snapshot_coord({"coord": GANGNEUNG}) == Coord(128.9, 37.8)
    assert snapshot_coord({"coord": {"lon": "128.9", "lat": 37.8}}) is None
    assert snapshot_coord({"coord": {"lon": True, "lat": 37.8}}) is None
    assert snapshot_coord({"coord": {"lon": -73.9, "lat": 40.7}}) is None  # 한국 밖
    assert snapshot_coord({}) is None
    assert snapshot_coord(None) is None


def test_needs_region_lookup_only_for_coordinate_only_snapshots() -> None:
    assert needs_region_lookup({"name": "경포해변", "coord": GANGNEUNG})
    # 이미 시도를 정할 수 있다 — 코드·주소가 있으면 묻지 않는다.
    assert not needs_region_lookup({"coord": GANGNEUNG, "region": {"sig_cd": "51150"}})
    assert not needs_region_lookup({"coord": GANGNEUNG, "address": {"label": "강원 강릉시"}})
    # 한 번 물었으면(찾음·못 찾음 모두) 다시 묻지 않는다.
    assert not needs_region_lookup({"coord": GANGNEUNG, "geo_region": {"status": "not_found"}})
    assert not needs_region_lookup({"name": "좌표 없음"})


def test_region_from_reverse_reads_first_region_with_a_sido() -> None:
    payload = {
        "candidates": [
            {"region": {"region_name": "코드 없음"}},
            {"region": {"sig_cd": "42150", "sido": "강원도", "sigungu": "강릉시"}},
        ]
    }
    # 옛 강원 코드(42)는 강원특별자치도(51)로 접는다. 시군구 코드는 받은 그대로 둔다.
    assert region_from_reverse(payload) == {
        "status": "found",
        "sido_code": "51",
        "sig_cd": "42150",
        "sido": "강원도",
        "sigungu": "강릉시",
    }
    assert region_from_reverse({"candidates": [{"region": {"bjd_cd": "1111010100"}}]}) == {
        "status": "found",
        "sido_code": "11",
    }
    assert region_from_reverse({"candidates": []}) is None
    assert region_from_reverse({"status": "ok"}) is None


def test_found_region_is_readable_by_home_aggregation() -> None:
    snapshot = {"coord": GANGNEUNG, "geo_region": {"status": "found", "sido_code": "51"}}
    assert sido_from_snapshot(snapshot) == "51"


@pytest.mark.asyncio
async def test_lookup_region_outcomes() -> None:
    found = FakeGeo({"candidates": [{"region": {"sig_cd": "51150"}}]})
    assert await lookup_region(found, Coord(128.9, 37.8), max_attempts=1) == {
        "status": "found",
        "sido_code": "51",
        "sig_cd": "51150",
    }
    assert found.calls[0]["include_region"] is True and found.calls[0]["max_attempts"] == 1
    # 행정구역 밖(바다 등)은 '못 찾음'으로 남겨 다시 묻지 않는다.
    assert await lookup_region(FakeGeo({"candidates": []}), Coord(128.9, 37.8)) == {
        "status": "not_found"
    }
    # 장애·4xx는 아무것도 쓰지 않는다(다음 백필이 다시 묻는다).
    assert await lookup_region(FakeGeo(KorTravelGeoUnavailable("down")), Coord(128.9, 37.8)) is None
    assert await lookup_region(FakeGeo(KorTravelGeoBadRequest("400")), Coord(128.9, 37.8)) is None


def test_carry_geo_region_follows_the_coordinate() -> None:
    region = {"status": "found", "sido_code": "51"}
    old = {"name": "a", "coord": GANGNEUNG, "geo_region": region}
    # 좌표가 같으면 클라이언트가 키를 빠뜨려도 이어 쓴다.
    assert carry_geo_region(old, {"name": "b", "coord": GANGNEUNG})["geo_region"] == region
    # 좌표가 바뀌면 옛 시도를 지운다(클라이언트가 그대로 보내도).
    moved = carry_geo_region(old, {"coord": {"lon": 129.2, "lat": 35.1}, "geo_region": region})
    assert "geo_region" not in moved
