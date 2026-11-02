"""`app.services.category_labels` — Map 카테고리 코드 → 표시 이름(2026-11-02 prod e2e)."""

from __future__ import annotations

from typing import Any

import pytest

from app.services import category_labels as module
from app.services.category_labels import (
    CategoryLabels,
    build_category_labels,
    get_category_labels,
    reset_category_label_cache,
)

# Map `/v1/categories` 실응답 형태(2026-11-02 prod 발췌).
_ITEMS: list[dict[str, Any]] = [
    {"code": "01000000", "label": "관광", "path": ["관광"]},
    {"code": "01070000", "label": "관광 > 국가유산", "path": ["관광", "국가유산"]},
    {
        "code": "01070300",
        "label": "관광 > 국가유산 > 사적·기념물",
        "path": ["관광", "국가유산", "사적·기념물"],
    },
    {"code": "06010000", "label": "교통 > 주차장", "path": ["교통", "주차장"]},
    {"code": "02010100", "label": "식음 > 음식점 > 한식", "path": ["식음", "음식점", "한식"]},
]


@pytest.fixture(autouse=True)
def _fresh_cache() -> Any:
    reset_category_label_cache()
    yield
    reset_category_label_cache()


def test_leaf_name_from_path() -> None:
    labels = build_category_labels(_ITEMS)
    assert labels.label("01070300") == "사적·기념물"
    assert labels.label("06010000") == "주차장"
    assert labels.label("02010100") == "한식"


def test_unknown_code_falls_back_to_nearest_ancestor() -> None:
    labels = build_category_labels(_ITEMS)
    assert labels.label("01070399") == "사적·기념물"
    assert labels.label("01079900") == "국가유산"
    assert labels.label("01990000") == "관광"


def test_unknown_code_without_ancestor_is_hidden_not_shown_as_number() -> None:
    labels = build_category_labels(_ITEMS)
    assert labels.label("99010100") is None
    assert CategoryLabels().label("01070300") is None


def test_human_label_passes_through_and_blank_is_none() -> None:
    labels = build_category_labels(_ITEMS)
    assert labels.label("해수욕장") == "해수욕장"
    assert labels.label("  ") is None
    assert labels.label(None) is None


def test_label_without_path_uses_last_label_segment() -> None:
    labels = build_category_labels([{"code": "03010000", "label": "숙박 > 호텔"}])
    assert labels.label("03010000") == "호텔"


class _Client:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    async def categories(self, *, include_counts: bool = False) -> dict[str, Any]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("map down")
        return {"items": _ITEMS}


async def test_catalog_is_cached_between_requests() -> None:
    client = _Client()
    first = await get_category_labels(client)
    second = await get_category_labels(client)
    assert first.label("06010000") == "주차장"
    assert second is first
    assert client.calls == 1


async def test_catalog_failure_degrades_to_empty_labels_and_retries_soon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failing = _Client(fail=True)
    labels = await get_category_labels(failing)
    assert labels.label("06010000") is None

    # 실패는 짧게만 캐시한다 — 실패 TTL이 지나면 다시 받는다.
    now = module.time.monotonic()
    monkeypatch.setattr(module.time, "monotonic", lambda: now + 61.0)
    recovered = await get_category_labels(_Client())
    assert recovered.label("06010000") == "주차장"
