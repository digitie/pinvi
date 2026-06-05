"""Dagster definitions 로드 sanity 테스트."""

from __future__ import annotations


def test_definitions_load() -> None:
    from tripmate.etl.definitions import defs

    assert defs is not None
    asset_keys = {node.key.to_user_string() for node in defs.resolve_asset_graph().asset_nodes}
    assert "tripmate_kasi_special_days" in asset_keys
    assert defs.get_job_def("kasi_poi_rise_set_job") is not None
