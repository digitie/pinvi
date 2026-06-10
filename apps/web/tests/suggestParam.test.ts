import { describe, expect, it } from 'vitest';
import { parseSuggestParam } from '@/lib/suggestParam';

describe('suggestParam', () => {
  it('유효한 lon,lat → coord', () => {
    expect(parseSuggestParam('126.978,37.566')).toEqual({ lon: 126.978, lat: 37.566 });
  });

  it('배열이면 첫 값 사용', () => {
    expect(parseSuggestParam(['127.0,37.5', 'x'])).toEqual({ lon: 127.0, lat: 37.5 });
  });

  it('한국 범위 밖 / 형식 오류 → null', () => {
    expect(parseSuggestParam('0,0')).toBeNull();
    expect(parseSuggestParam('126.978')).toBeNull();
    expect(parseSuggestParam('a,b')).toBeNull();
    expect(parseSuggestParam('')).toBeNull();
    expect(parseSuggestParam(undefined)).toBeNull();
  });
});
