import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { z } from 'zod';
import { apiClient } from './api';

const VWorldTokenSchema = z.object({
  api_key: z.string(),
  key_source: z.literal('server-issued'),
  ttl_seconds: z.number(),
});

export type VWorldTokenQuery = UseQueryResult<z.infer<typeof VWorldTokenSchema>>;

/**
 * VWorld 지도 키 — 앱에 번들하지 않고 `GET /mobile/vworld/token`으로 server-issued 발급받는다(ADR-043).
 * 탐색 지도·여행 지도가 같은 캐시를 쓴다.
 */
export function useVWorldToken() {
  return useQuery({
    queryKey: ['mobile', 'vworld-token'],
    queryFn: () =>
      apiClient.request('/mobile/vworld/token', { method: 'GET', schema: VWorldTokenSchema }),
    retry: false,
    staleTime: 60_000,
  });
}

/**
 * 로그인 없는 공유 화면의 지도 키 — 그 여행의 유효한 공유 토큰으로만 받는다
 * (`GET /mobile/shared/{tripId}/{token}/vworld/token`, 웹 공유 화면은 빌드타임 공개 설정 키를 쓴다).
 */
export function useSharedVWorldToken(tripId: string, token: string) {
  return useQuery({
    queryKey: ['mobile', 'vworld-token', 'shared', tripId, token],
    queryFn: () =>
      apiClient.request(
        `/mobile/shared/${encodeURIComponent(tripId)}/${encodeURIComponent(token)}/vworld/token`,
        { method: 'GET', schema: VWorldTokenSchema },
      ),
    enabled: Boolean(tripId && token),
    retry: false,
    staleTime: 60_000,
  });
}
