import { describe, expect, it } from 'vitest';
import { pickSearchBias, tripSearchBias } from '@/lib/searchBias';

describe('장소 검색 지역 편향', () => {
  it('여행 장소 경계에 여백을 붙인 bbox를 만든다', () => {
    const bias = tripSearchBias([
      { lon: 128.532949, lat: 37.129651 }, // 영월 고씨굴
      { lon: 128.528906, lat: 36.550314 }, // 안동하회마을
      { lon: 128.840297, lat: 36.728037 }, // 안동 도산서원
    ]);
    expect(bias).toBe('128.27,36.30,129.10,37.38');
  });

  it('좌표가 없으면 null이고, 한국 범위 밖으로 넘친 여백은 범위 안으로 좁힌다', () => {
    expect(tripSearchBias([])).toBeNull();
    expect(tripSearchBias([{ lon: Number.NaN, lat: 37 }])).toBeNull();
    expect(tripSearchBias([{ lon: 124.1, lat: 33.1 }])).toMatch(/^124\.00,33\.00,124\.3\d,33\.3\d$/);
  });

  it('여행 맥락이 먼저, 없으면 지도 화면', () => {
    expect(pickSearchBias('1,2,3,4', '5,6,7,8')).toBe('1,2,3,4');
    expect(pickSearchBias(null, '5,6,7,8')).toBe('5,6,7,8');
    expect(pickSearchBias(null, null)).toBeNull();
  });
});
