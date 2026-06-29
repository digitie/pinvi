"""T-261/T-262: nearest-neighbor seed + 2-opt 동선 최적화 단위 테스트."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.services.trip import (
    _optimize_day_order,
    _path_distance_m,
    _two_opt_improve,
)


def _poi(lon: float, lat: float) -> SimpleNamespace:
    return SimpleNamespace(
        attachment_id=uuid.uuid4(),
        feature_snapshot={"coord": {"lon": lon, "lat": lat}},
        sort_order="a0",
    )


def test_two_opt_uncrosses_a_bad_order() -> None:
    # lon 0,1,2,3 (lat 0) — 최적 open path는 정렬 순서다.
    pois = [_poi(0, 0), _poi(1, 0), _poi(2, 0), _poi(3, 0)]
    coord_by_id = {p.attachment_id: (float(i), 0.0) for i, p in enumerate(pois)}
    bad = [pois[0], pois[2], pois[1], pois[3]]  # 0→2→1→3 (교차)
    bad_dist = _path_distance_m(bad, coord_by_id)

    improved = _two_opt_improve(bad, coord_by_id, fix_start=True)

    assert [p.attachment_id for p in improved] == [p.attachment_id for p in pois]
    assert _path_distance_m(improved, coord_by_id) < bad_dist


def test_two_opt_keeps_start_when_fixed() -> None:
    pois = [_poi(0, 0), _poi(1, 0), _poi(2, 0), _poi(3, 0)]
    coord_by_id = {p.attachment_id: (float(i), 0.0) for i, p in enumerate(pois)}
    bad = [pois[2], pois[0], pois[1], pois[3]]

    improved = _two_opt_improve(bad, coord_by_id, fix_start=True)

    assert improved[0].attachment_id == pois[2].attachment_id  # 시작 POI 고정


def test_optimize_day_order_two_opt_beats_input_order() -> None:
    pois = [_poi(0, 0), _poi(2, 0), _poi(1, 0), _poi(3, 0)]  # 입력 자체가 교차
    ordered, total, previous, warnings = _optimize_day_order(
        pois, start_poi_id=pois[0].attachment_id, strategy="two_opt"
    )
    assert total is not None and previous is not None
    assert total < previous
    assert warnings == []
    assert ordered[0].attachment_id == pois[0].attachment_id


def test_optimize_day_order_appends_coordless_pois() -> None:
    a = _poi(0, 0)
    b = SimpleNamespace(attachment_id=uuid.uuid4(), feature_snapshot={}, sort_order="a0")
    c = _poi(1, 0)

    ordered, total, previous, warnings = _optimize_day_order(
        [a, b, c], start_poi_id=None, strategy="two_opt"
    )

    assert ordered[-1].attachment_id == b.attachment_id  # 좌표 없는 POI는 뒤로
    assert total is not None and previous is not None
    assert any("좌표가 없" in w for w in warnings)


def test_nearest_neighbor_only_strategy_skips_two_opt() -> None:
    pois = [_poi(0, 0), _poi(2, 0), _poi(1, 0), _poi(3, 0)]
    ordered, total, _previous, _warnings = _optimize_day_order(
        pois, start_poi_id=pois[0].attachment_id, strategy="nearest_neighbor"
    )
    # NN seed: 0 → 1 → 2 → 3 (근접). 여기선 2-opt 결과와 동일하지만 경로 유효성만 확인.
    assert total is not None
    assert ordered[0].attachment_id == pois[0].attachment_id
