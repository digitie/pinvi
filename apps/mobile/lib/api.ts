import {
  ApiClient,
  authApi,
  mobileAuthApi,
  noticePlanApi,
  poiApi,
  telegramApi,
  tripApi,
  userApi,
  MobileAuthResponseSchema,
  type MobileAuthResult,
} from '@pinvi/api-client';
import { mobileConfig } from './config';
import { clearTokens, getAccessToken, getRefreshToken, setTokens } from './tokens';

/**
 * 모바일 ApiClient. 웹은 httpOnly cookie를 쓰지만(ADR-032), 모바일은
 * SecureStore에 보관한 access token을 Authorization 헤더로 붙인다(frontend.md §4.2).
 *
 * 추가로, access 토큰 만료(401) 시 저장된 refresh 토큰으로 한 번 회전 재발급한 뒤
 * 같은 요청을 자동 재시도한다(expo-implementation-plan §3, 웹 cookie 자동 갱신 대응).
 * endpoint 함수/응답 파싱은 @pinvi/api-client 공용.
 */

let onUnauthorized: (() => void) | null = null;

/** AuthProvider가 401(refresh 실패) 시 로그아웃/리다이렉트 핸들러를 등록한다. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

// 동시 요청이 401을 동시에 만나도 refresh는 한 번만 — 진행 중 promise를 공유한다.
let refreshInFlight: Promise<boolean> | null = null;

/** 저장된 refresh 토큰으로 새 토큰을 발급받아 SecureStore에 저장한다. 성공 시 true. */
export async function refreshSession(): Promise<boolean> {
  if (refreshInFlight) {
    return refreshInFlight;
  }
  refreshInFlight = (async () => {
    const refresh = await getRefreshToken();
    if (!refresh) {
      return false;
    }
    try {
      // 래핑 fetcher를 거치지 않도록 전역 fetch를 직접 쓴다(401 재귀 방지).
      const res = await fetch(`${mobileConfig.apiBaseUrl}/mobile/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!res.ok) {
        return false;
      }
      const json: unknown = await res.json();
      const parsed = MobileAuthResponseSchema.safeParse(
        (json as { data?: unknown }).data ?? json,
      );
      if (!parsed.success) {
        return false;
      }
      await setTokens(parsed.data.access_token, parsed.data.refresh_token);
      return true;
    } catch {
      return false;
    }
  })();
  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
}

// 401을 만나면 refresh 후 1회 재시도하는 fetch 래퍼.
const refreshingFetcher: typeof fetch = async (input, init) => {
  const res = await fetch(input, init);
  if (res.status !== 401) {
    return res;
  }
  const refreshed = await refreshSession();
  if (!refreshed) {
    return res; // 원래 401 그대로 — ApiClient가 onUnauthorized 호출
  }
  const token = await getAccessToken();
  const retryInit: RequestInit = {
    ...init,
    headers: {
      ...(init?.headers as Record<string, string> | undefined),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  };
  return fetch(input, retryInit);
};

export const apiClient = new ApiClient({
  baseUrl: mobileConfig.apiBaseUrl,
  getAuthToken: () => getAccessToken(),
  fetcher: refreshingFetcher,
  onUnauthorized: () => onUnauthorized?.(),
});

/** baseUrl/토큰 어댑터가 묶인 도메인 API — 화면은 이걸 그대로 호출한다. */
export const api = {
  auth: authApi(apiClient),
  mobileAuth: mobileAuthApi(apiClient),
  trips: tripApi(apiClient),
  pois: poiApi(apiClient),
  noticePlans: noticePlanApi(apiClient),
  user: userApi(apiClient),
  telegram: telegramApi(apiClient),
};

/** 로그인/verify 성공 응답의 토큰을 SecureStore에 저장한다. */
export async function persistSession(result: MobileAuthResult): Promise<void> {
  await setTokens(result.access_token, result.refresh_token);
}

/** 로그아웃 — 서버 세션 폐기 시도 후 로컬 토큰 제거(실패해도 로컬은 비운다). */
export async function endSession(): Promise<void> {
  const refresh = await getRefreshToken();
  if (refresh) {
    try {
      await api.mobileAuth.logout(refresh);
    } catch {
      // 네트워크 실패여도 로컬 토큰은 제거한다.
    }
  }
  await clearTokens();
}
