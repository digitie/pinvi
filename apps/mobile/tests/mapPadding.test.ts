import { describe, expect, it } from 'vitest';
import { toMapLibrePadding } from '../lib/mapPadding';

describe('toMapLibrePadding', () => {
  it('숫자와 미지정은 그대로 둔다', () => {
    expect(toMapLibrePadding(40)).toBe(40);
    expect(toMapLibrePadding(undefined)).toBeUndefined();
  });

  it('면별 객체는 빠진 면을 0으로 채운다(native fitBounds와 같은 의미)', () => {
    expect(toMapLibrePadding({ top: 96, bottom: 320 })).toEqual({
      top: 96,
      right: 0,
      bottom: 320,
      left: 0,
    });
  });
});
