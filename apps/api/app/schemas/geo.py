"""Geocoding/행정구역 API schema — `docs/api/regions.md` + `docs/integrations/kraddr-geo.md`.

kraddr-geo v2 REST 후보(candidate)는 풍부하고 자주 진화하므로 TripMate 응답은 candidate를
`dict` 그대로 pass-through하되, 최상위 envelope만 타입 고정한다. 좌표는 `(lon, lat)`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SearchKind = Literal["address", "place", "district", "road", "category"]
BoundaryLevel = Literal["sido", "sigungu", "legal_dong"]


class GeoCandidateList(BaseModel):
    """v2 reverse/geocode/search/regions 공통 — candidate pass-through + 상태."""

    status: str
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    total: int | None = None
