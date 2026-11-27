"""`even_ranks` — 서버가 다시 매기는 POI 정렬 키(웹 `packages/domain` `evenRanks`와 같은 형식)."""

from __future__ import annotations

from app.services.poi import even_ranks


def test_even_ranks_match_web_format() -> None:
    # packages/domain/src/poiMove.test.ts가 같은 값을 단언한다.
    assert even_ranks(3) == ["002s", "005k", "008c"]
    assert even_ranks(0) == []


def test_even_ranks_sort_bytewise_in_order() -> None:
    ranks = even_ranks(500)
    assert len(set(ranks)) == 500
    # COLLATE "C"(바이트 순)와 Python 문자열 비교는 ASCII에서 같다.
    assert sorted(ranks) == ranks
    assert all(len(rank) == 4 for rank in ranks)


def test_even_ranks_widen_together_when_four_digits_overflow() -> None:
    ranks = even_ranks(17_000)
    assert len({len(rank) for rank in ranks}) == 1
    assert len(ranks[0]) == 5
    assert sorted(ranks) == ranks
