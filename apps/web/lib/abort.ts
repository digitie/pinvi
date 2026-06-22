/**
 * fetch/AbortController가 요청 취소 시 던지는 AbortError 판별.
 *
 * 빠르게 superseded되는 검색(map viewport pan, 검색어 변경)에서 직전 요청을 abort하면
 * 그 Promise는 AbortError로 reject된다. 이는 정상 취소이므로 사용자에게 오류로 노출하지
 * 않는다 (kor-travel-concierge #111 — abort 전파 패턴).
 */
export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError';
}
