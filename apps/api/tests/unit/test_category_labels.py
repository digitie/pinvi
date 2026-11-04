"""`app.services.category_labels` — Map 카테고리 코드 → 표시 이름(2026-11-02 prod e2e)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from app.clients.kor_travel_map import KorTravelMapUnavailable
from app.services import category_labels as module
from app.services.category_labels import (
    CategoryLabels,
    build_category_labels,
    get_category_labels,
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
    def __init__(self, *, fail: bool = False, delay: float = 0.0) -> None:
        self.calls = 0
        self.fail = fail
        self.delay = delay

    async def categories(self, *, include_counts: bool = False) -> dict[str, Any]:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise KorTravelMapUnavailable("map down")
        return {"items": _ITEMS}


class _Clock:
    """`module.time` 대역 — 이벤트 루프 시계는 건드리지 않고 이 모듈의 monotonic만 옮긴다."""

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=fake.monotonic))
    return fake


async def test_catalog_is_cached_between_requests(clock: _Clock) -> None:
    client = _Client()
    first = await get_category_labels(client)
    second = await get_category_labels(client)
    assert first.label("06010000") == "주차장"
    assert second is first
    assert client.calls == 1


async def test_cold_concurrent_requests_share_one_fetch(clock: _Clock) -> None:
    client = _Client(delay=0.02)
    results = await asyncio.gather(*(get_category_labels(client) for _ in range(5)))
    assert all(r.label("06010000") == "주차장" for r in results)
    assert client.calls == 1


async def test_expired_catalog_is_served_stale_while_one_refresh_runs(clock: _Clock) -> None:
    """만료 뒤 요청은 갱신을 기다리지 않는다 — 직전 값을 바로 받고 갱신은 한 번만 돈다."""
    client = _Client()
    await get_category_labels(client)
    clock.now += 3601.0
    slow = _Client(delay=0.05)
    started = asyncio.get_running_loop().time()
    stale = await asyncio.gather(*(get_category_labels(slow) for _ in range(3)))
    assert asyncio.get_running_loop().time() - started < 0.04
    assert all(r.label("06010000") == "주차장" for r in stale)
    await asyncio.sleep(0.1)
    assert slow.calls == 1


async def test_failed_refresh_keeps_last_good_catalog(clock: _Clock) -> None:
    await get_category_labels(_Client())
    clock.now += 3601.0
    failing = _Client(fail=True)
    assert (await get_category_labels(failing)).label("06010000") == "주차장"
    await asyncio.sleep(0.01)  # 뒤에서 도는 갱신이 실패로 끝나게
    assert failing.calls == 1
    assert (await get_category_labels(failing)).label("06010000") == "주차장"


async def test_cold_failure_degrades_to_empty_and_retries_after_short_ttl(clock: _Clock) -> None:
    failing = _Client(fail=True)
    assert (await get_category_labels(failing)).label("06010000") is None
    clock.now += 61.0
    recovered = _Client()
    # 실패 TTL이 지나면 (직전 값이 빈 카탈로그라도) 다시 받는다.
    await get_category_labels(recovered)
    await asyncio.sleep(0.01)
    assert (await get_category_labels(recovered)).label("06010000") == "주차장"


async def test_cold_fetch_is_bounded_by_short_budget(
    clock: _Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Map client 기본 재시도(3회, 회당 5초)를 요청 경로에 끌어들이지 않는다."""
    monkeypatch.setattr(module, "_FETCH_BUDGET_SECONDS", 0.05)
    hanging = _Client(delay=5.0)
    started = asyncio.get_running_loop().time()
    labels = await get_category_labels(hanging)
    assert asyncio.get_running_loop().time() - started < 1.0
    assert labels.label("06010000") is None


async def test_cancelled_cold_waiter_does_not_cancel_shared_fetch(clock: _Clock) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    class ControlledClient(_Client):
        async def categories(self, *, include_counts: bool = False) -> dict[str, Any]:
            self.calls += 1
            entered.set()
            await release.wait()
            return {"items": _ITEMS}

    client = ControlledClient()
    first = asyncio.create_task(get_category_labels(client))
    await entered.wait()
    second = asyncio.create_task(get_category_labels(client))
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    labels = await asyncio.wait_for(second, 1)
    assert labels.label("06010000") == "주차장"
    assert await get_category_labels(client) is labels
    assert client.calls == 1
