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


def test_rank_between_stays_strictly_between_neighbours() -> None:
    from app.services.poi import rank_between

    assert rank_between(None, None) == "002s"
    assert rank_between("a0", "a1") == "a0i"
    assert rank_between("002s", "005k") == "003"
    assert rank_between(None, "002s") == "001"
    for prev, next_ in [("a0", "a0m"), ("a0m", None), ("zz", None), ("a", "b"), ("005k", "005l")]:
        key = rank_between(prev, next_)
        assert key is not None
        assert prev < key and (next_ is None or key < next_), (prev, next_, key)


def test_rank_between_gives_up_where_no_key_fits() -> None:
    from app.services.poi import rank_between

    # `p` < ? < `p0` 인 키는 없다 — 호출자가 그 일자를 다시 매긴다.
    assert rank_between("p", "p0") is None
    assert rank_between(None, "0") is None
    # 허용 문자 밖의 키(옛 임시 키 등)도 만들지 않는다.
    assert rank_between("A", "B") is None


def test_rank_between_random_neighbours() -> None:
    import random

    from app.services.poi import rank_between

    rng = random.Random(20261127)  # noqa: S311 — 재현 가능한 시험 입력
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    for _ in range(2000):
        a, b = sorted(
            "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 6))) for _ in range(2)
        )
        if a == b:
            continue
        key = rank_between(a, b)
        if key is not None:
            assert a < key < b and len(key) <= 80


def test_rank_between_repeated_inserts_at_same_spot_stay_short() -> None:
    from app.services.poi import rank_between

    low, high = "002s", "005k"
    for _ in range(60):
        key = rank_between(low, high)
        assert key is not None and low < key < high
        high = key
    assert len(high) <= 80
