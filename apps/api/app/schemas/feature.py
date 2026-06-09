"""Feature Pydantic schema — `docs/api/features.md`.

라이브러리 DTO를 그대로 export하지 않고 TripMate 측 API 응답 schema로 재정의.
- 사용자에게 노출할 필드만 (PII / 내부 metadata 제외)
- Zod 측 `packages/schemas/src/feature.ts` 와 cross-validation

SPEC V8 §H-4 (Feature/지도 API) + ADR-015 (좌표 GeoJSON `(lng, lat)`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

FeatureKind = Literal[
    "place",
    "event",
    "notice",
    "price",
    "weather",
    "route",
    "area",
]
FeatureRequestStatus = Literal["pending", "approved", "rejected", "added", "duplicate"]
FeatureRequestType = Literal["new_place", "correction", "closure"]
# 사용자가 제안 가능한 kind는 사실상 장소/이벤트뿐(notice/price/weather/route/area는 운영 데이터).
FeatureSuggestionKind = Literal["place", "event"]
FeatureRequestCategory = Annotated[str, Field(min_length=1, max_length=80)]


class Coord(BaseModel):
    """EPSG:4326 — `(lon, lat)` 순서, 대한민국 범위 (ADR-018)."""

    lon: float = Field(ge=124.0, le=132.0)
    lat: float = Field(ge=33.0, le=43.0)


class BBox(BaseModel):
    """viewport bounding box."""

    lng_min: float = Field(ge=124.0, le=132.0)
    lat_min: float = Field(ge=33.0, le=43.0)
    lng_max: float = Field(ge=124.0, le=132.0)
    lat_max: float = Field(ge=33.0, le=43.0)

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.lng_min, self.lat_min, self.lng_max, self.lat_max)


class FeatureSummary(BaseModel):
    """viewport feature 마커 표시용 (in-bounds / nearby / search 응답)."""

    feature_id: str = Field(min_length=1, max_length=200)
    kind: FeatureKind
    title: str
    coord: Coord
    marker_color: str = Field(pattern=r"^P-\d{2}$")  # 16색 팔레트 P-01~P-16
    marker_icon: str = Field(max_length=64)  # maki icon name
    category: str | None = None
    summary: str | None = None  # 1줄 요약


class FeatureCluster(BaseModel):
    """클러스터 마커 응답 — zoom < 14에서 라이브러리 측 클러스터링."""

    cluster_id: str  # 라이브러리 측 정의
    center: Coord
    feature_count: int = Field(ge=2)
    sample_kinds: list[FeatureKind] = Field(max_length=8)
    bbox: BBox  # 클러스터 영역


class FeaturesInBoundsResponse(BaseModel):
    """viewport 응답 — feature 또는 cluster mixed."""

    features: list[FeatureSummary] = Field(default_factory=list)
    clusters: list[FeatureCluster] = Field(default_factory=list)
    zoom: int
    bbox: BBox


class FeatureDetail(BaseModel):
    """상세 응답 — `GET /features/{id}`."""

    feature_id: str = Field(min_length=1, max_length=200)
    kind: FeatureKind
    title: str
    coord: Coord
    marker_color: str = Field(pattern=r"^P-\d{2}$")
    marker_icon: str = Field(max_length=64)
    category: str | None = None
    address: str | None = None
    address_road: str | None = None
    bjd_code: str | None = None  # 법정동 코드
    sigungu_code: str | None = None
    description: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)  # 라이브러리 PlaceDetail 등
    source_ids: list[str] = Field(default_factory=list)  # `feature.source_links` 참조
    updated_at: datetime


class WeatherTimepoint(BaseModel):
    """KMA 시간축 1 point."""

    asof: datetime
    temp_c: float | None = None
    precipitation_mm: float | None = None
    precipitation_prob: float | None = None
    condition: str | None = None  # `clear` / `cloudy` / `rain` / `snow` 등
    wind_speed_ms: float | None = None
    humidity_pct: float | None = None


class FeatureWeatherCard(BaseModel):
    """KMA 시간축 응답 — `GET /features/{id}/weather`."""

    feature_id: str = Field(min_length=1, max_length=200)
    asof: datetime
    short_term: list[WeatherTimepoint] = Field(default_factory=list)  # 3h x 24
    daily: list[WeatherTimepoint] = Field(default_factory=list)  # day x 7
    sources: list[str] = Field(default_factory=list)  # 라이브러리 `source_links` 키


class FeatureRequestCreate(BaseModel):
    """사용자 feature 제안 큐 적재 — Admin이 검토 후 krtour feature 추가 API로 반영 (DEC-05)."""

    type: FeatureRequestType = "new_place"
    kind: FeatureSuggestionKind = "place"
    title: str = Field(min_length=1, max_length=200)
    coord: Coord
    categories: list[FeatureRequestCategory] = Field(default_factory=list, max_length=10)
    note: str | None = Field(default=None, max_length=2000)
    # correction/closure(기존 feature 참조) 시 필수, new_place 시 금지.
    target_feature_id: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_target_feature_id(self) -> Self:
        if self.type in ("correction", "closure") and self.target_feature_id is None:
            raise ValueError("correction/closure 제안은 target_feature_id가 필요합니다.")
        if self.type == "new_place" and self.target_feature_id is not None:
            raise ValueError("new_place 제안은 target_feature_id를 가질 수 없습니다.")
        return self


class FeatureRequestResponse(BaseModel):
    request_id: uuid.UUID
    status: FeatureRequestStatus = "pending"
    type: FeatureRequestType = "new_place"
    kind: FeatureKind
    title: str = Field(min_length=1, max_length=200)
    coord: Coord
    categories: list[FeatureRequestCategory] = Field(default_factory=list, max_length=10)
    note: str | None = None
    target_feature_id: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None
