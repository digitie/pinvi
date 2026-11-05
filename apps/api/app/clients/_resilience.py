"""Map·geo 전송 회로. 요청 의미는 client가 판단하며 상태는 worker별 client가 소유한다."""

from __future__ import annotations

from collections.abc import Callable


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

    def failure(self, token: tuple[bool, int]) -> None:
        if token[1] != self._generation:
            return
        self._failures += 1
        if token[0] or self._failures >= 3:
            self._opened_at = self._clock()
            self._generation += 1
            self._trial = False

    def release(self, token: tuple[bool, int]) -> None:
        if token[0] and token[1] == self._generation:
            self._trial = False
