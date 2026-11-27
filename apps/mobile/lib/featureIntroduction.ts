import { useQuery } from '@tanstack/react-query';
import { featureApi } from '@pinvi/api-client';
import type { SourceIntroduction } from '@pinvi/schemas';
import { apiClient } from './api';

/**
 * 장소의 출처 소개(TourAPI 소개문·대표 이미지·출처/공공누리 표시) — 웹 `PlaceInfoPanel`과 같은
 * `GET /features/{id}/detail-card` 서버 투영을 읽는다(저장하지 않는다). 지도 feature가 없는 장소는 묻지 않는다.
 * 보여 줄 소개가 없거나 읽지 못하면 null이다(빈 항목을 만들지 않는다).
 */
export function useFeatureIntroduction(featureId: string | null): SourceIntroduction | null {
  const query = useQuery({
    queryKey: ['feature', 'detail-card', featureId],
    queryFn: ({ signal }) => featureApi(apiClient).detailCard(featureId as string, {}, { signal }),
    enabled: Boolean(featureId),
    retry: false,
    staleTime: 10 * 60_000,
  });
  const card = query.data;
  return card?.kind === 'place' ? card.introduction : null;
}
