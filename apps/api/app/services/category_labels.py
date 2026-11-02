"""kor-travel-map 카테고리 코드 → 사용자 표시 이름.

Map은 feature `category`를 8자리 계층 코드(`01070300` = 관광 > 국가유산 > 사적·기념물)로 준다.
Pinvi 화면은 그 값을 그대로 보여 줬다 — 2026-11-02 prod e2e에서 장소 검색 결과의 둘째 줄과
상세 카드 부제가 `02010100`·`06010000` 같은 숫자였고, 서울의 식당 "하회마을"과 안동의
주차장 "도산서원"을 이름만으로 구별할 수 없었다.

이 모듈은 Map `/v1/categories` 카탈로그(정적, 145건)를 프로세스 안에 캐시하고 코드를
**잎 이름**(`path`의 마지막 단계, 예: `사적·기념물`, `주차장`, `한식`)으로 바꾼다. 응답의
`category`(코드)는 필터·마커 계약 때문에 그대로 두고, 표시용 `category_label`을 따로 채운다.
카탈로그를 못 받으면 직전 정상값을 계속 쓰고, 처음부터 없으면 label은 `None`이다 — 숫자 코드를
사용자에게 보이느니 비운다.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.clients.kor_travel_map import KorTravelMapError

logger = logging.getLogger(__name__)

# 카탈로그는 정적이라 길게 둔다. 실패는 짧게 — 다음 요청이 곧 다시 시도한다.
_TTL_SECONDS = 3600.0
_FAILURE_TTL_SECONDS = 60.0
# 카탈로그 조회 1회의 전체 예산(Map client 기본 재시도 3회 × 5초를 요청 경로에 끌어들이지 않는다).
_FETCH_BUDGET_SECONDS = 2.0
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
    refresh: asyncio.Task[CategoryLabels] | None = None


_cache = _Cache()


def reset_category_label_cache() -> None:
    """테스트 격리용."""
    task = _cache.refresh
    if task is not None and not task.done():
        try:
            task.cancel()
        except RuntimeError:  # 이미 닫힌 event loop의 task(테스트 사이)
            pass
    _cache.value = None
    _cache.expires_at = 0.0
    _cache.refresh = None


async def _fetch(client: _CategoriesClient) -> CategoryLabels:
    """카탈로그 1회 조회(짧은 예산). 실패하면 직전 정상값을 지키고 짧게 다시 시도하게 한다."""
    try:
        async with asyncio.timeout(_FETCH_BUDGET_SECONDS):
            data = await client.categories()
    except (KorTravelMapError, TimeoutError) as exc:
        logger.warning("category_labels.fetch_failed: %r", exc)
        labels = _cache.value or EMPTY_CATEGORY_LABELS
        ttl = _FAILURE_TTL_SECONDS
    except Exception:
        # 예상 밖 오류(프로그래밍 오류 등)는 error 로그와 traceback으로 드러내되, 표시 전용 보강이
        # 검색·상세 응답을 500으로 만들지는 않는다.
        logger.exception("category_labels.fetch_crashed")
        labels = _cache.value or EMPTY_CATEGORY_LABELS
        ttl = _FAILURE_TTL_SECONDS
    else:
        items = data.get("items") if isinstance(data, Mapping) else None
        fresh = build_category_labels(items if isinstance(items, list) else [])
        if fresh.by_code:
            labels, ttl = fresh, _TTL_SECONDS
        else:
            labels, ttl = _cache.value or EMPTY_CATEGORY_LABELS, _FAILURE_TTL_SECONDS
    _cache.value = labels
    _cache.expires_at = time.monotonic() + ttl
    return labels


def _refresh_task(client: _CategoriesClient) -> asyncio.Task[CategoryLabels]:
    """진행 중인 갱신 하나를 공유한다(single-flight). 다른 event loop의 낡은 task는 버린다."""
    loop = asyncio.get_running_loop()
    task = _cache.refresh
    if task is None or task.done() or task.get_loop() is not loop:
        task = loop.create_task(_fetch(client))
        _cache.refresh = task
    return task


async def get_category_labels(client: _CategoriesClient) -> CategoryLabels:
    """캐시된 카탈로그를 돌려준다. 예외를 올리지 않는다(표시 전용 보강).

    - 유효하면 그대로.
    - 만료됐지만 직전 값이 있으면 **그 값을 바로** 돌려주고 갱신은 뒤에서 한 번만 한다
      (요청 경로가 갱신을 기다리지 않는다 — 검색·지도 이동이 카탈로그 갱신에 붙잡히지 않게).
    - 처음(값 없음)이면 공유된 갱신 하나를 짧은 예산(`_FETCH_BUDGET_SECONDS`) 안에서 기다린다.
    """
    now = time.monotonic()
    if _cache.value is not None:
        if now >= _cache.expires_at:
            _refresh_task(client)
        return _cache.value
    return await asyncio.shield(_refresh_task(client))
