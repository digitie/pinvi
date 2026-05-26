"""LexoRank — POI sort_order. SPEC V8 E-6 (Critical).

JS LexoRank와 PG `COLLATE "C"` 정렬 결과 일치.
"""

from __future__ import annotations

import string

_BASE_CHARS = string.digits + string.ascii_lowercase  # 0-9, a-z (ASCII 정렬 일관)
_MIN_CHAR = _BASE_CHARS[0]
_MAX_CHAR = _BASE_CHARS[-1]


def between(prev: str | None, next_: str | None) -> str:
    """`prev` < return < `next_` 인 새 키 생성.

    - prev=None → "a0" 처음 / next_=None → 마지막 + "0"
    - prev=next_ 또는 잘못된 순서 → ValueError
    """
    if prev is not None and next_ is not None and prev >= next_:
        raise ValueError(f"prev must be strictly less than next: {prev!r} >= {next_!r}")

    if prev is None and next_ is None:
        return "a0"
    if prev is None:
        return _before(next_ or "")
    if next_ is None:
        return _after(prev)
    return _midpoint(prev, next_)


def _after(key: str) -> str:
    """key 뒤 — 마지막 글자 + 1 또는 "0" 추가."""
    if not key:
        return "a0"
    last = key[-1]
    if last < _MAX_CHAR:
        idx = _BASE_CHARS.index(last)
        return key[:-1] + _BASE_CHARS[idx + 1]
    return key + "0"


def _before(key: str) -> str:
    if not key:
        return "a0"
    first = key[0]
    if first > _MIN_CHAR:
        idx = _BASE_CHARS.index(first)
        return _BASE_CHARS[idx - 1] + "z"
    return _MIN_CHAR + _before(key[1:])


def _midpoint(a: str, b: str) -> str:
    # 가장 단순한 접근 — 공통 prefix 보존 + suffix midpoint
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    prefix = a[:i]
    a_suffix = a[i:]
    b_suffix = b[i:]
    # prefix가 같고 한 쪽이 다른 쪽의 prefix면 confl
    if a_suffix == "":
        return prefix + _after(b_suffix)[: max(1, len(b_suffix))]
    if b_suffix == "":
        return prefix + _after(a_suffix)
    a0 = a_suffix[0]
    b0 = b_suffix[0]
    a_idx = _BASE_CHARS.index(a0)
    b_idx = _BASE_CHARS.index(b0)
    if b_idx - a_idx > 1:
        mid_idx = (a_idx + b_idx) // 2
        return prefix + _BASE_CHARS[mid_idx]
    # 인접 — a 끝에 z 직전 추가
    return prefix + a0 + _after(a_suffix[1:] or "0")
