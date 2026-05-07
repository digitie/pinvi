from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class PublicFestivalMonthSummary(BaseModel):
    month: int = Field(ge=1, le=12)
    count: int


class PublicFestivalSummary(BaseModel):
    id: UUID
    source_record_id: str
    festival_name: str
    venue_name: str | None
    event_start_date: date | None
    event_end_date: date | None
    event_status: str
    road_address: str | None
    jibun_address: str | None
    sigungu_code: str | None
    sido_code: str | None
    longitude: Decimal | None
    latitude: Decimal | None
    homepage_url: str | None


class PublicFestivalMonthlyResponse(BaseModel):
    year: int
    month: int = Field(ge=1, le=12)
    months: list[PublicFestivalMonthSummary]
    festivals: list[PublicFestivalSummary]


class PublicFestivalDetail(PublicFestivalSummary):
    festival_content: str | None
    mnnst_name: str | None
    auspc_instt_name: str | None
    suprt_instt_name: str | None
    phone_number: str | None
    related_info: str | None
    address_snapshot: str | None
    road_name_code: str | None
    road_address_management_no: str | None
    provider_institution_name: str | None
    reference_date: date | None
    marker_color: str
    marker_icon: str


class PublicFestivalMapMarker(BaseModel):
    id: UUID
    source_record_id: str
    title: str
    event_start_date: date | None
    event_end_date: date | None
    event_status: str
    longitude: Decimal
    latitude: Decimal
    marker_color: str
    marker_icon: str
    layer_key: str


class PublicFestivalMapMarkerResponse(BaseModel):
    layer_key: str
    display_name: str
    markers: list[PublicFestivalMapMarker]


class PublicBeachObservation(BaseModel):
    observed_at: datetime
    observation_station_name: str | None
    tide: str | None
    wave_height_m: Decimal | None
    water_temperature_c: Decimal | None
    wind_speed_ms: Decimal | None
    wind_direction: str | None
    forecast_status: dict[str, object]
    collected_at: datetime


class PublicBeachIndexForecast(BaseModel):
    forecast_date: date
    forecast_slot: str
    index_score: Decimal | None
    total_index: str | None
    max_wave_height_m: Decimal | None
    avg_water_temperature_c: Decimal | None
    avg_air_temperature_c: Decimal | None
    max_wind_speed_ms: Decimal | None
    collected_at: datetime


class PublicBeachWaterQuality(BaseModel):
    survey_year: int
    survey_date: date | None
    survey_round: str | None
    survey_kind: str | None
    survey_location: str | None
    ecoli_result: str | None
    enterococcus_result: str | None
    suitability: str | None
    collected_at: datetime


class PublicBeachWeatherValue(BaseModel):
    provider: str
    endpoint: str
    normalized_category: str
    category_name: str
    value: str
    unit: str | None
    observed_at: datetime | None
    forecast_at: datetime | None
    collected_at: datetime


class PublicBeachSummary(BaseModel):
    id: UUID
    display_name: str
    longitude: Decimal | None
    latitude: Decimal | None
    legal_dong_code: str | None
    sigungu_code: str | None
    sido_code: str | None
    road_name_code: str | None
    road_address_management_no: str | None
    road_address: str | None
    address_snapshot: str | None
    address_mapping_method: str
    beach_width_m: Decimal | None
    beach_length_m: Decimal | None
    beach_material: str | None
    homepage_url: str | None
    homepage_name: str | None
    image_url: str | None
    emergency_contact: str | None
    source_providers: list[str]
    latest_observation: PublicBeachObservation | None
    latest_water_quality: PublicBeachWaterQuality | None
    upcoming_index_forecasts: list[PublicBeachIndexForecast]
    latest_weather: list[PublicBeachWeatherValue]


class PublicBeachListResponse(BaseModel):
    beaches: list[PublicBeachSummary]
    count: int


class PublicBeachMapMarker(BaseModel):
    id: UUID
    title: str
    longitude: Decimal
    latitude: Decimal
    marker_color: str
    marker_icon: str
    layer_key: str


class PublicBeachMapMarkerResponse(BaseModel):
    layer_key: str
    display_name: str
    markers: list[PublicBeachMapMarker]
