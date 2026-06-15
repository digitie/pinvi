/**
 * trip 공유 링크 URL — 프론트 공유 뷰 라우트(`/shared/{tripId}/{token}`)로 구성.
 * 서버 응답 `url` 대신 실제 구현된 라우트를 가리키게 한다.
 */

export function buildShareUrl(origin: string, tripId: string, token: string): string {
  return `${origin}/shared/${tripId}/${token}`;
}
