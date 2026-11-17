import { describe, expect, it } from 'vitest';
import { cameraBbox, clamp } from '../lib/cameraBbox';

describe('cameraBbox', () => {
  it('지도가 알려 준 bounds를 소수 셋째 자리 bbox로 바꾼다', () => {
    expect(
      cameraBbox({
        center: [127, 37.5],
        zoom: 12,
        bounds: { sw: [126.9, 37.4], ne: [127.1, 37.6] },
      }),
    ).toBe('126.900,37.400,127.100,37.600');
  });

  it('bounds가 없으면 중심·줌으로 추정한다', () => {
    const bbox = cameraBbox({ center: [127, 37], zoom: 10 });
    const [w, s, e, n] = (bbox ?? '').split(',').map(Number);
    expect(w).toBeLessThan(127);
    expect(e).toBeGreaterThan(127);
    expect(s).toBeLessThan(37);
    expect(n).toBeGreaterThan(37);
  });

  it('국내 범위로 자르고, 화면 전체가 범위 밖이면 null', () => {
    expect(cameraBbox({ center: [127, 37], zoom: 3 })).toBe('124.000,33.000,132.000,43.000');
    expect(cameraBbox({ center: [0, 0], zoom: 10 })).toBeNull();
  });

  it('clamp는 양 끝을 넘지 않는다', () => {
    expect(clamp(3, 5, 19)).toBe(5);
    expect(clamp(25, 5, 19)).toBe(19);
    expect(clamp(12, 5, 19)).toBe(12);
  });
});
