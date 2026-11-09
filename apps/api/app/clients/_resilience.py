"""Map·geo 전송 회로. 요청 의미는 client가 판단하며 상태는 worker별 client가 소유한다."""

from __future__ import annotations

from collections.abc import Callable

from prometheus_client import Counter

#: 동시 호출 상한(bulkhead)이 꽉 차 외부 호출 없이 바로 거부한 횟수(#621). 호출하지 않았으므로
#: ``api_call_log``에는 행이 없다 — 거부는 이 counter로만 보인다.
BULKHEAD_REJECTIONS = Counter(
    "pinvi_api_outbound_bulkhead_rejections_total",
    "Outbound calls rejected locally because the per-dependency concurrency cap was full.",
    ("provider", "scope"),
)


class TransportCircuit:
    """세대가 바뀌기 전 출발한 결과는 버리고 half-open 시험은 하나만 허용한다."""

    # view 사이 간격이 30초를 넘어도 첫 요청이 매번 timeout 예산을 쓰지 않게 한다.
    def __init__(self, *, clock: Callable[[], float], open_seconds: float = 120.0) -> None:
        self._clock = clock
        self._open_seconds = open_seconds
        self._failures = 0
        self._opened_at: float | None = None
        self._trial = False
        self._generation = 0

    def acquire(self) -> tuple[bool, int] | None:
        if self._opened_at is None:
            return False, self._generation
        if self._clock() - self._opened_at < self._open_seconds or self._trial:
            return None
        self._trial = True
        return True, self._generation

    def success(self, token: tuple[bool, int]) -> None:
        if token[1] != self._generation:
            return
        if self._opened_at is not None:
            self._generation += 1
        self._failures = 0
        self._opened_at = None
        self._trial = False

    def failure(self, token: tuple[bool, int]) -> bool:
        """실패를 센다. 이 실패로 회로가 열렸으면 True(호출자가 한 번만 경고를 남긴다)."""
        if token[1] != self._generation:
            return False
        self._failures += 1
        if token[0] or self._failures >= 3:
            self._opened_at = self._clock()
            self._generation += 1
            self._trial = False
            return True
        return False

    def release(self, token: tuple[bool, int]) -> None:
        if token[0] and token[1] == self._generation:
            self._trial = False
