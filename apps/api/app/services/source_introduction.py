"""장소 상세의 출처 소개·이용 안내 투영 — 소개문·원본 이미지(갤러리)·출처/공공누리 + 이용시간·요금·무장애·반려동물.

정본 입력은 Map 공개 `GET /v1/features/{id}`의 최상위 `visitor_info`(`PlaceVisitorInfo`, Map ADR-125)다.
Map은 TourAPI(관광지·문화시설·레포츠·축제)·국가유산청 설명문·박물관/미술관 표준데이터·휴양림 표준데이터의
방문 안내를 이 typed 묶음 하나로 준다(원천 문장 그대로, 이미지마다 공공누리 유형). `visitor_info`가 없는
옛 Map 응답이면 #809의 평면 키(`detail.facility_info.overview`/`image_url`/`license`, TourAPI 행만)로 대신한다.

규칙(원천 이용약관 + 공공누리):

- 출처 문구는 원천마다 PinVi가 고정한다(`SOURCE_ATTRIBUTION`) — Map 값으로 바꿔 달지 않는다. 모르는 원천
  (`source`)은 출처 표시 조건을 알 수 없으므로 통째로 싣지 않는다(fail-closed).
- 이미지는 이미지마다 공공누리 유형이 확인된 것만 싣는다. 유형·변경/상업 허용 값이 서로 맞지 않거나 유형을
  모르면 싣지 않는다. 상업적 이용금지(제2·4유형)는 PinVi의 상업성 판단 전까지 싣지 않는다
  (`_SHOW_NONCOMMERCIAL_ONLY_IMAGES`).
- 변경금지(제3·4유형)는 `no_derivatives=true` — 화면이 크롭·필터 없이 원본 비율로 그린다. 서버는 이미지를
  내려받거나 줄이지 않고 원본 URL을 그대로 넘긴다(원천 썸네일 `thumbnail_url`도 쓰지 않는다).
- 이미지 주소는 원천별로 아는 호스트의 https만 허용한다(TourAPI `*.visitkorea.or.kr`). `http://`면 같은 주소의
  https로 올린다(같은 파일을 받는 경로만 바꿀 뿐 이미지 변경이 아니다). 국가유산 이미지는 라이선스 코드가
  확인되지 않아 Map이 싣지 않고, PinVi도 허용 호스트가 없어 받지 않는다(옛 `image_url`·파일 이미지 포함).
- 문장은 남은 태그 꼴·제어 문자만 걷은 평문이다(줄바꿈 보존, 요약·재작성 없음). 너무 길면 자르지 않고 뺀다.
  화면은 텍스트로만 그린다(HTML로 해석하지 않는다).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any, Final, cast, get_args
from urllib.parse import urlsplit, urlunsplit

from app.schemas.feature import (
    AccessibilityGroup,
    AccessibilityItem,
    FeeAudience,
    IntroductionProvider,
    KoglType,
    SourceImage,
    SourceIntroduction,
    VisitFee,
    VisitGuide,
    VisitPetPolicy,
)

TOURAPI_ATTRIBUTION: Final = "한국관광공사"

SOURCE_ATTRIBUTION: Final[dict[IntroductionProvider, str]] = {
    "tourapi": TOURAPI_ATTRIBUTION,
    "krheritage": "국가유산청, www.khs.go.kr",
    "datagokr_museum": "공공데이터포털 전국박물관미술관정보표준데이터",
    "krforest_recreation_forest": "공공데이터포털 전국휴양림표준데이터",
}
"""원천별 출처 표시 문구(Map ADR-125 `attribution`과 같은 값을 PinVi가 고정)."""

_IMAGE_HOST_SUFFIX: Final[dict[IntroductionProvider, str]] = {"tourapi": ".visitkorea.or.kr"}
"""원천별 이미지 허용 호스트. 여기 없는 원천의 이미지는 받지 않는다(국가유산 — 라이선스 코드 미확인)."""

_IMAGES_MAX: Final = 10
_OVERVIEW_MAX: Final = 20000
"""이보다 긴 소개문은 싣지 않는다 — 잘라 내면 변경금지 본문을 바꾸는 셈이다."""
_GUIDE_TEXT_MAX: Final = 2000
_ALT_MAX: Final = 200

_SHOW_NONCOMMERCIAL_ONLY_IMAGES: Final = False
"""공공누리 제2·4유형(상업적 이용금지) 이미지를 보일지 — PinVi의 상업성 판단(소유자) 전까지 싣지 않는다."""

_KOGL_LABEL: Final[dict[int, str]] = {
    0: "공공누리 제0유형: 자유이용",
    1: "공공누리 제1유형: 출처표시",
    2: "공공누리 제2유형: 출처표시 + 상업적 이용금지",
    3: "공공누리 제3유형: 출처표시 + 변경금지",
    4: "공공누리 제4유형: 출처표시 + 상업적 이용금지 + 변경금지",
}
_KOGL_URL: Final[dict[int, str]] = {
    kind: f"https://www.kogl.or.kr/info/licenseType{kind}.do" for kind in _KOGL_LABEL
}

_HTML_TAGS: Final = (
    "a|abbr|b|big|blockquote|body|br|button|center|code|col|colgroup|dd|del|div|dl|dt|em|embed|"
    "font|form|h[1-6]|head|hr|html|i|iframe|img|input|ins|label|li|link|meta|noscript|object|ol|"
    "option|p|pre|s|script|section|select|small|source|span|strike|strong|style|sub|sup|svg|"
    "table|tbody|td|textarea|tfoot|th|thead|title|tr|u|ul|video"
)
_ATTR: Final = r"""\s+[A-Za-z_:][-\w:.]*(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+))?"""
_TAG_RE: Final = re.compile(rf"</?(?:{_HTML_TAGS})(?:{_ATTR})*\s*/?>", re.IGNORECASE | re.ASCII)
"""알려진 HTML 태그 이름만 지운다. `<A코스>`·`<삼국유사>`·`a < b > c` 같은 본문 꺾쇠는 원문 그대로 둔다
(본문을 바꾸지 않는다 — 화면은 텍스트로 이스케이프해 그린다)."""

_KOGL_BY_VALUE: Final[dict[str, KoglType]] = {
    # 옛 평면 키 경로 — Map `providers/visitkorea_attractions.py` `_KOGL_LICENSE` 값과 원천 코드만 정확히 맞춘다.
    "type1": 1,
    "type3": 3,
    "공공누리 제1유형(출처표시)": 1,
    "공공누리 제3유형(출처표시·변경금지)": 3,
}
_BR_RE: Final = re.compile(r"<br\s*/?>", re.IGNORECASE)
_SPACE_RE: Final = re.compile("[ \t\u00a0\u3000]+")
_FACILITY_RE: Final = re.compile(r"^[a-z_]{1,64}$")

_GUIDE_TEXT_FIELDS: Final = (
    "usage_hours",
    "rest_days",
    "parking",
    "parking_fee",
    "fee_text",
    "discount",
    "reservation",
    "inquiry",
    "transport",
    "facilities",
    "capacity",
    "pet_note",
)
_PET_FIELDS: Final = ("companion_type", "allowed_pets", "requirements", "notes")


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def kogl_type(license_value: Any) -> KoglType | None:
    """옛 Map 평면 `license` 값(유형 이름 또는 원천 코드) → 공공누리 유형. 정확히 아는 값만, 나머지는 None."""
    text = _text(license_value)
    if text is None:
        return None
    return _KOGL_BY_VALUE.get(text.lower())


def _drop_control(text: str) -> str:
    """제어·서식 문자(Cc/Cf — 양방향 제어 문자 포함)를 줄바꿈·탭(뒤에서 공백이 된다) 말고 지운다."""
    return "".join(
        ch for ch in text if ch in "\n\t" or unicodedata.category(ch) not in ("Cc", "Cf")
    )


def _plain(value: Any, max_length: int) -> str | None:
    """원천 문장 → 화면용 평문. 태그 꼴과 제어 문자를 지우고 줄바꿈만 남긴다(빈 줄 연속은 하나로).

    `max_length`보다 길면 자르지 않고 None이다(본문을 바꾸지 않는다).
    """
    text = _text(value)
    if text is None:
        return None
    text = _TAG_RE.sub("", _BR_RE.sub("\n", text))
    text = _drop_control(text)
    lines = [_SPACE_RE.sub(" ", line).strip() for line in text.replace("\r", "").split("\n")]
    paragraphs: list[str] = []
    blank = False
    for line in lines:
        if not line:
            blank = bool(paragraphs)
            continue
        if blank:
            paragraphs.append("")
            blank = False
        paragraphs.append(line)
    joined = "\n".join(paragraphs).strip()
    if not joined or len(joined) > max_length:
        return None
    return joined


def plain_overview(value: Any) -> str | None:
    """소개문 → 화면용 평문(20,000자 넘으면 None)."""
    return _plain(value, _OVERVIEW_MAX)


def guide_text(value: Any) -> str | None:
    """이용 안내 문장 1개 → 화면용 평문(2,000자 넘으면 None). 원천 문장 그대로(줄바꿈 보존)."""
    return _plain(value, _GUIDE_TEXT_MAX)


def source_image_url(provider: IntroductionProvider, value: Any) -> str | None:
    """원천 이미지 URL → https 원본 URL. 그 원천의 허용 호스트가 아니거나 모양이 이상하면 None."""
    suffix = _IMAGE_HOST_SUFFIX.get(provider)
    text = _text(value)
    if suffix is None or text is None or len(text) > 2048 or any(ch.isspace() for ch in text):
        return None
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.scheme.lower() not in ("http", "https") or not host.endswith(suffix):
        return None
    if parts.username or parts.password or port not in (None, 80, 443):
        return None
    return urlunsplit(("https", host, parts.path, parts.query, ""))


def tourapi_image_url(value: Any) -> str | None:
    """TourAPI 이미지 URL → https 원본 URL(`*.visitkorea.or.kr`만)."""
    return source_image_url("tourapi", value)


def _alt(name: str, caption: Any, index: int) -> str:
    """대체 텍스트 — 원천 이미지 이름이 있으면 그것, 없으면 장소명 + 대표 사진/사진 N."""
    cleaned = _text(caption)
    if cleaned is not None:
        text = " ".join(_drop_control(cleaned).split())
        if text:
            return text[:_ALT_MAX]
    suffix = " 대표 사진" if index == 0 else f" 사진 {index + 1}"
    base = " ".join(_drop_control(name).split()) or "장소"
    return base[: _ALT_MAX - len(suffix)] + suffix


def _image(url: str, alt: str, license_type: KoglType) -> SourceImage:
    return SourceImage(
        url=url,
        alt=alt,
        kogl_type=license_type,
        no_derivatives=license_type in (3, 4),
        license_label=_KOGL_LABEL[license_type],
        license_url=_KOGL_URL[license_type],
    )


def image_license_type(raw: Any) -> KoglType | None:
    """Map `ContentLicense` → 보여도 되는 공공누리 유형. 모르거나 모순되거나 정책상 뺄 것이면 None.

    변경·상업 허용 값은 유형에서 결정된다(3·4 변경금지, 2·4 상업금지). 둘이 유형과 맞지 않으면 어느 쪽이
    맞는지 단정할 수 없으므로 싣지 않는다.
    """
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kogl_type")
    derivatives = raw.get("derivatives_allowed")
    commercial = raw.get("commercial_allowed")
    if isinstance(kind, bool) or not isinstance(kind, int) or kind not in _KOGL_LABEL:
        return None
    if not isinstance(derivatives, bool) or not isinstance(commercial, bool):
        return None
    if derivatives != (kind in (0, 1, 2)) or commercial != (kind in (0, 1, 3)):
        return None
    if not commercial and not _SHOW_NONCOMMERCIAL_ONLY_IMAGES:
        return None
    return cast(KoglType, kind)


def _provider(info: dict[str, Any]) -> IntroductionProvider | None:
    source = info.get("source")
    if isinstance(source, str) and source in get_args(IntroductionProvider):
        return cast(IntroductionProvider, source)
    return None


def _reference_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def visitor_introduction(info: Any, *, name: str) -> SourceIntroduction | None:
    """Map `visitor_info` → 출처 소개(소개문 + 원본 이미지 갤러리). 보여 줄 값이 없으면 None."""
    if not isinstance(info, dict):
        return None
    provider = _provider(info)
    if provider is None:
        return None
    overview = plain_overview(info.get("description"))
    images: list[SourceImage] = []
    seen: set[str] = set()
    raw_images = info.get("images")
    for raw in raw_images if isinstance(raw_images, list) else []:
        if len(images) >= _IMAGES_MAX:
            break
        if not isinstance(raw, dict):
            continue
        url = source_image_url(provider, raw.get("url"))
        license_type = image_license_type(raw.get("license"))
        if url is None or license_type is None or url in seen:
            continue
        seen.add(url)
        images.append(_image(url, _alt(name, raw.get("caption"), len(images)), license_type))
    if overview is None and not images:
        return None
    return SourceIntroduction(
        provider=provider,
        attribution=SOURCE_ATTRIBUTION[provider],
        reference_date=_reference_date(info.get("reference_date")),
        overview=overview,
        images=images,
    )


def _fees(raw: Any) -> list[VisitFee]:
    fees: list[VisitFee] = []
    audiences = get_args(FeeAudience)
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict) or len(fees) >= 3:
            continue
        audience, amount = entry.get("audience"), entry.get("amount_krw")
        if audience not in audiences or isinstance(amount, bool) or not isinstance(amount, int):
            continue
        if not 0 <= amount <= 10_000_000 or any(fee.audience == audience for fee in fees):
            continue
        fees.append(VisitFee(audience=cast(FeeAudience, audience), amount_krw=amount))
    return fees


def _accessibility(raw: Any) -> list[AccessibilityItem]:
    items: list[AccessibilityItem] = []
    groups = get_args(AccessibilityGroup)
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict) or len(items) >= 40:
            continue
        group, facility = entry.get("group"), entry.get("facility")
        label, text = guide_text(entry.get("label")), guide_text(entry.get("text"))
        # 모르는 분류·시설 코드는 무시한다(원천이 늘면 값이 더해진다 — Map 소비자 규칙).
        if group not in groups or not isinstance(facility, str) or not _FACILITY_RE.match(facility):
            continue
        if label is None or text is None:
            continue
        items.append(
            AccessibilityItem(
                group=cast(AccessibilityGroup, group), facility=facility, label=label, text=text
            )
        )
    return items


def _pet_policy(raw: Any) -> VisitPetPolicy | None:
    if not isinstance(raw, dict):
        return None
    policy = VisitPetPolicy(
        companion_type=guide_text(raw.get("companion_type")),
        allowed_pets=guide_text(raw.get("allowed_pets")),
        requirements=guide_text(raw.get("requirements")),
        notes=guide_text(raw.get("notes")),
    )
    if not any(getattr(policy, key) for key in _PET_FIELDS):
        return None
    return policy


def visit_guide(info: Any) -> VisitGuide | None:
    """Map `visitor_info` → 이용 안내. 출처 말고 보여 줄 값이 없으면 None."""
    if not isinstance(info, dict):
        return None
    provider = _provider(info)
    if provider is None:
        return None
    texts = {key: guide_text(info.get(key)) for key in _GUIDE_TEXT_FIELDS}
    accommodation = info.get("accommodation_available")
    guide = VisitGuide.model_validate(
        {
            **texts,
            "provider": provider,
            "attribution": SOURCE_ATTRIBUTION[provider],
            "reference_date": _reference_date(info.get("reference_date")),
            "fees": _fees(info.get("fees")),
            "accommodation_available": accommodation if isinstance(accommodation, bool) else None,
            "accessibility": _accessibility(info.get("accessibility")),
            "pet_policy": _pet_policy(info.get("pet_policy")),
        }
    )
    has_value = (
        any(texts.values())
        or bool(guide.fees)
        or guide.accommodation_available is not None
        or bool(guide.accessibility)
        or guide.pet_policy is not None
    )
    return guide if has_value else None


def tourapi_introduction(detail: Any, *, name: str) -> SourceIntroduction | None:
    """옛 Map 평면 키(`detail.facility_info`) → TourAPI 출처 소개. `visitor_info`가 없는 Map 응답용 대체 경로."""
    if not isinstance(detail, dict):
        return None
    facility = detail.get("facility_info")
    if not isinstance(facility, dict) or _text(facility.get("tourapi_content_id")) is None:
        return None
    overview = plain_overview(facility.get("overview"))
    license_type = kogl_type(facility.get("license"))
    images: list[SourceImage] = []
    image_url = tourapi_image_url(facility.get("image_url"))
    if image_url is not None and license_type is not None:
        images.append(_image(image_url, _alt(name, None, 0), license_type))
    if overview is None and not images:
        return None
    # TourAPI 행의 출처는 늘 한국관광공사다 — Map 값으로 바꿔 달지 않는다(이용약관 필수 표시).
    return SourceIntroduction(
        provider="tourapi", attribution=TOURAPI_ATTRIBUTION, overview=overview, images=images
    )


def visitor_info_of(dto: dict[str, Any]) -> dict[str, Any] | None:
    """Map 상세 dto의 최상위 `visitor_info`(ADR-125). 없거나 객체가 아니면 None."""
    info = dto.get("visitor_info")
    return info if isinstance(info, dict) else None


def source_introduction(dto: dict[str, Any], *, name: str) -> SourceIntroduction | None:
    """Map 상세 dto → 출처 소개. `visitor_info`가 있으면 그것이 정본이고, 없을 때만 옛 평면 키를 읽는다."""
    info = visitor_info_of(dto)
    if info is not None:
        return visitor_introduction(info, name=name)
    return tourapi_introduction(dto.get("detail"), name=name)


def source_visit_guide(dto: dict[str, Any]) -> VisitGuide | None:
    """Map 상세 dto → 이용 안내(`visitor_info`가 있을 때만)."""
    return visit_guide(visitor_info_of(dto))
