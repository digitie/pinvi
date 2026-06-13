"""Geocoding/행정구역 API schema — `docs/api/regions.md` + `docs/integrations/kor-travel-geo.md`.

kor-travel-geo v2 REST 후보(candidate)는 풍부하고 자주 진화하므로 Pinvi 응답은 candidate를
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


class RegionCovering(BaseModel):
    """좌표를 포함하는 행정구역(단건). kor-travel-geo `region` 객체 pass-through."""

    boundary_level: BoundaryLevel
    region: dict[str, Any]


class UnifiedSearchResult(BaseModel):
    """통합 검색 — feature(kor_travel_map) + address(kor_travel_geo) + 내 POI(Pinvi). 소스별 degrade 가능."""

    features: list[dict[str, Any]] = Field(default_factory=list)
    addresses: list[dict[str, Any]] = Field(default_factory=list)
    my_pois: list[dict[str, Any]] = Field(default_factory=list)
    degraded_sources: list[str] = Field(default_factory=list)
