/**
 * trip 댓글 헬퍼 — `docs/api/trips.md`.
 *
 * 삭제 버튼은 작성자 또는 여행 소유자에게 노출(서버가 author/owner 권한을 최종 강제).
 */

export function canDeleteComment(
  comment: { author_user_id: string | null },
  currentUserId: string | null,
  ownerUserId?: string | null,
): boolean {
  return currentUserId != null && (comment.author_user_id === currentUserId || ownerUserId === currentUserId);
}
