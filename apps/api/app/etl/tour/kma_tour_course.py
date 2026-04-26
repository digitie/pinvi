from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.address import RegionServingBoundary
from app.models.tour import KmaRecommendedTourCourse, TourCourseRawKmaPoint

MARKER_SOURCE_TYPE = "kma_recommended_tour_course"
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
