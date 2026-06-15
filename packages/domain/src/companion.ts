/**
 * trip 동반자 표시 헬퍼 — `docs/api/trips.md`.
 */

import type { TripCompanionResponse, TripCompanionRole } from '@pinvi/schemas';

export const ROLE_LABEL: Record<TripCompanionRole, string> = {
  co_owner: '공동 소유자',
  editor: '편집자',
  viewer: '보기 전용',
};

export function companionDisplayName(c: {
  invited_nickname: string | null;
  invited_email: string | null;
}): string {
  return c.invited_nickname ?? c.invited_email ?? '알 수 없는 사용자';
}

/** 초대 수락(참여) 여부. */
export function companionJoined(c: Pick<TripCompanionResponse, 'joined_at'>): boolean {
  return c.joined_at != null;
}
