import type { TripViewPoi } from '@pinvi/schemas';

export function featureResolutionNotice(
  state: TripViewPoi['feature_resolution_state'],
): string | null {
  switch (state) {
    case 'retired':
      return '종료된 장소 정보';
    case 'suppressed':
      return '비공개 장소 정보';
    case 'missing':
      return '장소 정보 사용 불가';
    case 'unverified':
      return '저장된 정보 · 최신 상태 확인 실패';
    case 'found':
    case 'not_linked':
      return null;
    default: {
      const exhaustive: never = state;
      return exhaustive;
    }
  }
}
