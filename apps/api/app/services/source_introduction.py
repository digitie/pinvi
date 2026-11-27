"""장소 상세의 출처 소개 투영 — TourAPI 소개문·대표 이미지·출처/공공누리 표시.

kor-travel-map은 한국관광공사 국문 관광정보 서비스(KorService2, data.go.kr 15101578)의 관광지·문화시설·
레포츠를 place feature로 적재하고, `detail.facility_info`에 다음을 남긴다(Map
`providers/visitkorea_attractions.py`):

- `tourapi_content_id` — TourAPI contentid(이 키가 있어야 TourAPI 행으로 본다)
- `overview` — `detailCommon2` 소개문. Map이 `<br>`을 줄바꿈으로 바꾸고 태그·entity를 걷어 낸 평문이다.
- `image_url` — `firstimage` 원본 URL(`thumbnail_url`은 원천이 만든 작은 사본이라 쓰지 않는다)
- `attribution` — "한국관광공사"
- `license` — 이미지 공공누리 유형 이름(`cpyrhtDivCd` Type1/Type3 → "공공누리 제1유형(출처표시)" 등)

규칙(TourAPI 이용약관 + 공공누리):

- 출처는 늘 "한국관광공사"로 표시한다. 소개문만 있어도 출처를 단다.
- 이미지는 공공누리 유형이 확인된 것(제1유형·제3유형)만 보여 준다. 유형을 모르면 이용 조건을 알 수
  없으므로 싣지 않는다.
- 제3유형은 변경금지라 `no_derivatives=true`로 표시하고 화면이 크롭·필터 없이 원본 비율로 그린다.
  서버도 이미지를 내려받거나 줄이지 않는다 — 원본 URL을 그대로 넘긴다.
- 이미지 주소는 TourAPI 이미지 호스트(`*.visitkorea.or.kr`)의 https만 허용한다. 원천이 `http://`로 주면
  같은 주소의 https로 바꾼다(같은 파일을 받는 경로만 바꿀 뿐 이미지 변경이 아니다).
- 소개문은 Map이 이미 평문으로 만들지만, 남은 태그 꼴·제어 문자를 한 번 더 걷어 낸다. 화면은 텍스트로만
  그린다(HTML로 해석하지 않는다).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Final
from urllib.parse import urlsplit, urlunsplit

from app.schemas.feature import KoglType, SourceImage, SourceIntroduction

TOURAPI_ATTRIBUTION: Final = "한국관광공사"

_OVERVIEW_MAX: Final = 20000
"""이보다 긴 소개문은 싣지 않는다 — 잘라 내면 제3유형(변경금지) 본문을 바꾸는 셈이다."""
_ALT_MAX: Final = 200
_IMAGE_HOST_SUFFIX: Final = ".visitkorea.or.kr"

_KOGL_LABEL: Final[dict[int, str]] = {
    1: "공공누리 제1유형: 출처표시",
    3: "공공누리 제3유형: 출처표시 + 변경금지",
}
_KOGL_URL: Final[dict[int, str]] = {
    1: "https://www.kogl.or.kr/info/licenseType1.do",
    3: "https://www.kogl.or.kr/info/licenseType3.do",
}

_TAG_RE: Final = re.compile(r"</?[A-Za-z][^<>]*>")
"""태그 꼴만 지운다 — `a < b > c` 같은 본문 부등호는 남긴다(화면은 텍스트로 이스케이프해 그린다)."""
_BR_RE: Final = re.compile(r"<br\s*/?>", re.IGNORECASE)
_SPACE_RE: Final = re.compile("[ \t\u00a0\u3000]+")


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def kogl_type(license_value: Any) -> KoglType | None:
    """Map `license` 값(유형 이름 또는 원천 코드) → 공공누리 유형. 모르는 값은 None."""
    text = _text(license_value)
    if text is None:
        return None
    compact = text.replace(" ", "").lower()
    if "제1유형" in compact or compact == "type1":
        return 1
    if "제3유형" in compact or compact == "type3":
        return 3
    return None


def plain_overview(value: Any) -> str | None:
    """소개문 → 화면용 평문. 태그 꼴과 제어 문자를 지우고 줄바꿈만 남긴다(빈 줄 연속은 하나로)."""
    text = _text(value)
    if text is None:
        return None
    text = _TAG_RE.sub("", _BR_RE.sub("\n", text))
    # 제어·서식 문자(Cc/Cf — 양방향 제어 문자 포함)는 줄바꿈·탭(아래에서 공백이 된다) 말고 모두 지운다.
    text = "".join(
        ch for ch in text if ch in "\n\t" or unicodedata.category(ch) not in ("Cc", "Cf")
    )
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
    if not joined:
        return None
    if len(joined) > _OVERVIEW_MAX:
        return None
    return joined


def tourapi_image_url(value: Any) -> str | None:
    """TourAPI 이미지 URL → https 원본 URL. 허용 호스트가 아니거나 모양이 이상하면 None."""
    text = _text(value)
    if text is None or len(text) > 2048 or any(ch.isspace() for ch in text):
        return None
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.scheme.lower() not in ("http", "https") or not host.endswith(_IMAGE_HOST_SUFFIX):
        return None
    if parts.username or parts.password or parts.port not in (None, 80, 443):
        return None
    return urlunsplit(("https", host, parts.path, parts.query, ""))


def tourapi_introduction(detail: Any, *, name: str) -> SourceIntroduction | None:
    """Map place detail → TourAPI 출처 소개. TourAPI 행이 아니거나 보여 줄 값이 없으면 None."""
    if not isinstance(detail, dict):
        return None
    facility = detail.get("facility_info")
    if not isinstance(facility, dict) or _text(facility.get("tourapi_content_id")) is None:
        return None
    # 출처 표시는 Map이 남긴 값을 따르되, TourAPI 행은 늘 한국관광공사다.
    attribution = _text(facility.get("attribution")) or TOURAPI_ATTRIBUTION
    overview = plain_overview(facility.get("overview"))
    license_type = kogl_type(facility.get("license"))
    images: list[SourceImage] = []
    image_url = tourapi_image_url(facility.get("image_url"))
    if image_url is not None and license_type is not None:
        alt = (name.strip() or "장소")[: _ALT_MAX - 10] + " 대표 사진"
        images.append(
            SourceImage(
                url=image_url,
                alt=alt,
                kogl_type=license_type,
                no_derivatives=license_type == 3,
            )
        )
    if overview is None and not images:
        return None
    return SourceIntroduction(
        attribution=attribution[:100],
        overview=overview,
        images=images,
        # 공공누리 표시는 이미지에 걸린 유형이다 — 이미지를 싣지 않으면 유형도 싣지 않는다.
        kogl_type=license_type if images else None,
        license_label=_KOGL_LABEL[license_type] if images and license_type else None,
        license_url=_KOGL_URL[license_type] if images and license_type else None,
    )
