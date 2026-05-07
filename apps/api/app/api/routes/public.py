from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.db.session import get_db
from app.models.beach import (
    BeachIndexForecast,
    BeachObservation,
    BeachProfile,
    BeachProviderRef,
    BeachWaterQualityMeasurement,
)
from app.models.tour import TourServingPublicCulturalFestival
from app.models.weather import WeatherServingBeach
from app.schemas.public import (
    PublicBeachIndexForecast,
    PublicBeachListResponse,
    PublicBeachMapMarker,
    PublicBeachMapMarkerResponse,
    PublicBeachObservation,
    PublicBeachSummary,
    PublicBeachWaterQuality,
    PublicBeachWeatherValue,
    PublicFestivalDetail,
    PublicFestivalMapMarker,
    PublicFestivalMapMarkerResponse,
    PublicFestivalMonthlyResponse,
    PublicFestivalMonthSummary,
    PublicFestivalSummary,
)

router = APIRouter(prefix="/public", tags=["public"])

FESTIVAL_LAYER_KEY = "festival"
FESTIVAL_MARKER_COLOR = "#ff5a5f"
FESTIVAL_MARKER_ICON = "music"
BEACH_LAYER_KEY = "beach"
BEACH_MARKER_COLOR = "#0ea5e9"
BEACH_MARKER_ICON = "waves"


@router.get("/beaches", response_model=PublicBeachListResponse)
def get_public_beaches(
    db: Annotated[Session, Depends(get_db)],
    sido_code: Annotated[str | None, Query(min_length=2, max_length=10)] = None,
    sigungu_code: Annotated[str | None, Query(min_length=5, max_length=10)] = None,
    query: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=300)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PublicBeachListResponse:
    statement = select(BeachProfile).where(BeachProfile.is_active.is_(True))
    if sido_code is not None:
        statement = statement.where(BeachProfile.sido_code == sido_code)
    if sigungu_code is not None:
        statement = statement.where(BeachProfile.sigungu_code == sigungu_code)
    if query is not None:
        normalized_query = f"%{query.lower().strip()}%"
        statement = statement.where(
            or_(
                func.lower(BeachProfile.display_name).like(normalized_query),
                BeachProfile.normalized_name.like(normalized_query),
            )
        )
    count_statement = select(func.count()).select_from(statement.subquery())
    total_count = int(db.scalar(count_statement) or 0)
    rows = db.scalars(
        statement.order_by(BeachProfile.display_name.asc()).offset(offset).limit(limit)
    ).all()
    return PublicBeachListResponse(
        beaches=[_to_public_beach_summary(db, row) for row in rows],
        count=total_count,
    )


@router.get("/beaches/map-markers", response_model=PublicBeachMapMarkerResponse)
def get_public_beach_map_markers(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> PublicBeachMapMarkerResponse:
    rows = db.scalars(
        select(BeachProfile)
        .where(BeachProfile.is_active.is_(True))
        .where(BeachProfile.longitude.is_not(None))
        .where(BeachProfile.latitude.is_not(None))
        .order_by(BeachProfile.display_name.asc())
        .limit(limit)
    ).all()
    markers = [
        PublicBeachMapMarker(
            id=row.id,
            title=row.display_name,
            longitude=row.longitude,
            latitude=row.latitude,
            marker_color=BEACH_MARKER_COLOR,
            marker_icon=BEACH_MARKER_ICON,
            layer_key=BEACH_LAYER_KEY,
        )
        for row in rows
        if row.longitude is not None and row.latitude is not None
    ]
    return PublicBeachMapMarkerResponse(
        layer_key=BEACH_LAYER_KEY,
        display_name="해수욕장",
        markers=markers,
    )


@router.get("/beaches/{beach_id}", response_model=PublicBeachSummary)
def get_public_beach_detail(
    beach_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> PublicBeachSummary:
    row = db.get(BeachProfile, beach_id)
    if row is None or not row.is_active:
        raise HTTPException(status_code=404, detail="해수욕장 정보를 찾을 수 없다.")
    return _to_public_beach_summary(db, row)


@router.get("/festivals/monthly", response_model=PublicFestivalMonthlyResponse)
def get_public_monthly_festivals(
    db: Annotated[Session, Depends(get_db)],
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
) -> PublicFestivalMonthlyResponse:
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    resolved_year = year or today.year
    resolved_month = month or today.month
    month_start, month_end = _month_window(resolved_year, resolved_month)
    months = [
        PublicFestivalMonthSummary(
            month=candidate_month,
            count=_festival_count_for_month(db, resolved_year, candidate_month),
        )
        for candidate_month in range(1, 13)
    ]
    rows = db.scalars(
        select(TourServingPublicCulturalFestival)
        .where(TourServingPublicCulturalFestival.is_active.is_(True))
        .where(_overlaps_month(month_start, month_end))
        .order_by(
            TourServingPublicCulturalFestival.event_start_date.asc().nulls_last(),
            TourServingPublicCulturalFestival.festival_name.asc(),
        )
        .limit(limit)
    ).all()
    return PublicFestivalMonthlyResponse(
        year=resolved_year,
        month=resolved_month,
        months=months,
        festivals=[_to_public_festival_summary(row) for row in rows],
    )


@router.get("/festivals/map-markers", response_model=PublicFestivalMapMarkerResponse)
def get_public_festival_map_markers(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> PublicFestivalMapMarkerResponse:
    rows = db.scalars(
        select(TourServingPublicCulturalFestival)
        .where(TourServingPublicCulturalFestival.is_active.is_(True))
        .where(TourServingPublicCulturalFestival.longitude.is_not(None))
        .where(TourServingPublicCulturalFestival.latitude.is_not(None))
        .order_by(
            TourServingPublicCulturalFestival.event_start_date.asc().nulls_last(),
            TourServingPublicCulturalFestival.festival_name.asc(),
        )
        .limit(limit)
    ).all()
    return PublicFestivalMapMarkerResponse(
        layer_key=FESTIVAL_LAYER_KEY,
        display_name="축제",
        markers=[_to_public_festival_map_marker(row) for row in rows],
    )


@router.get("/festivals/{festival_id}", response_model=PublicFestivalDetail)
def get_public_festival_detail(
    festival_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> PublicFestivalDetail:
    row = db.get(TourServingPublicCulturalFestival, festival_id)
    if row is None or not row.is_active:
        raise HTTPException(status_code=404, detail="축제 정보를 찾을 수 없다.")
    return _to_public_festival_detail(row)


def _festival_count_for_month(db: Session, year: int, month: int) -> int:
    month_start, month_end = _month_window(year, month)
    return int(
        db.scalar(
            select(func.count())
            .select_from(TourServingPublicCulturalFestival)
            .where(TourServingPublicCulturalFestival.is_active.is_(True))
            .where(_overlaps_month(month_start, month_end))
        )
        or 0
    )


def _overlaps_month(month_start: date, month_end: date) -> ColumnElement[bool]:
    return or_(
        TourServingPublicCulturalFestival.event_start_date.between(month_start, month_end),
        TourServingPublicCulturalFestival.event_end_date.between(month_start, month_end),
        and_(
            TourServingPublicCulturalFestival.event_start_date <= month_start,
            TourServingPublicCulturalFestival.event_end_date >= month_end,
        ),
    )


def _month_window(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _to_public_beach_summary(db: Session, row: BeachProfile) -> PublicBeachSummary:
    return PublicBeachSummary(
        id=row.id,
        display_name=row.display_name,
        longitude=row.longitude,
        latitude=row.latitude,
        legal_dong_code=row.legal_dong_code,
        sigungu_code=row.sigungu_code,
        sido_code=row.sido_code,
        road_name_code=row.road_name_code,
        road_address_management_no=row.road_address_management_no,
        road_address=row.road_address,
        address_snapshot=row.address_snapshot,
        address_mapping_method=row.address_mapping_method,
        beach_width_m=row.beach_width_m,
        beach_length_m=row.beach_length_m,
        beach_material=row.beach_material,
        homepage_url=row.homepage_url,
        homepage_name=row.homepage_name,
        image_url=row.image_url,
        emergency_contact=row.emergency_contact,
        source_providers=_beach_source_providers(db, row.id),
        latest_observation=_latest_beach_observation(db, row.id),
        latest_water_quality=_latest_beach_water_quality(db, row.id),
        upcoming_index_forecasts=_upcoming_beach_index_forecasts(db, row.id),
        latest_weather=_latest_beach_weather(db, row.map_feature_id),
    )


def _beach_source_providers(db: Session, beach_id: UUID) -> list[str]:
    rows = db.scalars(
        select(BeachProviderRef.provider)
        .where(BeachProviderRef.beach_id == beach_id)
        .order_by(BeachProviderRef.provider.asc())
    ).all()
    return sorted(set(rows))


def _latest_beach_observation(db: Session, beach_id: UUID) -> PublicBeachObservation | None:
    row = db.scalar(
        select(BeachObservation)
        .where(BeachObservation.beach_id == beach_id)
        .where(BeachObservation.is_active.is_(True))
        .order_by(BeachObservation.observed_at.desc())
        .limit(1)
    )
    if row is None:
        return None
    return PublicBeachObservation(
        observed_at=row.observed_at,
        observation_station_name=row.observation_station_name,
        tide=row.tide,
        wave_height_m=row.wave_height_m,
        water_temperature_c=row.water_temperature_c,
        wind_speed_ms=row.wind_speed_ms,
        wind_direction=row.wind_direction,
        forecast_status=row.forecast_status,
        collected_at=row.collected_at,
    )


def _latest_beach_water_quality(db: Session, beach_id: UUID) -> PublicBeachWaterQuality | None:
    row = db.scalar(
        select(BeachWaterQualityMeasurement)
        .where(BeachWaterQualityMeasurement.beach_id == beach_id)
        .where(BeachWaterQualityMeasurement.is_active.is_(True))
        .order_by(
            BeachWaterQualityMeasurement.survey_date.desc().nulls_last(),
            BeachWaterQualityMeasurement.collected_at.desc(),
        )
        .limit(1)
    )
    if row is None:
        return None
    return PublicBeachWaterQuality(
        survey_year=row.survey_year,
        survey_date=row.survey_date,
        survey_round=row.survey_round,
        survey_kind=row.survey_kind,
        survey_location=row.survey_location,
        ecoli_result=row.ecoli_result,
        enterococcus_result=row.enterococcus_result,
        suitability=row.suitability,
        collected_at=row.collected_at,
    )


def _upcoming_beach_index_forecasts(
    db: Session,
    beach_id: UUID,
) -> list[PublicBeachIndexForecast]:
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    rows = db.scalars(
        select(BeachIndexForecast)
        .where(BeachIndexForecast.beach_id == beach_id)
        .where(BeachIndexForecast.is_active.is_(True))
        .where(BeachIndexForecast.forecast_date >= today)
        .order_by(BeachIndexForecast.forecast_date.asc(), BeachIndexForecast.forecast_slot.asc())
        .limit(14)
    ).all()
    return [
        PublicBeachIndexForecast(
            forecast_date=row.forecast_date,
            forecast_slot=row.forecast_slot,
            index_score=row.index_score,
            total_index=row.total_index,
            max_wave_height_m=row.max_wave_height_m,
            avg_water_temperature_c=row.avg_water_temperature_c,
            avg_air_temperature_c=row.avg_air_temperature_c,
            max_wind_speed_ms=row.max_wind_speed_ms,
            collected_at=row.collected_at,
        )
        for row in rows
    ]


def _latest_beach_weather(
    db: Session,
    map_feature_id: UUID | None,
) -> list[PublicBeachWeatherValue]:
    if map_feature_id is None:
        return []
    rows = db.scalars(
        select(WeatherServingBeach)
        .where(WeatherServingBeach.map_feature_id == map_feature_id)
        .where(WeatherServingBeach.is_active.is_(True))
        .order_by(
            WeatherServingBeach.normalized_category.asc(),
            WeatherServingBeach.forecast_at.desc().nulls_last(),
            WeatherServingBeach.observed_at.desc().nulls_last(),
            WeatherServingBeach.collected_at.desc(),
        )
        .limit(100)
    ).all()
    latest_by_category: dict[str, WeatherServingBeach] = {}
    for weather_row in rows:
        latest_by_category.setdefault(weather_row.normalized_category, weather_row)
    return [
        PublicBeachWeatherValue(
            provider=weather_row.provider,
            endpoint=weather_row.endpoint,
            normalized_category=weather_row.normalized_category,
            category_name=weather_row.category_name,
            value=weather_row.value,
            unit=weather_row.unit,
            observed_at=weather_row.observed_at,
            forecast_at=weather_row.forecast_at,
            collected_at=weather_row.collected_at,
        )
        for weather_row in latest_by_category.values()
    ]


def _to_public_festival_summary(
    row: TourServingPublicCulturalFestival,
) -> PublicFestivalSummary:
    return PublicFestivalSummary(
        id=row.id,
        source_record_id=row.source_record_id,
        festival_name=row.festival_name,
        venue_name=row.venue_name,
        event_start_date=row.event_start_date,
        event_end_date=row.event_end_date,
        event_status=row.event_status,
        road_address=row.road_address,
        jibun_address=row.jibun_address,
        sigungu_code=row.sigungu_code,
        sido_code=row.sido_code,
        longitude=row.longitude,
        latitude=row.latitude,
        homepage_url=row.homepage_url,
    )


def _to_public_festival_detail(
    row: TourServingPublicCulturalFestival,
) -> PublicFestivalDetail:
    return PublicFestivalDetail(
        **_to_public_festival_summary(row).model_dump(),
        festival_content=row.festival_content,
        mnnst_name=row.mnnst_name,
        auspc_instt_name=row.auspc_instt_name,
        suprt_instt_name=row.suprt_instt_name,
        phone_number=row.phone_number,
        related_info=row.related_info,
        address_snapshot=row.address_snapshot,
        road_name_code=row.road_name_code,
        road_address_management_no=row.road_address_management_no,
        provider_institution_name=row.provider_institution_name,
        reference_date=row.reference_date,
        marker_color=FESTIVAL_MARKER_COLOR,
        marker_icon=FESTIVAL_MARKER_ICON,
    )


def _to_public_festival_map_marker(
    row: TourServingPublicCulturalFestival,
) -> PublicFestivalMapMarker:
    if row.longitude is None or row.latitude is None:
        raise ValueError("map marker row requires coordinates")
    return PublicFestivalMapMarker(
        id=row.id,
        source_record_id=row.source_record_id,
        title=row.festival_name,
        event_start_date=row.event_start_date,
        event_end_date=row.event_end_date,
        event_status=row.event_status,
        longitude=row.longitude,
        latitude=row.latitude,
        marker_color=FESTIVAL_MARKER_COLOR,
        marker_icon=FESTIVAL_MARKER_ICON,
        layer_key=FESTIVAL_LAYER_KEY,
    )
