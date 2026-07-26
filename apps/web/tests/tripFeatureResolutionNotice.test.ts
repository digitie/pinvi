import { describe, expect, it } from 'vitest';
import { featureResolutionNotice } from '@/lib/tripFeatureResolution';

describe('featureResolutionNotice', () => {
  it.each([
    ['missing', '장소 정보 사용 불가'],
    ['unverified', '저장된 정보 · 최신 상태 확인 실패'],
    ['found', null],
    ['not_linked', null],
  ] as const)('%s 상태의 지도 안내 문구를 반환한다', (state, expected) => {
    expect(featureResolutionNotice(state)).toBe(expected);
  });
});
