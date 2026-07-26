import type { TripViewPoi } from '@pinvi/schemas';

export function featureResolutionNotice(
  state: TripViewPoi['feature_resolution_state'],
): string | null {
  if (state === 'missing') return '장소 정보 사용 불가';
  if (state === 'unverified') {
    return '저장된 정보 · 최신 상태 확인 실패';
  }
  return null;
}
