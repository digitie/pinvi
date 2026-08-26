'use client';

import { useEffect, useState } from 'react';
import { ApiError, featureApi } from '@pinvi/api-client';
import type { FeatureDetailCard } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { isAbortError } from '@/lib/abort';

export type EnrichmentProvider = 'kakao' | 'naver';

export interface UseFeatureDetailCardResult {
  card: FeatureDetailCard | null;
  loading: boolean;
  error: string | null;
}

/**
 * `GET /features/{id}/detail-card`를 로드한다(ADR-056). `providers`를 주면 옵트인 외부 enrichment를
 * 요청하며(display-only), featureId/providers가 바뀌면 직전 요청을 취소하고 재조회한다. 지도 컴포넌트가
 * TanStack Query 대신 쓰는 수동 fetch+abort 관례를 따른다(`FeatureMapView` 동일).
 */
export function useFeatureDetailCard(
  featureId: string | null,
  providers: EnrichmentProvider[] = [],
): UseFeatureDetailCardResult {
  const [card, setCard] = useState<FeatureDetailCard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // providers 배열은 렌더마다 새 참조가 될 수 있으므로 문자열 키로 안정화해 deps에 쓴다.
  const providersKey = providers.join(',');

  // featureId/providersKey가 바뀐 순간을 렌더 중에 잡아 card/error/loading을 그 자리에서
  // 리셋한다(react-hooks/set-state-in-effect: effect 안 동기 setState 금지 — 공식 "Adjusting
  // state when a prop changes" 패턴). 실제 fetch는 아래 effect에서 비동기로만 수행한다.
  const [prevFeatureId, setPrevFeatureId] = useState(featureId);
  const [prevProvidersKey, setPrevProvidersKey] = useState(providersKey);
  if (featureId !== prevFeatureId || providersKey !== prevProvidersKey) {
    setPrevFeatureId(featureId);
    setPrevProvidersKey(providersKey);
    setCard(null);
    setError(null);
    setLoading(!!featureId);
  }

  useEffect(() => {
    if (!featureId) return;
    const controller = new AbortController();
    void (async () => {
      try {
        const requested = providersKey
          ? (providersKey.split(',') as EnrichmentProvider[])
          : undefined;
        const result = await featureApi(apiClient).detailCard(
          featureId,
          { providers: requested },
          { signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        setCard(result);
      } catch (err) {
        if (isAbortError(err) || controller.signal.aborted) return;
        setError(err instanceof ApiError ? err.message : '상세 정보를 불러오지 못했습니다.');
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [featureId, providersKey]);

  return { card, loading, error };
}
