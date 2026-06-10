import { ApiError } from '@tripmate/api-client';

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
    if (error.status === 403) return '이 작업을 수행할 권한이 없습니다.';
    if (error.status === 404) return '요청한 항목을 찾을 수 없습니다.';
    if (error.status >= 500) return '서버에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.';
    return error.message || '요청을 처리하지 못했습니다.';
  }
  if (error instanceof Error && error.message) {
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
