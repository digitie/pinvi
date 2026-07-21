'use client';

import { useEffect, useState } from 'react';
import { FeatureDetailModal } from '@/components/map/FeatureDetailModal';
import { FeatureDetailCardBody } from '@/components/map/FeatureDetailCardBody';
import { useFeatureDetailCard, type EnrichmentProvider } from '@/lib/useFeatureDetailCard';

/**
 * Feature 상세 모달 컨테이너(TDR, ADR-056, F5). 마커 팝업의 "상세보기"가 열고, `useFeatureDetailCard`로
 * detail-card를 로드해 `FeatureDetailModal` + `FeatureDetailCardBody`를 조립한다. 옵트인 enrichment
 * 요청 상태를 여기서 관리한다. 양 지도(FeatureMapView/TripMapView)가 공용으로 소비한다.
 */
export interface FeatureDetailModalControllerProps {
  /** null이면 모달을 닫는다(열림 = featureId != null). */
  featureId: string | null;
  /** detail-card 로드 전/이름 부재 시 표시할 제목(마커 title). */
  fallbackTitle?: string;
  onClose: () => void;
}

const ENRICH_PROVIDERS: EnrichmentProvider[] = ['kakao', 'naver'];

export function FeatureDetailModalController({
  featureId,
  fallbackTitle,
  onClose,
}: FeatureDetailModalControllerProps) {
  const [providers, setProviders] = useState<EnrichmentProvider[]>([]);
  // feature가 바뀌면 enrichment 요청 상태를 초기화(새 장소는 내부 정보만으로 시작).
  useEffect(() => {
    setProviders([]);
  }, [featureId]);

  const { card, loading, error } = useFeatureDetailCard(featureId, providers);
  const enrichmentRequested = providers.length > 0;

  const title = card?.name || fallbackTitle || '장소';
  const subtitle = card
    ? [card.category, card.address_line].filter(Boolean).join(' · ') || undefined
    : undefined;

  return (
    <FeatureDetailModal
      open={featureId != null}
      title={title}
      subtitle={subtitle}
      loading={loading && card == null}
      error={error && card == null ? error : undefined}
      onClose={onClose}
    >
      {card && (
        <FeatureDetailCardBody
          card={card}
          enrichmentRequested={enrichmentRequested}
          enriching={loading && enrichmentRequested}
          onLoadEnrichment={() => setProviders(ENRICH_PROVIDERS)}
        />
      )}
    </FeatureDetailModal>
  );
}
