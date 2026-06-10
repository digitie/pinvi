import { describe, expect, it } from 'vitest';
import { formatDistanceMeters } from '@/lib/distance';

describe('distance', () => {
  it('formatDistanceMeters: m / km / null', () => {
    expect(formatDistanceMeters(0)).toBe('0m');
    expect(formatDistanceMeters(950)).toBe('950m');
    expect(formatDistanceMeters(1000)).toBe('1.0km');
    expect(formatDistanceMeters(12500)).toBe('12.5km');
    expect(formatDistanceMeters(null)).toBe('거리 정보 없음');
  });
});
