"""참조의 두 축(`feature_id` + `feature_uuid`)을 함께 다루는지 결박한다.

두 컬럼은 한 Map feature 참조의 양면인데 DB에 짝을 강제하는 제약이 없다.
복사 경로가 한쪽만 옮기면 원본은 정상인데 사본만 짝이 깨지고, reconciliation은
그 행에서 막힌다 — blocked event는 ack되지 않아 피드가 영구히 선다.

런타임 경로는 통합 테스트가 실 DB로 덮는다. 여기서는 **새로 생기는 복사
경로**가 같은 결함을 다시 들여오지 못하게 소스 수준에서 못 박는다.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SERVICES = Path(__file__).resolve().parents[2] / "app" / "services"

# (파일, 생성자를 담은 함수, 원본 표현식) — 이 세 곳은 기존 행을 복사한다.
_COPY_SITES = (
    ("admin_trip_operations.py", "TripDayPoi", "poi"),
    ("trip.py", "TripDayPoi", "source_poi"),
    ("notice_plan.py", "TripDayPoi", "src"),
)


def _constructor_calls(path: Path, class_name: str) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == class_name
    ]


def _keyword_source(call: ast.Call, name: str) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return ast.unparse(keyword.value)
    return None


def test_trip_poi_copy_paths_carry_both_reference_axes() -> None:
    for filename, class_name, origin in _COPY_SITES:
        path = _SERVICES / filename
        copies = [
            call
            for call in _constructor_calls(path, class_name)
            if _keyword_source(call, "feature_id") == f"{origin}.feature_id"
        ]
        assert copies, f"{filename}에서 {origin}.feature_id 복사 생성자를 찾지 못했다"
        for call in copies:
            assert _keyword_source(call, "feature_uuid") == f"{origin}.feature_uuid", (
                f"{filename}: feature_id만 복사하고 feature_uuid를 빠뜨렸다 — "
                "사본의 참조 짝이 깨져 reconciliation이 그 행에서 막힌다"
            )


def test_curated_poi_feature_id_edit_clears_the_stale_uuid_shadow() -> None:
    """feature_id만 바꾸고 UUID shadow를 남기면 두 축이 실제로 어긋난다.

    그건 reconciliation이 유일하게 block해야 할 상태이고, block은 피드를
    영구히 세운다. 새 참조의 UUID는 알 수 없으므로 비우는 것이 정답이다."""

    source = (_SERVICES / "notice_plan.py").read_text(encoding="utf-8")
    assert "if new_feature_id != poi.feature_id:" in source
    assert "poi.feature_uuid = None" in source
    assert "poi.feature_id = new_feature_id" in source
