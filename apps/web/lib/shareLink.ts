/**
 * trip 공유 링크 상태/표시 — `docs/api/trips.md`.
 */

import type { TripShareLinkVisibility } from '@pinvi/schemas';

export type ShareStatus = 'active' | 'expired' | 'revoked';

export function shareLinkStatus(
  link: { expires_at: string | null; revoked_at: string | null },
  now: number = Date.now()
): ShareStatus {
  if (link.revoked_at) return 'revoked';
  if (link.expires_at && new Date(link.expires_at).getTime() <= now) return 'expired';
  return 'active';
}

export const SHARE_STATUS_LABEL: Record<ShareStatus, string> = {
  active: '활성',
  expired: '만료',
  revoked: '철회',
};

export const VISIBILITY_LABEL: Record<TripShareLinkVisibility, string> = {
  view_only: '보기 전용',
  comment: '댓글 가능',
  edit: '편집 가능',
};
