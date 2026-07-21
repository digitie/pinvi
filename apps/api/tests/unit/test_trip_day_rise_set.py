"""`app.services.trip_day_rise_set` 단위 테스트 — 기준 좌표 해석(ADR-055 §6)."""

from __future__ import annotations

import uuid
from typing import Any

from app.models.poi import TripDayPoi
from app.services.trip_day_rise_set import resolve_day_reference


def _poi(name: str, lon: float | None, lat: float | None) -> TripDayPoi:
    snapshot: dict[str, Any] = {"name": name}
    if lon is not None and lat is not None:
        snapshot["coord"] = {"lon": lon, "lat": lat}
    poi = TripDayPoi(
        attachment_id=uuid.uuid4(),
        trip_id=uuid.uuid4(),
        day_index=1,
        sort_order="a0",
        feature_snapshot=snapshot,
        added_by_user_id=uuid.uuid4(),
        currency="KRW",
    )
    return poi


def test_reference_is_centroid_with_earliest_as_label() -> None:
    # 입력은 (created_at, attachment_id) 정렬 가정 — 첫 POI가 대표.
    pois = [_poi("첫 장소", 129.0, 35.0), _poi("둘째 장소", 129.2, 35.2)]
    ref = resolve_day_reference(pois)
    assert ref is not None
    assert round(ref.longitude, 3) == 129.1  # centroid
    assert round(ref.latitude, 3) == 35.1
    assert ref.reference_poi_id == pois[0].attachment_id  # earliest = 대표
    assert ref.reference_label == "첫 장소"


def test_reference_skips_coordless_pois_for_centroid() -> None:
    pois = [_poi("좌표없음", None, None), _poi("좌표있음", 129.3, 35.3)]
    ref = resolve_day_reference(pois)
    assert ref is not None
    assert round(ref.longitude, 3) == 129.3  # 좌표 있는 것만 centroid
    assert ref.reference_label == "좌표있음"  # 대표 = 좌표 있는 것 중 earliest


def test_reference_none_when_no_coords() -> None:
    assert resolve_day_reference([_poi("메모만", None, None)]) is None
    assert resolve_day_reference([]) is None
