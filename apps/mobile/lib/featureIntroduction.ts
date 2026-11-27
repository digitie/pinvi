import { useQuery } from '@tanstack/react-query';
import { featureApi } from '@pinvi/api-client';
import { cardIntroduction, cardVisitGuide } from '@pinvi/domain';
import type { SourceIntroduction, VisitGuide } from '@pinvi/schemas';
import { apiClient } from './api';

export interface FeatureSourceInfo {
  introduction: SourceIntroduction | null;
  visitGuide: VisitGuide | null;
}

/**
 * 장소의 출처 소개(소개문·원본 이미지·출처/공공누리)와 이용 안내(이용시간·요금·무장애·반려동물) — 웹
 * `PlaceInfoPanel`과 같은 `GET /features/{id}/detail-card` 서버 투영을 읽는다(저장하지 않는다). 지도 feature가
 * 없는 장소는 묻지 않는다. 보여 줄 값이 없거나 읽지 못하면 각각 null이다(빈 항목을 만들지 않는다).
 */
export function useFeatureSourceInfo(featureId: string | null): FeatureSourceInfo {
  const query = useQuery({
    queryKey: ['feature', 'detail-card', featureId],
    queryFn: ({ signal }) => featureApi(apiClient).detailCard(featureId as string, {}, { signal }),
    enabled: Boolean(featureId),
    retry: false,
    staleTime: 10 * 60_000,
  });
  const card = query.data;
  return { introduction: cardIntroduction(card), visitGuide: cardVisitGuide(card) };
}
