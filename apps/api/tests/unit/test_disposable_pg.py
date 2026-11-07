"""테스트 PostgreSQL cluster는 비내구·tmpfs로 뜬다 (n150 디스크 I/O 보호).

``make_nondurable``이 명령과 tmpfs를 실제로 얹는지(testcontainers 두 모양 모두), 이미지 major에 맞는
데이터 자리를 덮는지, 그리고 ``tests/`` 안의 모든 ``PostgresContainer(...)`` 생성이 그 함수를 거치는지 본다.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from tests.integration._disposable_pg import (
    DEFAULT_TMPFS_SIZE,
    NONDURABLE_COMMAND,
    TMPFS_SIZE_ENV,
    data_root,
    make_nondurable,
    resolve_tmpfs_size,
)

_TESTS = Path(__file__).resolve().parents[1]


class _Legacy:
    """testcontainers ≤4.14 모양 — tmpfs는 kwargs로만 넘길 수 있다."""

    def __init__(self, image: str) -> None:
        self.image = image
        self._kwargs: dict[str, Any] = {"labels": {"a": "b"}}
        self.command: str | None = None

    def with_command(self, command: str) -> _Legacy:
        self.command = command
        return self

    def with_kwargs(self, **kwargs: Any) -> _Legacy:
        self._kwargs = kwargs
        return self


class _Modern(_Legacy):
    """testcontainers 4.15+ 모양 — ``tmpfs`` 속성을 run()에 따로 넘긴다."""

    def __init__(self, image: str) -> None:
        super().__init__(image)
        self.tmpfs: dict[str, str] = {}


def test_command_turns_off_every_durability_knob() -> None:
    for knob in ("fsync=off", "synchronous_commit=off", "full_page_writes=off", "max_wal_size="):
        assert f"-c {knob}" in NONDURABLE_COMMAND


@pytest.mark.parametrize(
    ("image", "path"),
    [
        ("postgis/postgis:18-3.6-alpine", "/var/lib/postgresql"),
        ("postgres:18-alpine", "/var/lib/postgresql"),
        ("postgis/postgis:16-3.5-alpine", "/var/lib/postgresql/data"),
    ],
)
def test_data_root_follows_the_image_major(image: str, path: str) -> None:
    assert data_root(image) == path


@pytest.mark.parametrize(
    "image", ["postgres:latest", "postgis/postgis@sha256:4a43e3c3", "postgres"]
)
def test_unknown_major_fails_instead_of_guessing(image: str) -> None:
    with pytest.raises(ValueError, match="major"):
        data_root(image)


def test_legacy_shape_gets_command_and_tmpfs_kwarg_without_losing_others() -> None:
    container = make_nondurable(_Legacy("postgres:18-alpine"), size="1g")
    assert container.command == NONDURABLE_COMMAND
    assert container._kwargs == {
        "labels": {"a": "b"},
        "tmpfs": {"/var/lib/postgresql": "rw,size=1g"},
    }


def test_modern_shape_uses_the_tmpfs_attribute_not_kwargs() -> None:
    container = make_nondurable(_Modern("postgis/postgis:16-3.5-alpine"), size="2g")
    assert container.tmpfs == {"/var/lib/postgresql/data": "rw,size=2g"}
    assert "tmpfs" not in container._kwargs


def test_tmpfs_size_absent_is_default_and_malformed_fails() -> None:
    assert resolve_tmpfs_size({}) == DEFAULT_TMPFS_SIZE
    assert resolve_tmpfs_size({TMPFS_SIZE_ENV: "512m"}) == "512m"
    for bad in ("", "3", "3G", "0g", " 2g"):
        with pytest.raises(ValueError):
            resolve_tmpfs_size({TMPFS_SIZE_ENV: bad})


def _name(node: ast.Call) -> str | None:
    """``f(...)``와 ``module.f(...)`` 둘 다 ``f``로."""
    return getattr(node.func, "id", None) or getattr(node.func, "attr", None)


def _unwrapped_constructions(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wrapped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _name(node) == "make_nondurable":
            for arg in node.args:
                wrapped.update(id(inner) for inner in ast.walk(arg))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _name(node) == "PostgresContainer"
        and id(node) not in wrapped
    ]


def test_every_test_cluster_goes_through_make_nondurable() -> None:
    offenders: dict[str, list[int]] = {}
    seen = 0
    for path in sorted(_TESTS.rglob("*.py")):
        if path.name == "test_disposable_pg.py":
            continue
        if "PostgresContainer(" not in path.read_text(encoding="utf-8"):
            continue
        seen += 1
        lines = _unwrapped_constructions(path)
        if lines:
            offenders[str(path.relative_to(_TESTS))] = lines
    # 본 것에 하한을 건다 — 경로가 바뀌어 아무 파일도 안 보면 공허하게 초록이 된다.
    assert seen >= 3
    assert offenders == {}
