import { ApiClient } from '@pinvi/api-client';

/**
 * 클라이언트용 API 인스턴스. cookie 기반 인증이므로 token getter 불필요.
 */
export const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
  onUnauthorized: () => {
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
  },
});
