"""Public API schema — `docs/api/public.md`.

Pinvi `/public/*`는 인증 없이 노출되는 read-only 표면이다. 데이터 원천은
kor-travel-map `openapi.user.json`의 `/v1/public/*` 응답이며, Pinvi는 사용자에게
노출할 필드와 envelope/meta 투영만 소유한다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class PublicBeachView(BaseModel):
    """해수욕장 공개 목록/상세 view."""

    feature_id: str = Field(min_length=1, max_length=200)
    display_name: str
    address: dict[str, Any] = Field(default_factory=dict)
    source_providers: list[str] = Field(default_factory=list)
    updated_at: datetime
    beach_kind: str | None = None
    beach_width_m: float | None = None
    beach_length_m: float | None = None
    beach_material: str | None = None
    emergency_contact: str | None = None
    homepage_url: str | None = None
    image_url: str | None = None
    road_address: str | None = None
    jibun_address: str | None = None
    legal_dong_code: str | None = None
    sido_code: str | None = None
    sigungu_code: str | None = None
    lon: float | None = None
    lat: float | None = None
    marker_color: str | None = None
    marker_icon: str | None = None
    latest_water_quality: dict[str, Any] | None = None
    latest_weather: dict[str, Any] | None = None
    upcoming_index_forecasts: list[dict[str, Any]] = Field(default_factory=list)


class PublicBeachList(BaseModel):
    """해수욕장 공개 목록 payload."""

    items: list[PublicBeachView] = Field(default_factory=list)


PublicFestivalStatus = Literal["scheduled", "ongoing", "ended", "unknown"]


class PublicFestivalView(BaseModel):
    """축제 공개 목록/상세 view."""

    feature_id: str = Field(min_length=1, max_length=200)
    festival_name: str
    event_status: PublicFestivalStatus = "unknown"
    address: dict[str, Any] = Field(default_factory=dict)
    source_providers: list[str] = Field(default_factory=list)
    updated_at: datetime
    event_start_date: date | None = None
    event_end_date: date | None = None
    venue_name: str | None = None
    road_address: str | None = None
    jibun_address: str | None = None
    sido_code: str | None = None
    sigungu_code: str | None = None
    lon: float | None = None
    lat: float | None = None
    homepage_url: str | None = None
    festival_content: str | None = None
    organizer_name: str | None = None
    auspc_instt_name: str | None = None
    suprt_instt_name: str | None = None
    phone_number: str | None = None
    provider_org_name: str | None = None
    reference_date: date | None = None
    marker_color: str | None = None
    marker_icon: str | None = None


class PublicFestivalMonth(BaseModel):
    """월별 축제 count summary."""

    year: int
    month: int = Field(ge=1, le=12)
    count: int = Field(ge=0)


class PublicFestivalMonthly(BaseModel):
    """월별 축제 공개 목록 payload."""

    months: list[PublicFestivalMonth] = Field(default_factory=list)
    items: list[PublicFestivalView] = Field(default_factory=list)


class PublicMapMarker(BaseModel):
    """공개 지도 layer marker 1건."""

    feature_id: str = Field(min_length=1, max_length=200)
    name: str
    lon: float
    lat: float
    sigungu_code: str | None = None


PublicMapLayerKey = Literal["beach", "festival"]


class PublicMapMarkerLayer(BaseModel):
    """공개 지도 layer marker payload."""

    layer_key: PublicMapLayerKey
    display_name: str
    marker_icon: str
    marker_color: str
    items: list[PublicMapMarker] = Field(default_factory=list)
