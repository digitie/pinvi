"""Map `visitor_info`(ADR-125) → 상세 카드 `introduction`·`visit_guide` 투영과 장소 영업 정보 추출."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.schemas.feature import EventDetailCard, PlaceDetailCard
from app.services.feature_detail import build_detail_card
from app.services.poi_place_details import extract_place_details
from app.services.source_introduction import (
    image_license_type,
    source_image_url,
    visit_guide,
    visitor_introduction,
)

_IMG1 = "https://tong.visitkorea.or.kr/cms/resource/01/1_image2_1.jpg"
_IMG2 = "http://tong.visitkorea.or.kr/cms/resource/02/2_image2_1.jpg"


def _license(kogl: int, *, attribution: str = "한국관광공사") -> dict[str, Any]:
    return {
        "attribution": attribution,
        "kogl_type": kogl,
        "label": f"공공누리 제{kogl}유형",
        "derivatives_allowed": kogl in (0, 1, 2),
        "commercial_allowed": kogl in (0, 1, 3),
    }


def _tourapi_info(**over: Any) -> dict[str, Any]:
    info: dict[str, Any] = {
        "source": "tourapi",
        "attribution": "한국관광공사",
        "description": "괴산호를 따라 이어진 옛길이다.\n산막이마을까지 걷는다.",
        "usage_hours": "09:00~18:00<br>(입장마감 17:00)",
        "rest_days": "연중무휴",
        "parking": "가능(대형 20대)",
        "parking_fee": "소형 3,000원",
        "fee_text": "무료",
        "inquiry": "043-830-3114",
        "pet_note": "불가",
        "images": [
            {"url": _IMG1, "thumbnail_url": _IMG1, "license": _license(3)},
            {"url": _IMG2, "caption": "산막이옛길 출렁다리", "license": _license(1)},
        ],
        "accessibility": [
            {
                "group": "physical",
                "facility": "parking",
                "label": "주차",
                "text": "장애인 주차 2면",
            },
            {"group": "visual", "facility": "braile_block", "label": "점자블록", "text": "입구"},
        ],
        "pet_policy": {"companion_type": "일부구역 동반가능", "allowed_pets": "소형견"},
    }
    info.update(over)
    return {key: value for key, value in info.items() if value is not None}


def _dto(info: dict[str, Any] | None, *, kind: str = "place", **over: Any) -> dict[str, Any]:
    dto: dict[str, Any] = {
        "feature_id": "01a1c43c-f414-77d4-8e4e-addb3b650f56",
        "kind": kind,
        "name": "산막이옛길",
        "category": "01080500",
        "lon": 127.87,
        "lat": 36.76,
        "address": {"road": "충북 괴산군 칠성면 산막이옛길 88"},
        "urls": {},
        "detail": {"facility_info": {}},
        "visitor_info": info,
    }
    dto.update(over)
    return dto


# ── 출처 소개(introduction) ───────────────────────────────────────────────


def test_tourapi_gallery_keeps_per_image_license_and_https_upgrade() -> None:
    intro = visitor_introduction(_tourapi_info(), name="산막이옛길")
    assert intro is not None
    assert intro.provider == "tourapi"
    assert intro.attribution == "한국관광공사"
    assert intro.overview == "괴산호를 따라 이어진 옛길이다.\n산막이마을까지 걷는다."
    first, second = intro.images
    assert (first.url, first.alt, first.kogl_type, first.no_derivatives) == (
        _IMG1,
        "산막이옛길 대표 사진",
        3,
        True,
    )
    assert first.license_label == "공공누리 제3유형: 출처표시 + 변경금지"
    assert first.license_url == "https://www.kogl.or.kr/info/licenseType3.do"
    # 갤러리 이미지는 다른 유형일 수 있다 — 이미지마다 따로 붙는다. http는 같은 주소 https로.
    assert second.url == _IMG2.replace("http://", "https://")
    assert second.alt == "산막이옛길 출렁다리"
    assert (second.kogl_type, second.no_derivatives) == (1, False)
    assert second.license_url == "https://www.kogl.or.kr/info/licenseType1.do"


def test_gallery_is_capped_at_ten_and_deduplicated() -> None:
    images = [
        {"url": f"https://tong.visitkorea.or.kr/cms/{i}.jpg", "license": _license(1)}
        for i in range(14)
    ]
    images.insert(1, dict(images[0]))
    intro = visitor_introduction(_tourapi_info(images=images), name="x")
    assert intro is not None
    assert len(intro.images) == 10
    assert len({image.url for image in intro.images}) == 10
    assert intro.images[1].alt == "x 사진 2"


@pytest.mark.parametrize(
    "license_value",
    [
        None,
        {},
        _license(2),  # 상업적 이용금지 — PinVi 상업성 판단 전까지 싣지 않는다.
        _license(4),
        {**_license(3), "derivatives_allowed": True},  # 유형과 모순
        {**_license(1), "commercial_allowed": False},
        {**_license(1), "kogl_type": 5},
        {**_license(1), "kogl_type": True},
        {**_license(1), "kogl_type": "1"},
    ],
)
def test_image_license_fails_closed(license_value: Any) -> None:
    assert image_license_type(license_value) is None
    intro = visitor_introduction(
        _tourapi_info(images=[{"url": _IMG1, "license": license_value}]), name="x"
    )
    assert intro is not None
    assert intro.images == []
    assert intro.overview is not None


def test_kogl_type0_is_labeled_free_use() -> None:
    assert image_license_type(_license(0)) == 0
    intro = visitor_introduction(
        _tourapi_info(images=[{"url": _IMG1, "license": _license(0)}]), name="x"
    )
    assert intro is not None
    assert intro.images[0].license_label == "공공누리 제0유형: 자유이용"
    assert intro.images[0].license_url == "https://www.kogl.or.kr/info/licenseType0.do"
    assert intro.images[0].no_derivatives is False


def test_disallowed_image_host_dropped() -> None:
    intro = visitor_introduction(
        _tourapi_info(images=[{"url": "https://evil.example/a.jpg", "license": _license(1)}]),
        name="x",
    )
    assert intro is not None
    assert intro.images == []


def test_heritage_description_only_never_images() -> None:
    """국가유산 이미지는 라이선스 코드 미확인 — Map이 실어도 PinVi는 허용 호스트가 없어 싣지 않는다."""
    info = {
        "source": "krheritage",
        "attribution": "다른 문구",
        "description": "<삼국유사>에 전하는 절터이다.",
        "images": [{"url": "https://www.khs.go.kr/a.jpg", "license": _license(1)}],
    }
    intro = visitor_introduction(info, name="황룡사지")
    assert intro is not None
    assert intro.provider == "krheritage"
    # 출처는 원천별 고정 문구 — Map 값으로 바꾸지 않는다.
    assert intro.attribution == "국가유산청, www.khs.go.kr"
    assert intro.overview == "<삼국유사>에 전하는 절터이다."
    assert intro.images == []
    assert source_image_url("krheritage", "https://www.khs.go.kr/a.jpg") is None


def test_heritage_flat_image_url_is_ignored_when_visitor_info_present() -> None:
    dto = _dto(
        {"source": "krheritage", "attribution": "국가유산청", "description": "설명"},
        detail={"facility_info": {"image_url": "https://www.khs.go.kr/a.jpg"}},
    )
    card = build_detail_card(dto)
    assert isinstance(card, PlaceDetailCard)
    assert card.introduction is not None
    assert card.introduction.images == []


def test_museum_and_forest_sources() -> None:
    museum = visitor_introduction(
        {
            "source": "datagokr_museum",
            "attribution": "x",
            "description": "근현대 미술 소장품",
            "reference_date": "2026-05-31",
        },
        name="미술관",
    )
    assert museum is not None
    assert museum.attribution == "공공데이터포털 전국박물관미술관정보표준데이터"
    assert museum.reference_date == date(2026, 5, 31)
    guide = visit_guide(
        {
            "source": "krforest_recreation_forest",
            "attribution": "x",
            "fee_text": "어른 1,000원",
            "facilities": "숲속의집\n산책로",
            "capacity": "300명",
            "accommodation_available": True,
        }
    )
    assert guide is not None
    assert guide.attribution == "공공데이터포털 전국휴양림표준데이터"
    assert guide.facilities == "숲속의집\n산책로"
    assert guide.accommodation_available is True


def test_unknown_source_is_not_projected() -> None:
    info = {"source": "new_source", "attribution": "x", "description": "소개", "fee_text": "무료"}
    assert visitor_introduction(info, name="x") is None
    assert visit_guide(info) is None


def test_nothing_to_show_is_none() -> None:
    info = {"source": "tourapi", "attribution": "한국관광공사"}
    assert visitor_introduction(info, name="x") is None
    assert visit_guide(info) is None


# ── 이용 안내(visit_guide) ───────────────────────────────────────────────


def test_visit_guide_fields_badges_and_text_cleanup() -> None:
    guide = visit_guide(_tourapi_info())
    assert guide is not None
    assert guide.provider == "tourapi"
    assert guide.attribution == "한국관광공사"
    assert guide.usage_hours == "09:00~18:00\n(입장마감 17:00)"
    assert guide.rest_days == "연중무휴"
    assert guide.parking_fee == "소형 3,000원"
    assert guide.pet_note == "불가"
    assert [(a.group, a.facility, a.label) for a in guide.accessibility] == [
        ("physical", "parking", "주차"),
        ("visual", "braile_block", "점자블록"),
    ]
    assert guide.pet_policy is not None
    assert guide.pet_policy.allowed_pets == "소형견"
    assert guide.pet_policy.notes is None


def test_visit_guide_fees_ignore_unknown_and_invalid() -> None:
    guide = visit_guide(
        {
            "source": "datagokr_museum",
            "attribution": "x",
            "fees": [
                {"audience": "adult", "amount_krw": 2000},
                {"audience": "senior", "amount_krw": 500},
                {"audience": "youth", "amount_krw": True},
                {"audience": "youth", "amount_krw": 1000},
                {"audience": "adult", "amount_krw": 3000},
                {"audience": "child", "amount_krw": 0},
            ],
        }
    )
    assert guide is not None
    assert [(fee.audience, fee.amount_krw) for fee in guide.fees] == [
        ("adult", 2000),
        ("youth", 1000),
        ("child", 0),
    ]


def test_visit_guide_drops_unknown_accessibility_and_empty_pet_policy() -> None:
    guide = visit_guide(
        {
            "source": "tourapi",
            "attribution": "x",
            "accessibility": [
                {"group": "elderly", "facility": "x", "label": "x", "text": "x"},
                {"group": "hearing", "facility": "Bad-Code", "label": "x", "text": "x"},
                {"group": "hearing", "facility": "guide", "label": " ", "text": "x"},
                {
                    "group": "infant_family",
                    "facility": "stroller",
                    "label": "유모차",
                    "text": "대여",
                },
            ],
            "pet_policy": {"notes": "  "},
        }
    )
    assert guide is not None
    assert [a.facility for a in guide.accessibility] == ["stroller"]
    assert guide.pet_policy is None


def test_visit_guide_overlong_text_omitted_not_truncated() -> None:
    guide = visit_guide(
        {"source": "tourapi", "attribution": "x", "parking": "가" * 2001, "inquiry": "문의"}
    )
    assert guide is not None
    assert guide.parking is None
    assert guide.inquiry == "문의"


# ── 상세 카드 ──────────────────────────────────────────────────────────


def test_place_card_prefers_visitor_info_over_flat_keys() -> None:
    dto = _dto(
        _tourapi_info(),
        detail={
            "facility_info": {
                "tourapi_content_id": "1",
                "overview": "옛 평면 소개",
                "image_url": "https://tong.visitkorea.or.kr/old.jpg",
                "license": "Type1",
            }
        },
    )
    card = build_detail_card(dto)
    assert isinstance(card, PlaceDetailCard)
    assert card.introduction is not None
    assert card.introduction.overview == "괴산호를 따라 이어진 옛길이다.\n산막이마을까지 걷는다."
    assert card.introduction.images[0].url == _IMG1
    assert card.visit_guide is not None
    dumped = card.model_dump(mode="json")
    assert dumped["visit_guide"]["accessibility"][0]["label"] == "주차"
    assert dumped["introduction"]["images"][0]["license_label"].startswith("공공누리 제3유형")


def test_place_card_falls_back_to_flat_keys_without_visitor_info() -> None:
    dto = _dto(
        None,
        detail={
            "facility_info": {
                "tourapi_content_id": "1",
                "overview": "옛 평면 소개",
                "image_url": "http://tong.visitkorea.or.kr/old.jpg",
                "license": "Type3",
            }
        },
    )
    del dto["visitor_info"]
    card = build_detail_card(dto)
    assert isinstance(card, PlaceDetailCard)
    assert card.introduction is not None
    assert card.introduction.overview == "옛 평면 소개"
    assert card.introduction.images[0].url == "https://tong.visitkorea.or.kr/old.jpg"
    assert card.introduction.images[0].no_derivatives is True
    assert card.visit_guide is None


def test_festival_event_card_gets_introduction() -> None:
    info = {
        "source": "tourapi",
        "attribution": "한국관광공사",
        "description": "벚꽃이 피는 봄 축제",
        "images": [{"url": _IMG1, "license": _license(1)}],
    }
    card = build_detail_card(_dto(info, kind="event", name="진해군항제"))
    assert isinstance(card, EventDetailCard)
    assert card.introduction is not None
    assert card.introduction.overview == "벚꽃이 피는 봄 축제"
    assert card.introduction.images[0].alt == "진해군항제 대표 사진"
    assert card.visit_guide is None


def test_event_without_visitor_info_has_no_introduction() -> None:
    card = build_detail_card(_dto(None, kind="event"))
    assert isinstance(card, EventDetailCard)
    assert card.introduction is None
    assert card.visit_guide is None


# ── 여행 장소 영업 정보(trip_poi_place_details) ─────────────────────────────


_TODAY = date(2026, 11, 27)


def test_place_details_read_hours_and_rest_days_from_visitor_info() -> None:
    dto = _dto(
        _tourapi_info(),
        detail={"facility_info": {"usetime": "옛 평면 시간", "restdate": "옛 평면 휴무"}},
    )
    extracted = extract_place_details(dto, today=_TODAY)
    assert extracted.opening_hours == ["09:00~18:00\n(입장마감 17:00)"]
    assert extracted.closed_days == "연중무휴"
    assert extracted.sources()["opening_hours"] == "kor_travel_map"


def test_place_details_structured_hours_still_win() -> None:
    dto = _dto(
        _tourapi_info(rest_days=None),
        detail={
            "business_hours": {"weekday_text": ["월요일: 09:00~18:00"]},
            "facility_info": {},
        },
    )
    extracted = extract_place_details(dto, today=_TODAY)
    assert extracted.opening_hours == ["월요일: 09:00~18:00"]


def test_place_details_fall_back_to_flat_keys_without_visitor_info() -> None:
    dto = _dto(None, detail={"facility_info": {"usetime": "10:00~17:00", "restdate": "월요일"}})
    extracted = extract_place_details(dto, today=_TODAY)
    assert extracted.opening_hours == ["10:00~17:00"]
    assert extracted.closed_days == "월요일"
