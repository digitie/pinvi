import { describe, expect, it } from 'vitest';
import { featureResolutionNotice } from './tripFeatureResolution';

describe('featureResolutionNotice', () => {
  it.each([
    ['not_linked', null],
    ['found', null],
    ['retired', '종료된 장소 정보'],
    ['suppressed', '비공개 장소 정보'],
    ['missing', '장소 정보 사용 불가'],
    ['unverified', '저장된 정보 · 최신 상태 확인 실패'],
  ] as const)('%s 상태의 안내를 반환한다', (state, expected) => {
    expect(featureResolutionNotice(state)).toBe(expected);
  });
});
