import { ApiError } from '@pinvi/api-client';

/**
 * 사용자가 **스스로 해소할 수 있는** 403 코드. 이 목록에 있으면 서버가 보낸 안내 문구를 그대로
 * 보여준다 — 권한 부족과 달리, 사용자가 할 수 있는 행동이 있기 때문이다.
 */
const RECOVERABLE_FORBIDDEN_CODES = new Set(['LOCATION_CONSENT_REQUIRED']);

/** 위치 동의가 없어서 거절된 요청인가 (ADR-063). 호출부는 동의 재요청 흐름으로 연결한다. */
export function isLocationConsentRequired(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403 && error.code === 'LOCATION_CONSENT_REQUIRED';
}

/**
 * 사용자에게 보여줄 친화적인 오류 문구를 만든다.
 *
 * - `ApiError`: status별로 안내 문구를 구분한다 (401/403/404/5xx).
 * - 일반 `Error`: 메시지가 있으면 그대로, 없으면 기본 문구.
 * - 그 외(문자열·undefined 등): 기본 문구.
 *
 * Next.js error boundary가 넘기는 digest는 별도(`errorDigest`)로 처리한다.
 */
export function friendlyErrorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return '로그인이 필요하거나 세션이 만료되었습니다.';
    // 서버가 **무엇을 하면 되는지** 아는 403은 그 문구를 그대로 쓴다. 일괄로 "권한이 없습니다"라고
    // 덮으면 고칠 수 있는 상태가 고칠 수 없는 상태처럼 보인다 — 위치 동의가 정확히 그런 경우다
    // (동의만 하면 되는데 권한 문제로 읽힌다). 코드가 붙지 않은 403만 일반 문구로 떨어뜨린다.
    if (error.status === 403) {
      return RECOVERABLE_FORBIDDEN_CODES.has(error.code) && error.message
        ? error.message
        : '이 작업을 수행할 권한이 없습니다.';
    }
    if (error.status === 404) return '요청한 항목을 찾을 수 없습니다.';
    if (error.status >= 500)
      return '서버에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.';
    return error.message || '요청을 처리하지 못했습니다.';
  }
  // 한글이 하나라도 있으면 우리 코드가 사용자에게 보이려고 의도적으로 던진 문구로 본다
  // (실제로 저장소 전체의 의도적 `throw new Error(...)` 사용자 안내 문구는 전부 한글이다).
  // 한글이 없으면 `fetch failed: java.net.ConnectException…`류 네트워크/런타임 원문일
  // 가능성이 높다(T-319) — 그런 원문을 그대로 보여주면 사용자가 알 수도 고칠 수도 없다.
  if (error instanceof Error && error.message && /[가-힣]/.test(error.message)) {
    return error.message;
  }
  return '예기치 못한 오류가 발생했습니다.';
}

/**
 * Next.js가 production 빌드에서 error boundary로 넘기는 `digest`를 추출한다.
 * 서버 로그와 대조할 수 있는 짧은 해시 — 사용자에게 참조용으로만 노출한다.
 */
export function errorDigest(error: unknown): string | null {
  if (
    error &&
    typeof error === 'object' &&
    'digest' in error &&
    typeof (error as { digest?: unknown }).digest === 'string'
  ) {
    return (error as { digest: string }).digest;
  }
  return null;
}
