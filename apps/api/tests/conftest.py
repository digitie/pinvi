"""pytest fixture — Sprint 1 단위 테스트 진입점.

PostGIS testcontainer는 Sprint 2 통합 테스트에서 활성화. Sprint 1은 단위만.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _configure_logging() -> None:
    from app.core.logging import configure_logging

    configure_logging(level="WARNING")
