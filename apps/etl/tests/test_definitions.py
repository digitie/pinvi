"""Dagster definitions 로드 sanity 테스트."""

from __future__ import annotations


def test_definitions_load() -> None:
    from tripmate.etl.definitions import defs

    # Sprint 1 — asset 없음
    assert defs is not None
    assert defs.get_asset_graph().asset_nodes == []
