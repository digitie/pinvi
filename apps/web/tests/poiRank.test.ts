import { describe, expect, it } from 'vitest';
import { appendRank, arrayMove, evenRanks, reorderMoves } from '@/lib/poiRank';

describe('poiRank', () => {
  it('evenRanks: 사전식(COLLATE C) 오름차순 == 입력 순서', () => {
    const ranks = evenRanks(5);
    expect(ranks).toHaveLength(5);
    expect([...ranks].sort()).toEqual(ranks); // 바이트 순 정렬해도 그대로
    expect(new Set(ranks).size).toBe(5); // 중복 없음
  });

  it('appendRank: 마지막 키 뒤로 정렬', () => {
    const last = evenRanks(3)[2]!;
    const appended = appendRank(last);
    expect([last, appended].sort()).toEqual([last, appended]);
    expect(appendRank(null)).toBe(evenRanks(1)[0]);
    expect(appendRank('')).toBe(evenRanks(1)[0]);
  });

  it('arrayMove: 불변 + 범위 밖 무시', () => {
    const base = ['a', 'b', 'c', 'd'];
    expect(arrayMove(base, 0, 2)).toEqual(['b', 'c', 'a', 'd']);
    expect(arrayMove(base, 3, 0)).toEqual(['d', 'a', 'b', 'c']);
    expect(base).toEqual(['a', 'b', 'c', 'd']); // 원본 불변
    expect(arrayMove(base, 0, 9)).toEqual(base);
    expect(arrayMove(base, 1, 1)).toEqual(base);
  });

  it('reorderMoves: 변경된 항목만, 새 순서대로 정렬되는 키', () => {
    // 현재 키가 모두 새 키와 다른 초기 상태.
    const order = ['p1', 'p2', 'p3'];
    const current = new Map([
      ['p1', 'old1'],
      ['p2', 'old2'],
      ['p3', 'old3'],
    ]);
    const moves = reorderMoves(order, current);
    expect(moves).toHaveLength(3);
    // move 의 new_sort_order 가 order 순서대로 오름차순.
    const keys = moves.map((m) => m.new_sort_order);
    expect([...keys].sort()).toEqual(keys);
  });

  it('reorderMoves: 이미 올바른 키면 move 없음', () => {
    const order = ['p1', 'p2'];
    const ranks = evenRanks(2);
    const current = new Map([
      ['p1', ranks[0]!],
      ['p2', ranks[1]!],
    ]);
    expect(reorderMoves(order, current)).toEqual([]);
  });
});
