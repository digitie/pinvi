import { describe, expect, it } from 'vitest';
import { mapPinPlacement, mapPinSize } from '../components/mapPinLayout';

describe('mapPinLayout', () => {
  it('아이콘 든 여행 장소 원은 22(고르면 26), 아이콘 없으면 16(22), 보조 원은 12(18)', () => {
    expect(mapPinSize({ icon: 'cafe' })).toBe(22);
    expect(mapPinSize({ icon: 'cafe', selected: true })).toBe(26);
    expect(mapPinSize({})).toBe(16);
    expect(mapPinSize({ selected: true })).toBe(22);
    expect(mapPinSize({ compact: true })).toBe(12);
    expect(mapPinSize({ compact: true, selected: true })).toBe(18);
  });

  it('이름 핀은 위 끝 + 원 반지름만큼 위로 — 원 중심이 좌표, 원만 있으면 기본 자리', () => {
    expect(mapPinPlacement({ label: '경포대' })).toEqual({ anchor: 'top', offset: [0, -8] });
    expect(mapPinPlacement({ label: '경포대', selected: true })).toEqual({
      anchor: 'top',
      offset: [0, -11],
    });
    expect(mapPinPlacement({ label: '카페', icon: 'cafe' })).toEqual({
      anchor: 'top',
      offset: [0, -11],
    });
    expect(mapPinPlacement({ compact: true })).toBeNull();
    expect(mapPinPlacement({})).toBeNull();
  });
});
