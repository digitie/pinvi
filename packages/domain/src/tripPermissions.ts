import type { TripView } from '@pinvi/schemas';

/**
 * 이 사용자가 여행을 편집할 수 있는가 — 소유자이거나 동행 역할이 보기 전용(viewer)이 아니면 true.
 * 화면 표시용 판정이다(실제 권한은 서버가 강제한다). 사용자를 모르면 false.
 */
export function canEditTrip(
  view: Pick<TripView, 'trip' | 'companions'>,
  userId: string | null | undefined,
): boolean {
  if (!userId) return false;
  if (view.trip.owner_user_id === userId) return true;
  return view.companions.some(
    (companion) => companion.user_id === userId && companion.role !== 'viewer',
  );
}
