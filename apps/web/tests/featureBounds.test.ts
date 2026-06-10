import { describe, expect, it } from 'vitest';
import { clampZoom, toBboxParam } from '@/lib/featureBounds';

describe('featureBounds', () => {
  it('toBboxParam: 한국 범위 내 viewport 는 그대로(5자리)', () => {
    expect(toBboxParam(126.9, 37.4, 127.1, 37.6)).toBe('126.90000,37.40000,127.10000,37.60000');
  });

  it('toBboxParam: 한국 범위 밖은 clamp (바다/국경)', () => {
    // 경도 120(서해 밖)~135(동해 밖), 위도 30~45 → 124~132 / 33~43 로 clamp.
    expect(toBboxParam(120, 30, 135, 45)).toBe('124.00000,33.00000,132.00000,43.00000');
  });

  it('toBboxParam: west>east / south>north 도 min/max 로 정규화', () => {
    expect(toBboxParam(127.1, 37.6, 126.9, 37.4)).toBe('126.90000,37.40000,127.10000,37.60000');
  });

  it('clampZoom: 5~19 정수로 clamp', () => {
    expect(clampZoom(12.4)).toBe(12);
    expect(clampZoom(2)).toBe(5);
    expect(clampZoom(25)).toBe(19);
  });
});
