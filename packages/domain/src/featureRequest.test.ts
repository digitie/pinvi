import { describe, expect, it } from 'vitest';
import { buildNewPlaceRequest, parseCategories } from './featureRequest';

describe('featureRequest', () => {
  it('parseCategories: trim·중복 제거·최대 10', () => {
    expect(parseCategories('카페, 디저트 ,카페')).toEqual(['카페', '디저트']);
    expect(parseCategories('')).toEqual([]);
    expect(parseCategories(Array.from({ length: 15 }, (_, i) => `c${i}`).join(','))).toHaveLength(10);
  });

  it('buildNewPlaceRequest: new_place + coord + note 정규화', () => {
    expect(
      buildNewPlaceRequest(
        { kind: 'place', title: '  새 카페 ', categories: '카페', note: '  ' },
        { lon: 126.97, lat: 37.57 }
      )
    ).toEqual({
      type: 'new_place',
      kind: 'place',
      title: '새 카페',
      coord: { lon: 126.97, lat: 37.57 },
      categories: ['카페'],
      note: null,
    });
  });

  it('buildNewPlaceRequest: event + note 유지', () => {
    const res = buildNewPlaceRequest(
      { kind: 'event', title: '벚꽃축제', categories: '', note: '4월 초' },
      { lon: 127, lat: 37 }
    );
    expect(res.kind).toBe('event');
    expect(res.note).toBe('4월 초');
    expect(res.categories).toEqual([]);
  });
});
