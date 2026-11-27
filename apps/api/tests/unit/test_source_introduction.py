"""`app.services.source_introduction` 단위 테스트 — TourAPI 소개문·대표 이미지·출처/공공누리 투영."""

from __future__ import annotations

from typing import Any

import pytest

from app.schemas.feature import PlaceDetailCard
from app.services.feature_detail import build_detail_card
from app.services.source_introduction import (
    kogl_type,
    plain_overview,
    tourapi_image_url,
    tourapi_introduction,
)

_IMAGE = "https://tong.visitkorea.or.kr/cms/resource/29/3488229_image2_1.jpg"


def _facility(**over: Any) -> dict[str, Any]:
    # prod Map `/v1/features/{id}` 산막이옛길(2026-11-27) facility_info 모양.
    base: dict[str, Any] = {
        "tourapi_content_id": "1948361",
        "tourapi_content_type_id": "28",
        "lcls_systm3": "LS011900",
        "overview": "괴산호를 따라 이어진 옛길이다.\n산막이마을까지 걷는다.",
        "image_url": _IMAGE,
        "thumbnail_url": "https://tong.visitkorea.or.kr/cms/resource/29/3488229_image3_1.jpg",
        "attribution": "한국관광공사",
        "license": "공공누리 제3유형(출처표시·변경금지)",
        "modified_time": "2026-11-11T08:48:02+09:00",
    }
    base.update(over)
    return {key: value for key, value in base.items() if value is not None}


def _detail(**over: Any) -> dict[str, Any]:
    return {"place_kind": "tourapi_leisure", "facility_info": _facility(**over)}


def test_type3_image_overview_and_attribution() -> None:
    intro = tourapi_introduction(_detail(), name="산막이옛길")
    assert intro is not None
    assert intro.provider == "tourapi"
    assert intro.attribution == "한국관광공사"
    assert intro.overview == "괴산호를 따라 이어진 옛길이다.\n산막이마을까지 걷는다."
    assert len(intro.images) == 1
    image = intro.images[0]
    # 원천이 만든 작은 사본(thumbnail_url)이 아니라 원본을 그대로 쓴다.
    assert image.url == _IMAGE
    assert image.alt == "산막이옛길 대표 사진"
    assert image.kogl_type == 3
    assert image.no_derivatives is True
    assert intro.kogl_type == 3
    assert intro.license_label == "공공누리 제3유형: 출처표시 + 변경금지"
    assert intro.license_url == "https://www.kogl.or.kr/info/licenseType3.do"


def test_type1_image_allows_derivatives_flag_false() -> None:
    intro = tourapi_introduction(_detail(license="공공누리 제1유형(출처표시)"), name="부산타워")
    assert intro is not None
    assert intro.images[0].kogl_type == 1
    assert intro.images[0].no_derivatives is False
    assert intro.license_url == "https://www.kogl.or.kr/info/licenseType1.do"


def test_raw_type_codes_are_understood() -> None:
    assert kogl_type("Type1") == 1
    assert kogl_type("Type3") == 3
    assert kogl_type("공공누리 제 3 유형") == 3
    assert kogl_type("Type2") is None
    assert kogl_type("") is None
    assert kogl_type(None) is None


def test_unknown_license_drops_image_but_keeps_overview() -> None:
    """이용 조건을 모르는 이미지는 싣지 않는다 — 소개문과 출처는 남는다."""
    intro = tourapi_introduction(_detail(license=None), name="남산서울타워")
    assert intro is not None
    assert intro.images == []
    assert intro.overview is not None
    assert intro.kogl_type is None
    assert intro.license_label is None
    assert intro.license_url is None


def test_overview_only_has_no_license_mark() -> None:
    intro = tourapi_introduction(_detail(image_url=None), name="남산서울타워")
    assert intro is not None
    assert intro.images == []
    assert intro.license_label is None
    assert intro.attribution == "한국관광공사"


def test_image_only_without_overview() -> None:
    intro = tourapi_introduction(_detail(overview=None), name="부산타워")
    assert intro is not None
    assert intro.overview is None
    assert len(intro.images) == 1


def test_nothing_to_show_is_none() -> None:
    assert tourapi_introduction(_detail(overview=None, image_url=None), name="x") is None
    assert tourapi_introduction(_detail(overview="  ", license=None), name="x") is None


@pytest.mark.parametrize(
    "detail",
    [
        None,
        "x",
        {},
        {"facility_info": None},
        # MOIS·표준데이터 등 다른 출처 행 — 같은 키 이름이 있어도 TourAPI 출처로 표시하지 않는다.
        {"facility_info": {"overview": "소개", "image_url": _IMAGE, "license": "Type1"}},
    ],
)
def test_non_tourapi_rows_are_ignored(detail: Any) -> None:
    assert tourapi_introduction(detail, name="x") is None


def test_missing_attribution_falls_back_to_kto() -> None:
    intro = tourapi_introduction(_detail(attribution=None), name="x")
    assert intro is not None
    assert intro.attribution == "한국관광공사"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (_IMAGE, _IMAGE),
        # 원천이 http로 주면 같은 주소의 https로 올린다(혼합 콘텐츠 차단 회피).
        ("http://tong.visitkorea.or.kr/cms/a.jpg", "https://tong.visitkorea.or.kr/cms/a.jpg"),
        ("HTTPS://TONG.visitkorea.or.kr/a.jpg#frag", "https://tong.visitkorea.or.kr/a.jpg"),
        ("https://evil.example/a.jpg", None),
        ("https://visitkorea.or.kr.evil.example/a.jpg", None),
        ("https://user:pw@tong.visitkorea.or.kr/a.jpg", None),
        ("https://tong.visitkorea.or.kr:8443/a.jpg", None),
        ("javascript:alert(1)//.visitkorea.or.kr", None),
        ("data:image/png;base64,AAAA", None),
        ("//tong.visitkorea.or.kr/a.jpg", None),
        ("https://tong.visitkorea.or.kr/a b.jpg", None),
        ("", None),
        (None, None),
        (123, None),
    ],
)
def test_image_url_allowlist(raw: Any, expected: str | None) -> None:
    assert tourapi_image_url(raw) == expected


def test_disallowed_image_host_is_dropped() -> None:
    intro = tourapi_introduction(_detail(image_url="https://evil.example/a.jpg"), name="x")
    assert intro is not None
    assert intro.images == []
    assert intro.license_label is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("첫 줄<br>둘째 줄", "첫 줄\n둘째 줄"),
        ("<p>본문</p><script>alert(1)</script>", "본문alert(1)"),
        ('<img src=x onerror="alert(1)">사진', "사진"),
        # 태그 꼴이 아닌 부등호는 본문이라 남긴다(화면이 텍스트로 이스케이프한다).
        ("a < b > c", "a < b > c"),
        ("1 <2", "1 <2"),
        ("  여러   칸\t공백  ", "여러 칸 공백"),
        ("줄1\n\n\n\n줄2", "줄1\n\n줄2"),
        ("\n\n앞뒤 빈 줄\n\n", "앞뒤 빈 줄"),
        ("제어\u0000문자\u202e뒤집기\u200b", "제어문자뒤집기"),
        ("윈도\r\n줄바꿈", "윈도\n줄바꿈"),
        ("", None),
        ("<br><br>", None),
        (None, None),
    ],
)
def test_plain_overview_sanitizes(raw: Any, expected: str | None) -> None:
    assert plain_overview(raw) == expected


def test_overlong_overview_is_omitted_not_truncated() -> None:
    """자르면 제3유형(변경금지) 본문을 바꾸는 셈이라 너무 긴 소개문은 통째로 뺀다."""
    assert plain_overview("가" * 20001) is None
    assert plain_overview("가" * 20000) == "가" * 20000


def test_long_name_alt_fits_schema() -> None:
    intro = tourapi_introduction(_detail(), name="가" * 500)
    assert intro is not None
    assert len(intro.images[0].alt) <= 200


def test_build_detail_card_carries_introduction() -> None:
    dto = {
        "feature_id": "01a1c43c-f414-77d4-8e4e-addb3b650f56",
        "kind": "place",
        "name": "산막이옛길",
        "category": "01080500",
        "lon": 127.87,
        "lat": 36.76,
        "address": {"road": "충북 괴산군 칠성면 산막이옛길 88"},
        "urls": {},
        "detail": _detail(),
    }
    card = build_detail_card(dto)
    assert isinstance(card, PlaceDetailCard)
    assert card.introduction is not None
    assert card.introduction.images[0].no_derivatives is True
    dumped = card.model_dump(mode="json")
    assert dumped["introduction"]["attribution"] == "한국관광공사"


def test_build_detail_card_without_tourapi_has_null_introduction() -> None:
    dto = {
        "feature_id": "place:1",
        "kind": "place",
        "name": "스타벅스 광안리",
        "urls": {},
        "detail": {"phone": "051-000-0000"},
    }
    card = build_detail_card(dto)
    assert isinstance(card, PlaceDetailCard)
    assert card.introduction is None
    assert card.model_dump(mode="json")["introduction"] is None
