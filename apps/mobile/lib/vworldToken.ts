import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { apiClient } from './api';

const VWorldTokenSchema = z.object({
  api_key: z.string(),
  key_source: z.literal('server-issued'),
  ttl_seconds: z.number(),
});

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
