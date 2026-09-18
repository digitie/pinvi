"""지도 weather marker 응답 schema — kor-travel-weather 직접 노출 (ADR-068, T-368).

feature가 아니다. `kor-travel-map`의 `FeatureSummary`/`FeatureKind`와는 완전히
분리된 스키마다 — T-363 trip view가 확립한 "완전 분리" 원칙을 지도 marker 표면에
적용한 결과다(설계 `docs/integrations/kor-travel-weather.md` §4.6/§7-3).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.feature import BBox, Coord

WeatherCondition = Literal["sunny", "cloudy", "rainy", "snowy"]


class WeatherMapMarker(BaseModel):
    """지도 표시용 — kor-travel-weather `NearbyOut` 투영.

    현재 온도를 안전하게 구하지 못하면 목록에 아예 포함하지 않는다 — 예전
    `FeatureMapView.tsx`가 선택 전 마커에 `temperature=0`을 표시하던 것과 달리,
    없는 값을 0으로 가장하지 않는다.
    """

    location_id: str = Field(min_length=1, max_length=200)
    name: str
    coord: Coord
    temperature_c: float
    condition: WeatherCondition
    provider: str | None = None


class WeatherMarkersInBoundsResponse(BaseModel):
    """viewport 응답 — `GET /weather/markers-in-bounds`."""

    items: list[WeatherMapMarker] = Field(default_factory=list)
    zoom: int
    bbox: BBox
