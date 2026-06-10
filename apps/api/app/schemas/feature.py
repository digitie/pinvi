"""Feature Pydantic schema — `docs/api/features.md`.

krtour-map OpenAPI(`openapi.user.json`) 응답을 TripMate 측 API 응답 schema로 투영한다.
TripMate는 응답 셰입을 소유하되 **krtour 실계약 field 명/의미에 정합**한다(ADR-026/030):
평면 `lon`/`lat`(DEC-07→`lon`/`lat` 정렬), 표시명 `name`, 구조화 `address` 객체,
클러스터 자연키 `cluster_key`, 날씨 평탄 `metrics`(+`forecast_style`).

- 사용자에게 노출할 필드만 (PII / 내부 metadata 제외)
- Zod 측 `packages/schemas/src/feature.ts` 와 cross-validation
- `feature_id` 는 krtour `make_feature_id` 출력 불투명 문자열(ADR-028, UUID 아님)
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
    """마커/목록 표시용 (in-bounds items / nearby / search 응답).

    krtour `FeatureSummary`/`NearbyFeatureSummary` 투영. krtour는 평면 `lon`/`lat`,
    `name`, `status`를 주고 `lon`/`lat`/`marker_*`는 nullable. nearby 응답에만
    `distance_m`이 채워진다.
    """

    feature_id: str = Field(min_length=1, max_length=200)
    kind: FeatureKind
    name: str
    coord: Coord | None = None  # krtour lon/lat nullable (point geometry 없는 kind)
    category: str | None = None
    marker_color: str = Field(default="P-13", pattern=r"^P-\d{2}$")  # 16색 P-01~P-16
    marker_icon: str = Field(default="marker", max_length=64)  # maki icon name
    status: str | None = None  # active / inactive / hidden 등 (krtour lifecycle)
    distance_m: float | None = None  # nearby 응답에만


class FeatureCluster(BaseModel):
    """서버(krtour) 클러스터 — `cluster_key`는 행정구역 코드(자연키, ADR-048 §3.1)."""

    cluster_key: str
    coord: Coord
    feature_count: int = Field(ge=1)


class FeaturesInBoundsResponse(BaseModel):
    """viewport 응답 — 개별 feature(`items`) + 서버 cluster(`clusters`) 혼합.

    클러스터링은 krtour 서버 책임(`cluster_unit`/`zoom`). granularity는
    `meta.cluster.cluster_unit`로 오므로 `cluster_unit`에 투영한다.
    """

    items: list[FeatureSummary] = Field(default_factory=list)
    clusters: list[FeatureCluster] = Field(default_factory=list)
    cluster_unit: str | None = None  # sido | sigungu | eupmyeondong | individual
    zoom: int
    bbox: BBox


class FeatureDetail(BaseModel):
    """상세 응답 — `GET /features/{id}` (krtour `FeatureDetailResponse` 투영)."""

    feature_id: str = Field(min_length=1, max_length=200)
    kind: FeatureKind
    name: str
    coord: Coord | None = None
    category: str | None = None
    address: dict[str, Any] | None = None  # 구조화 주소 객체 (krtour 원본)
    legal_dong_code: str | None = None  # 법정동 코드
    sido_code: str | None = None
    sigungu_code: str | None = None
    marker_color: str = Field(default="P-13", pattern=r"^P-\d{2}$")
    marker_icon: str = Field(default="marker", max_length=64)
    urls: dict[str, Any] = Field(default_factory=dict)  # homepage/sns/review 등
    detail: dict[str, Any] = Field(default_factory=dict)  # kind별 PlaceDetail 등
    status: str | None = None
    updated_at: datetime


class WeatherMetric(BaseModel):
    """krtour 평탄 weather metric — `forecast_style` 태그로 카드 그룹핑(표현 계층)."""

    metric_key: str
    metric_name: str | None = None
    forecast_style: str  # nowcast / ultra_short / short / mid / observed / index / advisory
    timeline_bucket: str | None = None
    valid_at: datetime | None = None
    issued_at: datetime | None = None
    observed_at: datetime | None = None
    value_number: float | None = None
    value_text: str | None = None
    unit: str | None = None
    severity: str | None = None


class FeatureWeatherCard(BaseModel):
    """weather 응답 — `GET /features/{id}/weather` (krtour `WeatherCardData` 투영).

    krtour는 평탄 `metrics` 목록 + `source_styles`를 준다. 프런트는 `forecast_style`
    별로 그룹핑해 카드를 구성한다(KMA provider 변환을 TripMate가 직접 작성하지 않음).
    """

    feature_id: str = Field(min_length=1, max_length=200)
    asof: datetime | None = None
    latest_at: datetime | None = None
    is_stale: bool = False
    source_styles: list[str] = Field(default_factory=list)
    metrics: list[WeatherMetric] = Field(default_factory=list)


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
