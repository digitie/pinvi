import type { TripWeatherRefreshResponse } from '@pinvi/schemas';

/** 새로고침 결과 안내 — 다시 읽은 뒤에도 비어 있을 때 이유를 짧게 말한다. */
export function weatherRefreshMessage(result: TripWeatherRefreshResponse): string {
  if (result.refreshed > 0) {
    return '날씨를 다시 확인했습니다. 예보는 보통 열흘 앞까지만 있습니다.';
  }
  if (result.cooldown > 0) {
    return `방금 확인했습니다. ${result.retry_after_seconds ?? 60}초 뒤 다시 시도할 수 있습니다.`;
  }
  if (result.failed > 0) return '날씨 서비스에 연결하지 못했습니다. 잠시 뒤 다시 시도하세요.';
  if (result.no_data > 0) return '이 장소 근처에 날씨 관측·예보 지점이 없습니다.';
  return '좌표가 있는 장소만 날씨를 확인할 수 있습니다.';
}
