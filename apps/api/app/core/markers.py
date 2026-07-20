"""마커 팔레트 공용 헬퍼 — 16색 팔레트 키(P-01~P-16)와 일자 기본색(ADR-055).

팔레트 색 데이터 정본은 프론트 `@pinvi/design-tokens`이지만, 서버는 trip-day 기본색과
POI `display_marker_color`를 **결정론적으로** 계산해 지도 핀과 목록 뱃지가 항상 같은 색을
쓰게 한다(색 divergence 방지). 여기서는 키 형식 검증과 일자 인덱스 기반 색 해석만 다룬다.
"""

from __future__ import annotations

import re

#: 팔레트 키 형식 — P-01 ~ P-16.
MARKER_COLOR_PATTERN = re.compile(r"^P-(0[1-9]|1[0-6])$")

#: 팔레트 색 수(일자 기본색 순환 주기).
DAY_PALETTE_SIZE = 16


def is_marker_color_key(value: str | None) -> bool:
    """`value`가 유효한 팔레트 키(P-01~P-16)면 True."""
    return value is not None and MARKER_COLOR_PATTERN.match(value) is not None


def default_day_marker_color(day_index: int) -> str:
    """일자 기본 팔레트 색 — `P-{((day_index-1) % 16) + 1:02d}` (1→P-01, 16→P-16, 17→P-01)."""
    slot = ((day_index - 1) % DAY_PALETTE_SIZE) + 1
    return f"P-{slot:02d}"


def resolve_day_marker_color(day_index: int, override: str | None) -> str:
    """일자 표시색 — override가 유효 키면 그것, 아니면 인덱스 기본색. 항상 유효 키를 반환."""
    if override is not None and MARKER_COLOR_PATTERN.match(override):
        return override
    return default_day_marker_color(day_index)


def resolve_display_marker_color(
    day_index: int, day_override: str | None, poi_custom: str | None
) -> str:
    """POI 표시색 — custom(POI) > 일자색(override 또는 기본). 항상 유효 키를 반환(ADR-055)."""
    if poi_custom is not None and MARKER_COLOR_PATTERN.match(poi_custom):
        return poi_custom
    return resolve_day_marker_color(day_index, day_override)
