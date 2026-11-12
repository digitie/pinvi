"""pytest fixture — Sprint 1 단위 테스트 진입점.

PostGIS testcontainer는 Sprint 2 통합 테스트에서 활성화. Sprint 1은 단위만.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _configure_logging() -> None:
    from app.core.logging import configure_logging

    configure_logging(level="WARNING")


@pytest.fixture(autouse=True)
def _reset_category_label_cache() -> Iterator[None]:
    """`category_labels`의 프로세스 캐시가 테스트 사이에 새지 않게 한다."""
    from app.services.category_labels import reset_category_label_cache

    reset_category_label_cache()
    yield
    reset_category_label_cache()


@pytest.fixture(autouse=True)
def _reset_weather_markers_cache() -> Iterator[None]:
    """weather `/markers` 프로세스 캐시(#621)가 테스트 사이에 새지 않게 한다."""
    from app.services.weather_markers_cache import reset_weather_markers_cache

    reset_weather_markers_cache()
    yield
    reset_weather_markers_cache()
