"""kor-travel-map 카테고리 코드 → 사용자 표시 이름.

Map은 feature `category`를 8자리 계층 코드(`01070300` = 관광 > 국가유산 > 사적·기념물)로 준다.
Pinvi 화면은 그 값을 그대로 보여 줬다 — 2026-11-02 prod e2e에서 장소 검색 결과의 둘째 줄과
상세 카드 부제가 `02010100`·`06010000` 같은 숫자였고, 서울의 식당 "하회마을"과 안동의
주차장 "도산서원"을 이름만으로 구별할 수 없었다.

이 모듈은 Map `/v1/categories` 카탈로그(정적, 145건)를 프로세스 안에 캐시하고 코드를
**잎 이름**(`path`의 마지막 단계, 예: `사적·기념물`, `주차장`, `한식`)으로 바꾼다. 응답의
`category`(코드)는 필터·마커 계약 때문에 그대로 두고, 표시용 `category_label`을 따로 채운다.
카탈로그를 못 받으면 label은 `None`이다 — 숫자 코드를 사용자에게 보이느니 비운다.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# 카탈로그는 정적이라 길게 둔다. 실패는 짧게 — 다음 요청이 곧 다시 시도한다.
_TTL_SECONDS = 3600.0
_FAILURE_TTL_SECONDS = 60.0
# Map 카테고리 코드는 2자리 단위 계층(대·중·소·세)을 0으로 채운 8자리다.
_CODE_RE = re.compile(r"^\d{8}$")


class _CategoriesClient(Protocol):
    async def categories(self, *, include_counts: bool = False) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class CategoryLabels:
    """코드 → 잎 이름. 모르는 코드는 상위 계층 이름으로 물러선다."""

    by_code: Mapping[str, str] = field(default_factory=dict)

    def label(self, category: str | None) -> str | None:
        if category is None:
            return None
        value = category.strip()
        if not value:
            return None
        if not _CODE_RE.fullmatch(value):
            # 이미 사람이 읽는 값(구 snapshot·외부 provider 등) — 그대로 쓴다.
            return value
        for candidate in _ancestors(value):
            found = self.by_code.get(candidate)
            if found:
                return found
        return None


EMPTY_CATEGORY_LABELS = CategoryLabels()


def _ancestors(code: str) -> Iterable[str]:
    """`01070301` → `01070301`, `01070300`, `01070000`, `01000000` (자기 자신부터 대분류까지)."""
    yield code
    for keep in (6, 4, 2):
        parent = code[:keep] + "0" * (8 - keep)
        if parent != code:
            yield parent


def _leaf_name(item: Mapping[str, Any]) -> str | None:
    path = item.get("path")
    if isinstance(path, list):
        names = [str(part).strip() for part in path if isinstance(part, str) and part.strip()]
        if names:
            return names[-1]
    label = item.get("label")
    if isinstance(label, str) and label.strip():
        return label.split(">")[-1].strip() or None
    return None


def build_category_labels(items: Iterable[Any]) -> CategoryLabels:
    by_code: dict[str, str] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        code = item.get("code")
        name = _leaf_name(item)
        if isinstance(code, str) and code.strip() and name:
            by_code[code.strip()] = name
    return CategoryLabels(by_code=by_code)


@dataclass(slots=True)
class _Cache:
    value: CategoryLabels | None = None
    expires_at: float = 0.0


_cache = _Cache()


def reset_category_label_cache() -> None:
    """테스트 격리용."""
    _cache.value = None
    _cache.expires_at = 0.0


async def get_category_labels(client: _CategoriesClient) -> CategoryLabels:
    """캐시된 카탈로그를 돌려준다. 만료됐으면 한 번 다시 받는다(실패해도 예외를 올리지 않는다).

    잠금을 두지 않는다 — 만료 순간에 동시 요청이 겹치면 카탈로그를 두 번 받을 뿐이고(정적
    145건), 요청 경로가 그 갱신을 기다리며 줄 서지 않는다.
    """
    now = time.monotonic()
    if _cache.value is not None and now < _cache.expires_at:
        return _cache.value
    try:
        data = await client.categories()
    # 표시 전용 보강이다 — 카탈로그를 못 받아도 검색·상세 응답은 깨지지 않아야 한다.
    except Exception as exc:  # noqa: BLE001
        logger.warning("category_labels.fetch_failed: %s", exc)
        labels, ttl = EMPTY_CATEGORY_LABELS, _FAILURE_TTL_SECONDS
    else:
        items = data.get("items") if isinstance(data, Mapping) else None
        labels = build_category_labels(items if isinstance(items, list) else [])
        ttl = _TTL_SECONDS if labels.by_code else _FAILURE_TTL_SECONDS
    _cache.value = labels
    _cache.expires_at = now + ttl
    return labels
