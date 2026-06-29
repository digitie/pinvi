"""Geocoding/행정구역 API schema — `docs/api/regions.md` + `docs/integrations/kor-travel-geo.md`.

kor-travel-geo v2 REST 후보(candidate)는 풍부하고 자주 진화하므로 Pinvi 응답은 candidate를
`dict` 그대로 pass-through하되, 최상위 envelope만 타입 고정한다. 좌표는 `(lon, lat)`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SearchKind = Literal["address", "place", "district", "road", "category"]
# kor-travel-geo v2 행정구역 level 어휘 (구 `legal_dong` → `emd`, ADR-049 / geo ADR-056·062).
BoundaryLevel = Literal["sido", "sigungu", "emd"]
RegionRelation = Literal["contains", "overlaps"]


class GeoCandidateList(BaseModel):
    """v2 reverse/geocode/search 공통 — candidate pass-through + 상태."""

    status: str
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    total: int | None = None


class RegionCovering(BaseModel):
    """좌표를 포함하는 행정구역(단건). kor-travel-geo `region` 객체 pass-through."""

    boundary_level: BoundaryLevel
    region: dict[str, Any]


class RegionWithinRadiusItem(BaseModel):
    """반경 내 행정구역 1건. `relation`: contains(중심 포함) | overlaps(반경 원과 교차)."""

    code: str
    name: str | None = None
    relation: RegionRelation


class RegionsWithinRadius(BaseModel):
    """좌표 반경 내 행정구역 — level별 그룹. kor-travel-geo v2 `/v2/regions/within-radius`.

    응답은 후보(candidate) 목록이 아니라 sido/sigungu/emd level별 배열이다(geo ADR-062).
    `center`는 `{lon, lat}`, 요청하지 않은 level은 빈 배열로 온다.
    """

    center: dict[str, Any] = Field(default_factory=dict)
    radius_km: float
    sido: list[RegionWithinRadiusItem] = Field(default_factory=list)
    sigungu: list[RegionWithinRadiusItem] = Field(default_factory=list)
    emd: list[RegionWithinRadiusItem] = Field(default_factory=list)


class UnifiedSearchResult(BaseModel):
    """통합 검색 — feature(kor_travel_map) + address(kor_travel_geo) + 내 POI(Pinvi). 소스별 degrade 가능."""

    features: list[dict[str, Any]] = Field(default_factory=list)
    addresses: list[dict[str, Any]] = Field(default_factory=list)
    my_pois: list[dict[str, Any]] = Field(default_factory=list)
    degraded_sources: list[str] = Field(default_factory=list)
