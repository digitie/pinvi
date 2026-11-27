import { describe, expect, it } from 'vitest';
import {
  applyPoiMove,
  evenRanks,
  isNoopPoiMove,
  poiRowDropTarget,
  poiStepMoveTarget,
  type PoiDayOrder,
} from './poiRank';

const days: PoiDayOrder[] = [
  { dayIndex: 1, poiIds: ['a', 'b', 'c'] },
  { dayIndex: 2, poiIds: [] },
  { dayIndex: 3, poiIds: ['d'] },
];

describe('장소 이동 자리', () => {
  it('행 위쪽 절반은 그 행 앞, 아래쪽 절반은 다음 행 앞(마지막이면 맨 끝)', () => {
    expect(poiRowDropTarget(days[0]!, 1, 'before')).toEqual({ dayIndex: 1, beforePoiId: 'b' });
    expect(poiRowDropTarget(days[0]!, 1, 'after')).toEqual({ dayIndex: 1, beforePoiId: 'c' });
    expect(poiRowDropTarget(days[0]!, 2, 'after')).toEqual({ dayIndex: 1, beforePoiId: null });
  });

  it('같은 일자에서 자기 앞·바로 다음 앞은 제자리, 다른 일자는 항상 이동', () => {
    expect(isNoopPoiMove('b', days[0]!, { dayIndex: 1, beforePoiId: 'b' })).toBe(true);
    expect(isNoopPoiMove('b', days[0]!, { dayIndex: 1, beforePoiId: 'c' })).toBe(true);
    expect(isNoopPoiMove('c', days[0]!, { dayIndex: 1, beforePoiId: null })).toBe(true);
    expect(isNoopPoiMove('b', days[0]!, { dayIndex: 1, beforePoiId: 'a' })).toBe(false);
    expect(isNoopPoiMove('b', days[0]!, { dayIndex: 1, beforePoiId: null })).toBe(false);
    expect(isNoopPoiMove('c', days[0]!, { dayIndex: 2, beforePoiId: null })).toBe(false);
  });

  it('한 칸 이동은 일자 경계를 넘는다 — 빈 일자도 거친다', () => {
    expect(poiStepMoveTarget(days, 'b', 'up')).toEqual({ dayIndex: 1, beforePoiId: 'a' });
    expect(poiStepMoveTarget(days, 'a', 'down')).toEqual({ dayIndex: 1, beforePoiId: 'c' });
    expect(poiStepMoveTarget(days, 'b', 'down')).toEqual({ dayIndex: 1, beforePoiId: null });
    expect(poiStepMoveTarget(days, 'c', 'down')).toEqual({ dayIndex: 2, beforePoiId: null });
    expect(poiStepMoveTarget(days, 'd', 'up')).toEqual({ dayIndex: 2, beforePoiId: null });
    expect(poiStepMoveTarget(days, 'a', 'up')).toBeNull();
    expect(poiStepMoveTarget(days, 'd', 'down')).toBeNull();
    expect(poiStepMoveTarget(days, 'zz', 'down')).toBeNull();
  });

  it('applyPoiMove는 출발 일자에서 빼고 도착 일자 기준 장소 앞에 넣는다(원본 불변)', () => {
    expect(applyPoiMove(days, 'c', { dayIndex: 3, beforePoiId: 'd' })).toEqual([
      { dayIndex: 1, poiIds: ['a', 'b'] },
      { dayIndex: 2, poiIds: [] },
      { dayIndex: 3, poiIds: ['c', 'd'] },
    ]);
    expect(applyPoiMove(days, 'a', { dayIndex: 2, beforePoiId: null })[1]).toEqual({
      dayIndex: 2,
      poiIds: ['a'],
    });
    expect(applyPoiMove(days, 'a', { dayIndex: 1, beforePoiId: null })[0]!.poiIds).toEqual([
      'b',
      'c',
      'a',
    ]);
    expect(days[0]!.poiIds).toEqual(['a', 'b', 'c']);
  });

  it('서버 `even_ranks`와 같은 키 형식이다', () => {
    // apps/api/app/services/poi.py even_ranks(3) == ['002s', '005k', '008c']
    expect(evenRanks(3)).toEqual(['002s', '005k', '008c']);
  });
});
