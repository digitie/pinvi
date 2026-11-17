import { describe, expect, it } from 'vitest';
import { mapPinPlacement, mapPinSize } from '../components/mapPinLayout';

describe('mapPinLayout', () => {
  it('여행 장소 원은 16(고르면 22), 보조 원은 12(고르면 18)', () => {
    expect(mapPinSize(false, false)).toBe(16);
    expect(mapPinSize(false, true)).toBe(22);
    expect(mapPinSize(true, false)).toBe(12);
    expect(mapPinSize(true, true)).toBe(18);
  });

  it('이름 핀은 위 끝 + 원 반지름만큼 위로 — 원 중심이 좌표, 원만 있으면 기본 자리', () => {
    expect(mapPinPlacement({ label: '경포대' })).toEqual({ anchor: 'top', offset: [0, -8] });
    expect(mapPinPlacement({ label: '경포대', selected: true })).toEqual({
      anchor: 'top',
      offset: [0, -11],
    });
    expect(mapPinPlacement({ compact: true })).toBeNull();
    expect(mapPinPlacement({})).toBeNull();
  });
});
