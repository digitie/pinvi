"""Dagster code location 진입점.

Sprint 1: 빈 Definitions — UI에 노출되는 asset 없음. Sprint 5에서
`python-krtour-map`의 변환·적재 함수를 호출하는 asset을 본 모듈에 등록.
"""

from __future__ import annotations

from dagster import Definitions

defs = Definitions(
    assets=[],
    schedules=[],
    sensors=[],
    resources={},
)
