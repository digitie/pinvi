"""#635 geometry와 완결성 신호를 누락하지 않는 경계."""

from __future__ import annotations

from typing import Any

import pytest

from app.api.v1.features import _summary_from_kor_travel_map
from app.schemas.feature import BBox, FeaturesInBoundsResponse

OUTER = [[127.0, 37.5], [127.02, 37.5], [127.02, 37.52], [127.0, 37.5]]
HOLE = [[127.005, 37.505], [127.01, 37.505], [127.01, 37.51], [127.005, 37.505]]
GEOMETRIES = [
    {"type": "LineString", "coordinates": OUTER[:2]},
    {"type": "MultiLineString", "coordinates": [OUTER[:2], HOLE[:2]]},
    {"type": "Polygon", "coordinates": [OUTER, HOLE]},
    {"type": "MultiPolygon", "coordinates": [[OUTER, HOLE], [OUTER]]},
]


@pytest.mark.parametrize("geometry", GEOMETRIES)
def test_summary_preserves_full_geometry_without_inventing_point(geometry: dict[str, Any]) -> None:
    shape = _summary_from_kor_travel_map(
        {
            "feature_id": "geometry:635",
            "kind": "route" if "LineString" in geometry["type"] else "area",
            "name": "도형 검증",
            "lon": None,
            "lat": None,
            "marker_color": "P-06",
            "geometry": geometry,
        }
    )
    assert shape.model_dump().get("geometry") == geometry
    assert shape.coord is None
    assert shape.marker_color == "P-06"


def test_in_bounds_preserves_truncation_instead_of_claiming_complete() -> None:
    data = FeaturesInBoundsResponse(
        items=[],
        clusters=[],
        zoom=14,
        bbox=BBox(lng_min=127, lat_min=37.5, lng_max=127.1, lat_max=37.6),
        truncated=True,
    )
    assert data.model_dump().get("truncated") is True
