import { ApiError, userApi } from '@pinvi/api-client';
import { hasLocationConsent } from '@pinvi/domain';
import type { LocationConsentState } from '@pinvi/domain';
import { apiClient } from './api';

/**
 * 웹의 위치 동의 상태 공유 캐시 (T-325).
 *
 * 모바일은 TanStack Query key를 공유해 철회가 지도에 즉시 반영되지만, 웹의 `(app)` 라우트에는
 * `QueryClientProvider`가 없다(admin 전용). 그래서 모듈 스코프 캐시 + 명시적 무효화로 같은 성질을
 * 만든다 — 설정에서 철회하면 `invalidateLocationConsent()`가 지도의 판단을 다시 잠근다.
 * (LBS 제16조: 철회 즉시 위치 기능 비활성.)
 *
 * 좌표는 여기에 담지 않는다. 담는 것은 "동의했는가"라는 boolean 하나뿐이다.
 */

const TTL_MS = 60_000;

let cached: { value: LocationConsentState; fetchedAt: number } | null = null;
let inFlight: Promise<LocationConsentState> | null = null;

async function load(): Promise<LocationConsentState> {
  try {
    const consents = await userApi(apiClient).getConsents();
    return hasLocationConsent(consents) ? 'granted' : 'missing';
  } catch (err) {
    // 비로그인은 오류가 아니라 "확인할 수 없는 상태"다 — 자동 경로는 조용히 중단한다.
    if (err instanceof ApiError && err.status === 401) {
      return 'unauthenticated';
    }
    return 'error';
  }
}

/**
 * 동의 상태를 돌려준다. 같은 순간의 중복 호출은 하나의 요청을 공유하고, TTL 안에서는 캐시를 쓴다.
 * `'error'`는 캐시하지 않는다 — 일시적 실패를 1분 동안 굳히면 사용자가 재시도해도 잠긴 채로 남는다.
 */
export async function getLocationConsentState(options?: {
  force?: boolean;
}): Promise<LocationConsentState> {
  const now = Date.now();
  if (!options?.force && cached && now - cached.fetchedAt < TTL_MS) {
    return cached.value;
  }
  if (inFlight) {
    return inFlight;
  }
  inFlight = load()
    .then((value) => {
      if (value !== 'error') {
        cached = { value, fetchedAt: Date.now() };
      }
      return value;
    })
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

/** 동의 기록/철회 직후 호출한다. 다음 조회가 서버를 다시 본다. */
export function invalidateLocationConsent(): void {
  cached = null;
}

/** 동의를 방금 기록했을 때 서버 왕복 없이 상태를 앞당긴다(다이얼로그 확인 직후). */
export function setLocationConsentGranted(): void {
  cached = { value: 'granted', fetchedAt: Date.now() };
}
