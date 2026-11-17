"""시도(광역 지자체) 판정 — 홈 여행 통계의 '다녀온 지역' 집계용.

외부 호출(kor-travel-geo reverse)은 쓰지 않는다. 좌표 → 지역 조회는 위치정보 확인자료·동의 경로를
타야 하고, 홈 화면 한 번에 장소 수만큼 부르는 것은 과하다. 대신 이미 저장된 값만 본다:

1. 행정·법정동 코드(앞 2자리 = 시도 코드). 2023 강원(42→51)·2024 전북(45→52) 개편은 새 코드로 접는다.
2. 주소·지역 문자열의 시도 이름(약칭·정식 명칭).
3. 시·군 이름(시도를 하나로 정할 수 있는 것만 — '고성'(강원·경남)과 '광주시'(경기)는 뺀다).

판정할 수 없으면 None을 돌려준다(추측하지 않는다).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

# 정본 시도 코드 → 약칭. 표시는 약칭, 키는 코드.
SIDO_NAMES: dict[str, str] = {
    "11": "서울",
    "26": "부산",
    "27": "대구",
    "28": "인천",
    "29": "광주",
    "30": "대전",
    "31": "울산",
    "36": "세종",
    "41": "경기",
    "51": "강원",
    "43": "충북",
    "44": "충남",
    "52": "전북",
    "46": "전남",
    "47": "경북",
    "48": "경남",
    "50": "제주",
}
_LEGACY_SIDO_CODES = {"42": "51", "45": "52"}

_SIDO_ALIASES: dict[str, tuple[str, ...]] = {
    "11": ("서울", "서울시", "서울특별시"),
    "26": ("부산", "부산시", "부산광역시"),
    "27": ("대구", "대구시", "대구광역시"),
    "28": ("인천", "인천시", "인천광역시"),
    "29": ("광주", "광주광역시"),
    "30": ("대전", "대전시", "대전광역시"),
    "31": ("울산", "울산시", "울산광역시"),
    "36": ("세종", "세종시", "세종특별자치시"),
    "41": ("경기", "경기도"),
    "51": ("강원", "강원도", "강원특별자치도"),
    "43": ("충북", "충청북도"),
    "44": ("충남", "충청남도"),
    "52": ("전북", "전라북도", "전북특별자치도"),
    "46": ("전남", "전라남도"),
    "47": ("경북", "경상북도"),
    "48": ("경남", "경상남도"),
    "50": ("제주", "제주도", "제주특별자치도"),
}

# 시도를 하나로 정할 수 있는 시·군 이름(접미 '시'·'군' 없이). 자치구 이름은 여러 시에 겹쳐 쓰지 않는다.
_SIGUNGU_SIDO: dict[str, Sequence[str]] = {
    "41": (
        "수원 성남 의정부 안양 부천 광명 평택 동두천 안산 고양 과천 구리 남양주 오산 시흥 군포 "
        "의왕 하남 용인 파주 이천 안성 김포 화성 양주 포천 여주 연천 가평 양평"
    ).split(),
    "51": (
        "춘천 원주 강릉 동해 태백 속초 삼척 홍천 횡성 영월 평창 정선 철원 화천 양구 인제 양양"
    ).split(),
    "43": "청주 충주 제천 보은 옥천 영동 증평 진천 괴산 음성 단양".split(),
    "44": "천안 공주 보령 아산 서산 논산 계룡 당진 금산 부여 서천 청양 홍성 예산 태안".split(),
    "52": "전주 군산 익산 정읍 남원 김제 완주 진안 무주 장수 임실 순창 고창 부안".split(),
    "46": (
        "목포 여수 순천 나주 광양 담양 곡성 구례 고흥 보성 화순 장흥 강진 해남 영암 무안 함평 "
        "영광 장성 완도 진도 신안"
    ).split(),
    "47": (
        "포항 경주 김천 안동 구미 영주 영천 상주 문경 경산 의성 청송 영양 영덕 청도 고령 성주 "
        "칠곡 예천 봉화 울진 울릉"
    ).split(),
    "48": (
        "창원 진주 통영 사천 김해 밀양 거제 양산 의령 함안 창녕 남해 하동 산청 함양 거창 합천"
    ).split(),
    "50": ("제주", "서귀포"),
    "27": ("군위",),
    "28": ("강화", "옹진"),
    "26": ("기장",),
    "31": ("울주",),
}

_ALIAS_TO_CODE: dict[str, str] = {
    alias: code for code, aliases in _SIDO_ALIASES.items() for alias in aliases
}
_SIGUNGU_TO_CODE: dict[str, str] = {
    name: code for code, names in _SIGUNGU_SIDO.items() for name in names
}
_CODE_RE = re.compile(r"^[0-9]{2,10}$")
_TOKEN_SPLIT_RE = re.compile(r"[\s,·/()\[\]]+")
_CODE_KEYS = (
    "sido_code",
    "legal_dong_code",
    "bjd_code",
    "bjd_cd",
    "region_code",
    "sigungu_code",
    "sig_cd",
    "adm_cd",
    "code",
)
_TEXT_KEYS = ("sido", "sido_name", "label", "road", "jibun", "full", "name")
_CONTAINER_KEYS = ("region", "address", "location")


def sido_name(code: str) -> str:
    return SIDO_NAMES[code]


def sido_from_code(value: object) -> str | None:
    """행정·법정동 코드(2~10자리)의 앞 2자리를 정본 시도 코드로. 알 수 없는 코드는 None."""
    if not isinstance(value, str) or not _CODE_RE.fullmatch(value):
        return None
    prefix = _LEGACY_SIDO_CODES.get(value[:2], value[:2])
    return prefix if prefix in SIDO_NAMES else None


def sido_from_text(value: object) -> str | None:
    """주소·지역 문자열에서 처음 판정되는 시도. 시도 이름이 시·군 이름보다 앞선다."""
    if not isinstance(value, str):
        return None
    tokens = [token for token in _TOKEN_SPLIT_RE.split(value.strip()) if token]
    for token in tokens:
        code = _ALIAS_TO_CODE.get(token)
        if code is not None:
            return code
    for token in tokens:
        base = token[:-1] if len(token) > 2 and token[-1] in "시군" else token
        code = _SIGUNGU_TO_CODE.get(base)
        if code is not None:
            return code
    return None


def _sido_from_mapping(value: Mapping[str, Any]) -> str | None:
    for key in _CODE_KEYS:
        code = sido_from_code(value.get(key))
        if code is not None:
            return code
    for key in _TEXT_KEYS:
        code = sido_from_text(value.get(key))
        if code is not None:
            return code
    return None


def sido_from_snapshot(snapshot: object) -> str | None:
    """POI `feature_snapshot`의 코드·주소에서 시도. 장소 이름은 보지 않는다(이름 속 지명은 오판)."""
    if not isinstance(snapshot, Mapping):
        return None
    for key in ("sido_code", "legal_dong_code", "bjd_code", "bjd_cd", "region_code", "sig_cd"):
        code = sido_from_code(snapshot.get(key))
        if code is not None:
            return code
    for key in _CONTAINER_KEYS:
        nested = snapshot.get(key)
        if isinstance(nested, Mapping):
            code = _sido_from_mapping(nested)
        else:
            code = sido_from_text(nested)
        if code is not None:
            return code
    return sido_from_text(snapshot.get("address_label"))
