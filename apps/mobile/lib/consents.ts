import { useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@pinvi/api-client';
import { hasLocationConsent, locationConsentItems } from '@pinvi/domain';
import { api } from './api';

/** 동의 현황 query key — 설정 화면(철회)과 위치 gate(지도)가 같은 캐시를 공유한다. */
export const CONSENTS_QUERY_KEY = ['consents'] as const;

export type LocationConsentStatus = 'loading' | 'granted' | 'missing' | 'unauthenticated' | 'error';

/**
 * 위치 기능 gate — 웹 `FeatureMapView.handleMyLocation` 대응(issue #215/#203).
 * `lbs_tos` + `location_collection`이 모두 유효할 때만 `granted`(`hasLocationConsent`).
 * 철회(설정 > 동의 관리)하면 같은 query가 invalidate돼 위치 기능이 자동으로 잠긴다.
 * `grant()`는 두 동의를 PUT하고 캐시를 갱신한다(웹 `LocationConsentDialog` "동의하고 사용").
 */
export function useLocationConsent(): {
  status: LocationConsentStatus;
  grant: () => Promise<void>;
  refetch: () => Promise<unknown>;
} {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: CONSENTS_QUERY_KEY,
    queryFn: () => api.user.getConsents(),
    staleTime: 60_000,
  });

  const grant = useCallback(async () => {
    await api.user.putConsents(locationConsentItems());
    await queryClient.invalidateQueries({ queryKey: CONSENTS_QUERY_KEY });
  }, [queryClient]);

  // 비로그인(401)은 오류가 아니라 "확인할 수 없는 상태"다 — 자동 경로는 조용히 중단해야 하고,
  // 사용자에게 "동의 저장 실패" 같은 잘못된 원인을 보여주면 안 된다.
  const status: LocationConsentStatus = query.isPending
    ? 'loading'
    : query.isError
      ? query.error instanceof ApiError && query.error.status === 401
        ? 'unauthenticated'
        : 'error'
      : hasLocationConsent(query.data)
        ? 'granted'
        : 'missing';

  return { status, grant, refetch: query.refetch };
}
