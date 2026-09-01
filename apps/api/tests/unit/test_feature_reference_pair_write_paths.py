"""참조의 두 축(`feature_id` + `feature_uuid`)을 함께 다루는지 결박한다.

두 컬럼은 한 Map feature 참조의 양면인데 DB에 짝을 강제하는 제약이 없다.
복사 경로가 한쪽만 옮기면 원본은 정상인데 사본만 짝이 깨지고, reconciliation은
그 행에서 막힌다 — blocked event는 ack되지 않아 피드가 영구히 선다.

AST로 읽는다. 문자열 검색은 주석에도 통과하고(적대 리뷰 M6) 서식 변경에
깨지기 때문이다. 생성자·속성 대입·bulk update 세 형태를 모두 본다.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SERVICES = Path(__file__).resolve().parents[2] / "app" / "services"

# 두 축을 쓰는 모든 관계와 그 컬럼 이름.
_AXES = (("feature_id", "feature_uuid"), ("target_feature_id", "target_feature_uuid"))


def _tree(name: str) -> ast.Module:
    return ast.parse((_SERVICES / name).read_text(encoding="utf-8"))


def _keyword(call: ast.Call, name: str) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return ast.unparse(keyword.value)
    return None


def _copy_constructors(tree: ast.Module, class_name: str) -> list[tuple[ast.Call, str]]:
    """`Klass(feature_id=<origin>.feature_id, ...)` 꼴 생성자와 그 origin."""

    found: list[tuple[ast.Call, str]] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == class_name
        ):
            continue
        for id_column, _uuid_column in _AXES:
            value = _keyword(node, id_column)
            if value is not None and value.endswith(f".{id_column}"):
                found.append((node, value[: -len(id_column) - 1]))
    return found


def test_reference_copy_constructors_carry_both_axes() -> None:
    """기존 행을 복사하는 생성자는 두 축을 함께 옮겨야 한다."""

    sites = (
        ("admin_trip_operations.py", "TripDayPoi"),
        ("trip.py", "TripDayPoi"),
        ("notice_plan.py", "TripDayPoi"),
    )
    seen = 0
    for filename, class_name in sites:
        for call, origin in _copy_constructors(_tree(filename), class_name):
            seen += 1
            for id_column, uuid_column in _AXES:
                if _keyword(call, id_column) != f"{origin}.{id_column}":
                    continue
                assert _keyword(call, uuid_column) == f"{origin}.{uuid_column}", (
                    f"{filename}: {id_column}만 복사하고 {uuid_column}를 빠뜨렸다 — "
                    "사본의 참조 짝이 깨져 reconciliation이 그 행에서 막힌다"
                )
    assert seen >= 3, f"복사 생성자를 {seen}개만 찾았다 — 탐지기가 눈이 멀었다"


def test_attribute_assignment_never_changes_one_axis_alone() -> None:
    """`row.feature_id = ...` 대입은 같은 블록에서 UUID 축도 함께 다뤄야 한다.

    한쪽만 바꾸면 두 축이 실제로 어긋난 행이 생기고, 그건 reconciliation이
    유일하게 block해야 할 상태다 — 그리고 block은 피드를 영구히 세운다."""

    for filename in ("notice_plan.py", "admin_pois.py", "poi.py", "feature_request.py"):
        path = _SERVICES / filename
        if not path.exists():
            continue
        tree = _tree(filename)
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            body = ast.unparse(function)
            for id_column, uuid_column in _AXES:
                if f".{id_column} = " not in body:
                    continue
                # 같은 함수 안에서 UUID 축도 반드시 다뤄야 한다.
                assert f".{uuid_column} = " in body, (
                    f"{filename}::{function.name}가 {id_column}만 대입한다 — "
                    f"{uuid_column}를 함께 갱신하거나 비워야 한다"
                )


def test_bulk_updates_that_set_one_axis_are_enumerated() -> None:
    """`update(...).values(feature_id=...)` 는 UUID 축을 남긴다.

    narrowing 이후에는 무해하지만(UUID가 NULL이면 legacy 축으로 판정) 새 경로가
    말없이 늘어나면 안 된다. 알려진 목록을 못 박아 증가를 눈에 보이게 한다."""

    known = {("feature_request.py", "feature_id")}
    found: set[tuple[str, str]] = set()
    for filename in sorted(p.name for p in _SERVICES.glob("*.py")):
        for node in ast.walk(_tree(filename)):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "values"
            ):
                continue
            for id_column, uuid_column in _AXES:
                if _keyword(node, id_column) is not None and _keyword(node, uuid_column) is None:
                    found.add((filename, id_column))
    assert found == known, (
        f"한 축만 쓰는 bulk update 목록이 바뀌었다: {sorted(found)} != {sorted(known)}"
    )
