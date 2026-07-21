import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { FeatureDetailCard, ExternalEnrichment } from '@pinvi/schemas';
import { FeatureDetailCardBody } from '@/components/map/FeatureDetailCardBody';

function placeCard(over: Partial<Extract<FeatureDetailCard, { kind: 'place' }>> = {}) {
  return {
    kind: 'place',
    feature_id: 'place:1',
    name: '스타벅스 광안리',
    coord: { lon: 129.12, lat: 35.15 },
    category: '카페',
    address_line: '부산 광안로 1',
    marker_color: 'P-07',
    marker_icon: 'cafe',
    homepage_url: 'https://sb.example',
    status: 'active',
    enrichment: [],
    degraded_providers: [],
    phone: '051-000-0000',
    business_hours: '09:00-22:00',
    ...over,
  } as Extract<FeatureDetailCard, { kind: 'place' }>;
}

describe('FeatureDetailCardBody', () => {
  it('place 카드의 일반 필드를 렌더한다', () => {
    render(<FeatureDetailCardBody card={placeCard()} />);
    expect(screen.getByTestId('feature-detail-card-body-address')).toHaveTextContent('부산 광안로 1');
    expect(screen.getByTestId('feature-detail-card-body-phone')).toHaveTextContent('051-000-0000');
    expect(screen.getByTestId('feature-detail-card-body-hours')).toHaveTextContent('09:00-22:00');
    expect(screen.getByTestId('feature-detail-card-body-category')).toHaveTextContent('카페');
  });

  it('place 카드는 enrichment 미요청 시 "더 보기" 버튼을 보인다', () => {
    const onLoad = vi.fn();
    render(<FeatureDetailCardBody card={placeCard()} onLoadEnrichment={onLoad} />);
    const btn = screen.getByTestId('feature-detail-card-body-load-enrichment');
    fireEvent.click(btn);
    expect(onLoad).toHaveBeenCalledTimes(1);
  });

  it('matched enrichment 행에 attribution + back-link + 전화를 보인다', () => {
    const enrichment: ExternalEnrichment[] = [
      {
        provider: 'kakao',
        matched: true,
        name: '스타벅스 광안리점',
        address: '부산 수영구',
        phone: '051-111-2222',
        provider_url: 'http://place.map.kakao.com/k1',
        external_id: 'k1',
      },
    ];
    render(
      <FeatureDetailCardBody
        card={placeCard({ enrichment })}
        enrichmentRequested
      />,
    );
    const row = screen.getByTestId('feature-detail-enrichment-kakao');
    expect(row).toHaveTextContent('카카오');
    expect(row).toHaveTextContent('051-111-2222');
    const link = screen.getByTestId('feature-detail-enrichment-kakao-link');
    expect(link).toHaveAttribute('href', 'http://place.map.kakao.com/k1');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('matched=false면 "일치하는 외부 정보 없음"을 보인다', () => {
    const enrichment: ExternalEnrichment[] = [
      { provider: 'naver', matched: false, name: null, address: null, phone: null, provider_url: null, external_id: null },
    ];
    render(<FeatureDetailCardBody card={placeCard({ enrichment })} enrichmentRequested />);
    expect(screen.getByTestId('feature-detail-enrichment-naver')).toHaveTextContent(
      '일치하는 외부 정보 없음',
    );
  });

  it('degraded_providers가 있으면 안내를 보인다', () => {
    render(
      <FeatureDetailCardBody
        card={placeCard({ enrichment: [], degraded_providers: ['kakao'] })}
        enrichmentRequested
      />,
    );
    expect(screen.getByTestId('feature-detail-card-body-enrichment-degraded')).toBeInTheDocument();
  });

  it('price 카드의 품목을 렌더하고 place 전용 UI는 없다', () => {
    const price = {
      kind: 'price',
      feature_id: 'price:1',
      name: 'OO주유소',
      coord: null,
      category: null,
      address_line: null,
      marker_color: 'P-02',
      marker_icon: 'fuel',
      homepage_url: null,
      status: null,
      enrichment: [],
      degraded_providers: [],
      unit: '원/L',
      items: [{ name: '휘발유', price: '1650' }],
    } as Extract<FeatureDetailCard, { kind: 'price' }>;
    render(<FeatureDetailCardBody card={price} />);
    expect(screen.getByTestId('feature-detail-card-body-price')).toHaveTextContent('휘발유');
    // place 전용 enrichment 버튼은 없다.
    expect(screen.queryByTestId('feature-detail-card-body-load-enrichment')).not.toBeInTheDocument();
  });
});
