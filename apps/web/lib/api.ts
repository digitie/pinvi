import { ApiClient } from '@pinvi/api-client';

/**
 * 클라이언트용 API 인스턴스. cookie 기반 인증이므로 token getter 불필요.
 */
/** 세션을 되살릴 수 없을 때(갱신 실패 뒤에도 401) 로그인 화면으로 보낸다. */
export function redirectToLogin(): void {
  if (typeof window !== 'undefined') {
    window.location.href = '/login';
  }
}

export const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
  onUnauthorized: redirectToLogin,
});
