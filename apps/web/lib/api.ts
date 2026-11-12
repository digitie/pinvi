import { ApiClient } from '@pinvi/api-client';
import { safeLoginReturnTo } from '@/lib/loginReturnTo';

/**
 * 클라이언트용 API 인스턴스. cookie 기반 인증이므로 token getter 불필요.
 */
/** 세션을 되살릴 수 없을 때(갱신 실패 뒤에도 401) 로그인 화면으로 보낸다. */
export function redirectToLogin(): void {
  if (typeof window !== 'undefined') {
    // 복귀 경로에서 공유·저장소 토큰과 비밀 query를 지운다(#671) — `/login?next=`는 로그·Referer로 퍼진다.
    const next = safeLoginReturnTo(window.location.pathname + window.location.search + window.location.hash);
    // 갱신 실패401 뒤에는 인증된 JS 상태·캐시도 폐기하도록 같은 origin의 문서를 다시 로드한다.
    window.location.href = new URL('/login?next=' + encodeURIComponent(next), window.location.origin).href;
  }
}

export const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
  onUnauthorized: redirectToLogin,
});

/** 공개 공유 화면은 로그인 실패에도 초안을 유지하고 새 탭 로그인을 안내한다. */
export const sharedApiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});
