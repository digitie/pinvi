"""LexoRank 단위 테스트."""

from __future__ import annotations

import pytest

from app.services.lexorank import between


def test_between_initial() -> None:
    assert between(None, None) == "a0"


def test_between_after_prev() -> None:
    key = between("a0", None)
    assert key > "a0"


def test_between_before_next() -> None:
    key = between(None, "z9")
    assert key < "z9"


def test_between_two_keys_ascii_order() -> None:
    a = "a0"
    b = "a2"
    mid = between(a, b)
    # COLLATE "C" ASCII 순서 — a < mid < b
    assert a < mid < b


def test_between_invalid_order_raises() -> None:
    with pytest.raises(ValueError):
        between("z", "a")
