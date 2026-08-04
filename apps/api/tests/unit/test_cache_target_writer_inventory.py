"""TripDayPoi direct writer inventory drift gate (T-VN-41-P)."""

from __future__ import annotations

import ast
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[2]
_EXPECTED_DIRECT_WRITERS = {
    ("app/services/admin_pois.py", "create_admin_poi"),
    ("app/services/admin_trip_operations.py", "_clone_poi"),
    ("app/services/notice_plan.py", "copy_plan_to_trip"),
    ("app/services/poi.py", "create_poi"),
    ("app/services/trip.py", "copy_trip"),
}


class _TripDayPoiWriterVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.scope: list[str] = []
        self.writers: set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_Call(self, node: ast.Call) -> None:
        is_constructor = isinstance(node.func, ast.Name) and node.func.id == "TripDayPoi"
        is_qualified_constructor = (
            isinstance(node.func, ast.Attribute) and node.func.attr == "TripDayPoi"
        )
        if is_constructor or is_qualified_constructor:
            self.writers.add(self.scope[-1] if self.scope else "<module>")
        self.generic_visit(node)


def test_trip_day_poi_direct_writer_inventory_is_reviewed() -> None:
    actual: set[tuple[str, str]] = set()
    for path in sorted((_API_ROOT / "app").rglob("*.py")):
        visitor = _TripDayPoiWriterVisitor()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        relative = path.relative_to(_API_ROOT).as_posix()
        actual.update((relative, writer) for writer in visitor.writers)

    assert actual == _EXPECTED_DIRECT_WRITERS
