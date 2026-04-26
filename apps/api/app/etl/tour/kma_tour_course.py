from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.etl.weather.client import KmaWeatherApiClient
from app.models.address import RegionServingBoundary
from app.models.tour import (
    KmaRecommendedTourCourse,
    TourCourseRawKmaPoint,
    TourCourseRawKmaSpotWeather,
    TourCourseServingKmaSpotWeather,
)

MARKER_SOURCE_TYPE = "kma_recommended_tour_course"
KMA_TOUR_SPOT_WEATHER_ENDPOINT = "getTourStnVilageFcst1"
KST = ZoneInfo("Asia/Seoul")
EXPECTED_COLUMNS = {
    "테마분류",
    "코스 아이디",
    "관광지 아이디",
    "지역 아이디",
    "관광지명",
    "경도(도)",
    "위도(도)",
    "코스순서",
    "이동시간",
    "실내구분",
    "테마명",
}
THEME_CATEGORY_MAP = {
    "TH01": "nature",
    "TH02": "culture_art",
    "TH03": "leisure",
    "TH04": "food",
    "TH05": "history_tradition",
}
TOUR_WEATHER_CATEGORY_SPECS = {
    "POP": ("강수확률", "rain_probability", "%"),
    "PTY": ("강수형태", "precipitation_type", None),
    "PCP": ("강수량", "precipitation", "mm"),
    "REH": ("습도", "humidity", "%"),
    "SKY": ("하늘상태", "sky", None),
    "TMP": ("기온", "temperature", "deg_c"),
    "TMN": ("일 최저기온", "temperature_min", "deg_c"),
    "TMX": ("일 최고기온", "temperature_max", "deg_c"),
    "WSD": ("풍속", "wind_speed", "m/s"),
}


@dataclass(frozen=True)
class KmaTourCourseParseResult:
    rows: list[dict[str, str]]
    source_encoding: str
    csv_file_name: str


@dataclass(frozen=True)
class KmaTourCourseLoadResult:
    raw_row_count: int
    serving_row_count: int
    mapped_row_count: int
    skipped_row_count: int
    source_file_hash: str
    source_encoding: str


@dataclass(frozen=True)
class KmaTourCourseWeatherTarget:
    longitude: Decimal | float | str
    latitude: Decimal | float | str
    radius_km: Decimal | float | str = Decimal("15")


@dataclass(frozen=True)
class KmaTourCourseWeatherLoadResult:
    target_count: int
    course_count: int
    raw_row_count: int
    serving_row_count: int
    skipped_row_count: int


def load_kma_tour_course_file(
    session: Session,
    source_path: Path | str,
    *,
    source_snapshot_date: date | None = None,
    collected_at: datetime | None = None,
) -> KmaTourCourseLoadResult:
    path = Path(source_path)
    return load_kma_tour_course_bytes(
        session,
        source_file_name=path.name,
        data=path.read_bytes(),
        source_snapshot_date=source_snapshot_date,
        collected_at=collected_at,
    )


def load_kma_tour_course_bytes(
    session: Session,
    *,
    source_file_name: str,
    data: bytes,
    source_snapshot_date: date | None = None,
    collected_at: datetime | None = None,
) -> KmaTourCourseLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    source_file_hash = hashlib.sha256(data).hexdigest()
    parsed = parse_kma_tour_course_bytes(source_file_name=source_file_name, data=data)
    raw_count = 0
    serving_count = 0
    mapped_count = 0
    skipped_count = 0

    session.execute(
        delete(KmaRecommendedTourCourse).where(
            KmaRecommendedTourCourse.source_file_hash == source_file_hash
        )
    )
    session.execute(
        delete(TourCourseRawKmaPoint).where(
            TourCourseRawKmaPoint.source_file_hash == source_file_hash
        )
    )
    for row_number, row in enumerate(parsed.rows, start=1):
        raw_payload = dict(row)
        theme_category_code = _required_text(row, "테마분류")
        course_id = _required_text(row, "코스 아이디")
        spot_id = _required_text(row, "관광지 아이디")
        spot_name = _required_text(row, "관광지명")
        region_id = _optional_text(row, "지역 아이디")
        session.add(
            TourCourseRawKmaPoint(
                source_file_name=parsed.csv_file_name,
                source_file_hash=source_file_hash,
                source_encoding=parsed.source_encoding,
                source_snapshot_date=source_snapshot_date,
                row_number=row_number,
                theme_category_code=theme_category_code,
                course_id=course_id,
                spot_id=spot_id,
                region_id=region_id,
                spot_name=spot_name,
                raw_payload=raw_payload,
                raw_line=None,
                response_hash=_hash_payload(raw_payload),
                collected_at=resolved_collected_at,
            )
        )
        raw_count += 1

        lon = _optional_decimal(row.get("경도(도)"))
        lat = _optional_decimal(row.get("위도(도)"))
        if lon is None or lat is None:
            skipped_count += 1
            continue
        boundary = _find_legal_boundary(session, longitude=lon, latitude=lat)
        if boundary is not None:
            mapped_count += 1
        session.add(
            KmaRecommendedTourCourse(
                source_file_name=parsed.csv_file_name,
                source_file_hash=source_file_hash,
                source_encoding=parsed.source_encoding,
                source_snapshot_date=source_snapshot_date,
                theme_category_code=theme_category_code,
                theme_category=THEME_CATEGORY_MAP.get(theme_category_code, "unknown"),
                theme_name=_optional_text(row, "테마명"),
                course_id=course_id,
                spot_id=spot_id,
                region_id=region_id,
                spot_name=spot_name,
                longitude=lon,
                latitude=lat,
                course_order=_optional_int(row.get("코스순서")),
                travel_time_minutes=_optional_int(row.get("이동시간")),
                indoor_type=_optional_text(row, "실내구분"),
                legal_dong_code=boundary.legal_dong_code if boundary else None,
                sigungu_code=boundary.sigungu_code if boundary else None,
                sido_code=boundary.sido_code if boundary else None,
                address_snapshot=None,
                address_mapping_method="postgis_point_in_polygon" if boundary else "unmapped",
                marker_source_type=MARKER_SOURCE_TYPE,
                raw_payload=raw_payload,
                collected_at=resolved_collected_at,
            )
        )
        serving_count += 1
    session.flush()
    return KmaTourCourseLoadResult(
        raw_row_count=raw_count,
        serving_row_count=serving_count,
        mapped_row_count=mapped_count,
        skipped_row_count=skipped_count,
        source_file_hash=source_file_hash,
        source_encoding=parsed.source_encoding,
    )


def load_kma_tour_course_weather_for_nearby_targets(
    session: Session,
    client: KmaWeatherApiClient,
    *,
    targets: list[KmaTourCourseWeatherTarget],
    max_courses: int = 200,
    collected_at: datetime | None = None,
) -> KmaTourCourseWeatherLoadResult:
    resolved_collected_at = _resolve_collected_at(collected_at)
    courses = _select_courses_near_targets(session, targets=targets, max_courses=max_courses)
    raw_count = 0
    serving_count = 0
    skipped_count = 0
    seen_course_ids: set[str] = set()
    course_lookup = {(course.course_id, course.spot_id): course for course in courses}

    for course_id in sorted({course.course_id for course in courses}):
        if course_id in seen_course_ids:
            continue
        seen_course_ids.add(course_id)
        rows = client.fetch_tour_spot_weather(course_id=course_id)
        for row in rows:
            raw_payload = dict(row)
            spot_id = (
                _optional_text_any(raw_payload, "spotId")
                or _optional_text_any(raw_payload, "spot_id")
                or _optional_text_any(raw_payload, "tourSpotId")
            )
            category_code = _optional_text_any(raw_payload, "category") or _optional_text_any(
                raw_payload, "categoryCode"
            )
            base_date = _optional_text_any(raw_payload, "baseDate")
            base_time = _optional_text_any(raw_payload, "baseTime")
            forecast_date = _optional_text_any(raw_payload, "fcstDate") or base_date
            forecast_time = _optional_text_any(raw_payload, "fcstTime") or base_time
            session.add(
                TourCourseRawKmaSpotWeather(
                    endpoint=KMA_TOUR_SPOT_WEATHER_ENDPOINT,
                    course_id=course_id,
                    spot_id=spot_id,
                    base_date=base_date,
                    base_time=base_time,
                    forecast_date=forecast_date,
                    forecast_time=forecast_time,
                    category_code=category_code,
                    raw_payload=raw_payload,
                    response_hash=_hash_payload(raw_payload),
                    collected_at=resolved_collected_at,
                )
            )
            raw_count += 1
            if category_code is None:
                skipped_count += 1
                continue
            source_course = course_lookup.get((course_id, spot_id)) if spot_id else None
            if source_course is None:
                source_course = next(
                    (candidate for candidate in courses if candidate.course_id == course_id),
                    None,
                )
            _upsert_tour_course_spot_weather(
                session,
                source_course=source_course,
                row=raw_payload,
                course_id=course_id,
                spot_id=spot_id,
                base_date=base_date,
                base_time=base_time,
                forecast_date=forecast_date,
                forecast_time=forecast_time,
                category_code=category_code,
                collected_at=resolved_collected_at,
            )
            serving_count += 1
    session.flush()
    return KmaTourCourseWeatherLoadResult(
        target_count=len(targets),
        course_count=len(courses),
        raw_row_count=raw_count,
        serving_row_count=serving_count,
        skipped_row_count=skipped_count,
    )


def parse_kma_tour_course_bytes(*, source_file_name: str, data: bytes) -> KmaTourCourseParseResult:
    csv_file_name, csv_bytes = _extract_csv(source_file_name=source_file_name, data=data)
    errors: list[str] = []
    for encoding in ("cp949", "ms949", "utf-8-sig"):
        try:
            text = csv_bytes.decode(encoding)
            rows = list(csv.DictReader(io.StringIO(text)))
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
            continue
        if not rows:
            return KmaTourCourseParseResult(
                rows=[], source_encoding=encoding, csv_file_name=csv_file_name
            )
        missing = EXPECTED_COLUMNS - set(rows[0])
        if missing:
            raise ValueError(f"KMA tour course CSV is missing columns: {sorted(missing)}")
        return KmaTourCourseParseResult(
            rows=[
                {str(key): str(value or "").strip() for key, value in row.items()} for row in rows
            ],
            source_encoding=encoding,
            csv_file_name=csv_file_name,
        )
    joined_errors = "; ".join(errors)
    raise UnicodeDecodeError("kma_tour_course", csv_bytes, 0, len(csv_bytes), joined_errors)


def _extract_csv(*, source_file_name: str, data: bytes) -> tuple[str, bytes]:
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not names:
                raise ValueError("KMA tour course ZIP does not contain a CSV file.")
            selected = sorted(names)[0]
            return selected, archive.read(selected)
    return source_file_name, data


def _select_courses_near_targets(
    session: Session,
    *,
    targets: list[KmaTourCourseWeatherTarget],
    max_courses: int,
) -> list[KmaRecommendedTourCourse]:
    if not targets:
        return []
    courses = list(
        session.scalars(
            select(KmaRecommendedTourCourse).order_by(
                KmaRecommendedTourCourse.course_id,
                KmaRecommendedTourCourse.course_order,
                KmaRecommendedTourCourse.spot_id,
            )
        )
    )
    matched: list[tuple[float, KmaRecommendedTourCourse]] = []
    seen_ids: set[tuple[str, str]] = set()
    normalized_targets = [
        (
            float(_decimal(target.longitude)),
            float(_decimal(target.latitude)),
            float(_decimal(target.radius_km)),
        )
        for target in targets
    ]
    for course in courses:
        course_key = (course.course_id, course.spot_id)
        if course_key in seen_ids:
            continue
        lon = float(course.longitude)
        lat = float(course.latitude)
        distances = [
            _haversine_km(lon1=lon, lat1=lat, lon2=target_lon, lat2=target_lat)
            for target_lon, target_lat, _radius_km in normalized_targets
        ]
        min_distance = min(distances)
        if any(
            distance <= radius_km
            for distance, (_target_lon, _target_lat, radius_km) in zip(
                distances,
                normalized_targets,
                strict=True,
            )
        ):
            matched.append((min_distance, course))
            seen_ids.add(course_key)
    matched.sort(key=lambda item: (item[0], item[1].course_id, item[1].course_order or 0))
    return [course for _distance, course in matched[:max_courses]]


def _upsert_tour_course_spot_weather(
    session: Session,
    *,
    source_course: KmaRecommendedTourCourse | None,
    row: dict[str, Any],
    course_id: str,
    spot_id: str | None,
    base_date: str | None,
    base_time: str | None,
    forecast_date: str | None,
    forecast_time: str | None,
    category_code: str,
    collected_at: datetime,
) -> TourCourseServingKmaSpotWeather:
    existing = session.scalar(
        select(TourCourseServingKmaSpotWeather)
        .where(TourCourseServingKmaSpotWeather.course_id == course_id)
        .where(TourCourseServingKmaSpotWeather.spot_id == spot_id)
        .where(TourCourseServingKmaSpotWeather.base_date == base_date)
        .where(TourCourseServingKmaSpotWeather.base_time == base_time)
        .where(TourCourseServingKmaSpotWeather.forecast_date == forecast_date)
        .where(TourCourseServingKmaSpotWeather.forecast_time == forecast_time)
        .where(TourCourseServingKmaSpotWeather.category_code == category_code)
    )
    category_name, normalized_category, unit = TOUR_WEATHER_CATEGORY_SPECS.get(
        category_code,
        (category_code, "unknown", None),
    )
    values = {
        "endpoint": KMA_TOUR_SPOT_WEATHER_ENDPOINT,
        "source_file_hash": source_course.source_file_hash if source_course else None,
        "theme_category_code": source_course.theme_category_code if source_course else None,
        "spot_name": (
            source_course.spot_name if source_course else _optional_text_any(row, "spotName")
        ),
        "longitude": source_course.longitude if source_course else None,
        "latitude": source_course.latitude if source_course else None,
        "legal_dong_code": source_course.legal_dong_code if source_course else None,
        "sigungu_code": source_course.sigungu_code if source_course else None,
        "sido_code": source_course.sido_code if source_course else None,
        "category_name": category_name,
        "normalized_category": normalized_category,
        "value": (
            _optional_text_any(row, "fcstValue") or _optional_text_any(row, "obsrValue") or ""
        ),
        "unit": unit,
        "raw_payload": dict(row),
        "collected_at": collected_at,
    }
    if existing is None:
        existing = TourCourseServingKmaSpotWeather(
            course_id=course_id,
            spot_id=spot_id,
            base_date=base_date,
            base_time=base_time,
            forecast_date=forecast_date,
            forecast_time=forecast_time,
            category_code=category_code,
            **values,
        )
        session.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    return existing


def _haversine_km(*, lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    earth_radius_km = 6371.0088
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * earth_radius_km * math.asin(math.sqrt(haversine))


def _find_legal_boundary(
    session: Session,
    *,
    longitude: Decimal,
    latitude: Decimal,
) -> RegionServingBoundary | None:
    point = func.ST_SetSRID(func.ST_MakePoint(float(longitude), float(latitude)), 4326)
    return session.scalar(
        select(RegionServingBoundary)
        .where(RegionServingBoundary.boundary_level == "legal_dong")
        .where(func.ST_Covers(RegionServingBoundary.geom, point))
        .order_by(func.ST_Area(RegionServingBoundary.geom))
        .limit(1)
    )


def _required_text(row: dict[str, str], key: str) -> str:
    value = _optional_text(row, key)
    if value is None:
        raise ValueError(f"KMA tour course row is missing required field {key}.")
    return value


def _optional_text(row: dict[str, str], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None


def _optional_text_any(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _decimal(value: Decimal | float | str | Any) -> Decimal:
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"value must be decimal-compatible: {value!r}") from exc


def _resolve_collected_at(collected_at: datetime | None) -> datetime:
    if collected_at is None:
        return datetime.now(KST)
    if collected_at.tzinfo is None:
        return collected_at.replace(tzinfo=KST)
    return collected_at


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()
