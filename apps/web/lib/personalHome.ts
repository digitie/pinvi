import type { HomeTripCard } from '@pinvi/schemas';

/** 시도 17개 — '다녀온 지역 N/17'의 분모. */
export const SIDO_TOTAL = 17;

/** 다음 여행의 배지 — 진행 중 / 오늘 출발 / D-n. */
export function nextTripBadge(trip: Pick<HomeTripCard, 'phase' | 'days_until'>): string | null {
  if (trip.phase === 'ongoing') return '여행 중';
  if (trip.phase !== 'upcoming' || trip.days_until == null) return null;
  return trip.days_until === 0 ? '오늘 출발' : `D-${trip.days_until}`;
}
