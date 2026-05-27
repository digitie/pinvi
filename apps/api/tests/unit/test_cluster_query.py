"""cluster_query 단위 테스트 — zoom → mode 결정 로직 (SQL 빌더는 통합 테스트에서)."""

from __future__ import annotations

import pytest

from app.services.cluster_query import ClusterMode, select_cluster_mode


@pytest.mark.parametrize(
    ("zoom", "expected"),
    [
        (3, "sido"),
        (6, "sido"),
        (7, "sigungu"),
        (10, "sigungu"),
        (11, "dbscan"),
        (13, "dbscan"),
        (14, "individual"),
        (19, "individual"),
    ],
)
def test_select_cluster_mode(zoom: int, expected: ClusterMode) -> None:
    assert select_cluster_mode(zoom) == expected
