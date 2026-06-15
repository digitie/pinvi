/**
 * trip 댓글 헬퍼 — `docs/api/trips.md`.
 *
 * 삭제 버튼은 본인 댓글에만 노출(서버가 author/owner 권한을 최종 강제).
 */

export function canDeleteComment(
  comment: { author_user_id: string | null },
  currentUserId: string | null
): boolean {
  return currentUserId != null && comment.author_user_id === currentUserId;
}
