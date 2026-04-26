from __future__ import annotations

import io
import zipfile
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.etl.tour.kma_tour_course import (
    MARKER_SOURCE_TYPE,
    KmaTourCourseWeatherTarget,
    load_kma_tour_course_bytes,
    load_kma_tour_course_weather_for_nearby_targets,
    parse_kma_tour_course_bytes,
)
from app.models.tour import (
    KmaRecommendedTourCourse,
    TourCourseRawKmaPoint,
    TourCourseRawKmaSpotWeather,
    TourCourseServingKmaSpotWeather,
)

KST = ZoneInfo("Asia/Seoul")


class FakeKmaTourWeatherClient:
    def fetch_tour_spot_weather(self, *, course_id: str) -> list[dict[str, str]]:
        assert course_id == "177"
        return [
            {
                "courseId": "177",
                "spotId": "17703",
                "baseDate": "20260426",
                "baseTime": "1200",
                "fcstDate": "20260426",
                "fcstTime": "1500",
                "category": "TMP",
                "fcstValue": "22",
            },
            {
                "courseId": "177",
                "spotId": "17703",
                "baseDate": "20260426",
                "baseTime": "1200",
                "fcstDate": "20260426",
                "fcstTime": "1500",
                "fcstValue": "ignored",
            },
        ]


def test_kma_tour_course_loader_decodes_cp949_and_replaces_same_file(
    db_session: Session,
) -> None:
    data = _sample_csv_text().encode("cp949")

    first_result = load_kma_tour_course_bytes(
        db_session,
        source_file_name="kma-tour.csv",
        data=data,
        collected_at=datetime(2026, 4, 26, 13, 0, tzinfo=KST),
    )
    second_result = load_kma_tour_course_bytes(
        db_session,
        source_file_name="kma-tour.csv",
        data=data,
        collected_at=datetime(2026, 4, 26, 13, 10, tzinfo=KST),
    )
    db_session.commit()

    serving_rows = db_session.scalars(
        select(KmaRecommendedTourCourse).order_by(KmaRecommendedTourCourse.course_order)
    ).all()

    assert first_result.raw_row_count == 2
    assert first_result.serving_row_count == 2
    assert first_result.source_encoding == "cp949"
    assert second_result.raw_row_count == 2
    assert db_session.scalars(select(TourCourseRawKmaPoint)).all()
    assert len(db_session.scalars(select(TourCourseRawKmaPoint)).all()) == 2
    assert len(serving_rows) == 2
    assert [(row.course_id, row.spot_id, row.course_order) for row in serving_rows] == [
        ("177", "17703", 3),
        ("177", "17704", 4),
    ]
    assert serving_rows[0].theme_category == "history_tradition"
    assert serving_rows[0].longitude == Decimal("128.42323800")
    assert serving_rows[0].latitude == Decimal("34.84774900")
    assert serving_rows[0].address_mapping_method == "unmapped"
    assert serving_rows[0].address_snapshot is None
    assert serving_rows[0].marker_source_type == MARKER_SOURCE_TYPE


def test_kma_tour_course_parser_reads_first_csv_from_zip() -> None:
    data = _sample_csv_text().encode("cp949")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("nested/kma-tour.csv", data)

    parsed = parse_kma_tour_course_bytes(source_file_name="kma-tour.zip", data=buffer.getvalue())

    assert parsed.csv_file_name == "nested/kma-tour.csv"
    assert parsed.source_encoding == "cp949"
    assert parsed.rows[0]["관광지명"] == "(통영)세병관(통제영지)"


def test_kma_tour_course_weather_cache_collects_only_nearby_course_targets(
    db_session: Session,
) -> None:
    load_kma_tour_course_bytes(
        db_session,
        source_file_name="kma-tour.csv",
        data=_sample_csv_text().encode("cp949"),
        collected_at=datetime(2026, 4, 26, 13, 0, tzinfo=KST),
    )

    result = load_kma_tour_course_weather_for_nearby_targets(
        db_session,
        FakeKmaTourWeatherClient(),  # type: ignore[arg-type]
        targets=[
            KmaTourCourseWeatherTarget(
                longitude=Decimal("128.423238"),
                latitude=Decimal("34.847749"),
                radius_km=Decimal("1"),
            )
        ],
        collected_at=datetime(2026, 4, 26, 13, 10, tzinfo=KST),
    )
    db_session.commit()

    raw_row = db_session.scalar(select(TourCourseRawKmaSpotWeather))
    serving_row = db_session.scalar(select(TourCourseServingKmaSpotWeather))

    assert result.target_count == 1
    assert result.course_count == 2
    assert result.raw_row_count == 2
    assert result.serving_row_count == 1
    assert result.skipped_row_count == 1
    assert raw_row is not None
    assert serving_row is not None
    assert serving_row.course_id == "177"
    assert serving_row.spot_id == "17703"
    assert serving_row.normalized_category == "temperature"
    assert serving_row.value == "22"


def _sample_csv_text() -> str:
    return (
        "테마분류,코스 아이디,관광지 아이디,지역 아이디,관광지명,경도(도),위도(도),"
        "코스순서,이동시간,실내구분,테마명\n"
        "TH05,177,17703,4822051000,(통영)세병관(통제영지),128.423238,34.847749,"
        "3,2,실외,종교/역사/전통\n"
        "TH05,177,17704,4822051000,(통영)충렬사,128.417847,34.846626,"
        "4,3,실외,종교/역사/전통\n"
    )
