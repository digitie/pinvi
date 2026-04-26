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
    load_kma_tour_course_bytes,
    parse_kma_tour_course_bytes,
)
from app.models.tour import KmaRecommendedTourCourse, TourCourseRawKmaPoint

KST = ZoneInfo("Asia/Seoul")


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


def _sample_csv_text() -> str:
    return (
        "테마분류,코스 아이디,관광지 아이디,지역 아이디,관광지명,경도(도),위도(도),"
        "코스순서,이동시간,실내구분,테마명\n"
        "TH05,177,17703,4822051000,(통영)세병관(통제영지),128.423238,34.847749,"
        "3,2,실외,종교/역사/전통\n"
        "TH05,177,17704,4822051000,(통영)충렬사,128.417847,34.846626,"
        "4,3,실외,종교/역사/전통\n"
    )
