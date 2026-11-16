"""Map feature dto → 장소 영업 정보 추출(`extract_place_details`)."""

from __future__ import annotations

from datetime import date

from app.services.poi_place_details import extract_place_details

TODAY = date(2026, 11, 16)


def test_structured_hours_with_weekday_text_and_closed_weekday() -> None:
    dto = {
        "detail": {
            "phones": ["054-123-4567"],
            "business_hours": {
                "timezone": "Asia/Seoul",
                "periods": [
                    {"open": {"day": d, "time": "0900"}, "close": {"day": d, "time": "1800"}}
                    for d in (0, 2, 3, 4, 5, 6)
                ],
                "special_days": [
                    {"date": "2026-12-25", "is_closed": True},
                    {"date": "2026-01-01", "is_closed": True},  # 지난 날짜는 빼고
                    {"date": "2026-12-31", "is_closed": False},
                ],
                "weekday_text": ["월요일: 휴무", "화요일: 09:00~18:00"],
            },
        },
        "urls": {"homepage": "https://example.go.kr"},
    }
    extracted = extract_place_details(dto, today=TODAY)
    assert extracted.opening_hours == ["월요일: 휴무", "화요일: 09:00~18:00"]
    assert extracted.closed_days == "매주 월요일 · 12월 25일 휴무"
    assert extracted.phone == "054-123-4567"
    assert extracted.website == "https://example.go.kr"
    assert extracted.sources() == {
        "opening_hours": "kor_travel_map",
        "closed_days": "kor_travel_map",
        "phone": "kor_travel_map",
        "website": "kor_travel_map",
    }
    assert not extracted.empty


def test_periods_without_weekday_text_are_rendered_monday_first() -> None:
    dto = {
        "detail": {
            "business_hours": {
                "periods": [
                    {"open": {"day": 1, "time": "1000"}, "close": {"day": 1, "time": "1400"}},
                    {"open": {"day": 1, "time": "1700"}, "close": {"day": 1, "time": "2100"}},
                    {"open": {"day": 6, "time": "1000"}},
                ]
            }
        }
    }
    extracted = extract_place_details(dto, today=TODAY)
    assert extracted.opening_hours[0] == "월요일: 10:00~14:00, 17:00~21:00"
    assert extracted.opening_hours[5] == "토요일: 10:00~"
    assert extracted.opening_hours[6] == "일요일: 휴무"
    assert extracted.closed_days == "매주 화요일, 수요일, 목요일, 금요일, 일요일"


def test_always_open() -> None:
    dto = {"detail": {"business_hours": {"periods": [{"open": {"day": 0, "time": "0000"}}]}}}
    extracted = extract_place_details(dto, today=TODAY)
    assert extracted.opening_hours == ["매일 24시간 영업"]
    assert extracted.closed_days == "연중무휴"


def test_source_text_fields_and_facility_fallbacks() -> None:
    dto = {
        "detail": {
            "facility_info": {
                "operating_time": "09:00~18:00 (입장 마감 17:00)",
                "rstde_info": "매주 월요일, 1월 1일",
                "tel": "02-000-0000",
                "url": "http://museum.example",
            }
        },
        "urls": {},
    }
    extracted = extract_place_details(dto, today=TODAY)
    assert extracted.opening_hours == ["09:00~18:00 (입장 마감 17:00)"]
    assert extracted.closed_days == "매주 월요일, 1월 1일"
    assert extracted.phone == "02-000-0000"
    assert extracted.website == "http://museum.example"


def test_nothing_known_is_empty_and_not_guessed() -> None:
    extracted = extract_place_details(
        {"detail": {"business_hours": {"periods": []}}, "urls": {"homepage": "ftp://x"}},
        today=TODAY,
    )
    assert extracted.empty
    assert extracted.closed_days is None
    assert extracted.sources() == {}
