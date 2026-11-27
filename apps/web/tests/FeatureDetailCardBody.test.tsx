import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ContainingArea, FeatureDetailCard, ExternalEnrichment } from '@pinvi/schemas';
import { FeatureDetailCardBody } from '@/components/map/FeatureDetailCardBody';

function placeCard(over: Partial<Extract<FeatureDetailCard, { kind: 'place' }>> = {}) {
  return {
    kind: 'place',
    feature_id: 'place:1',
    name: '스타벅스 광안리',
    coord: { lon: 129.12, lat: 35.15 },
    category: '02020100',
    category_label: '카페',
    address_line: '부산 광안로 1',
    marker_color: 'P-07',
    marker_icon: 'cafe',
    homepage_url: 'https://sb.example',
    enrichment: [],
    degraded_providers: [],
    containing_areas: [],
    phone: '051-000-0000',
    business_hours: '09:00-22:00',
    ...over,
  } as Extract<FeatureDetailCard, { kind: 'place' }>;
}

describe('FeatureDetailCardBody containing areas', () => {
  const area = (
    over: Partial<ContainingArea> & Pick<ContainingArea, 'name' | 'area_kind'>,
  ): ContainingArea => ({
    feature_id: over.name,
    category_label: null,
    ...over,
  });

  it('국립공원·보호지역을 작은 면 순서대로 정보 칩으로 보여 준다', () => {
    render(
      <FeatureDetailCardBody
        card={placeCard({
          containing_areas: [
            area({ name: '우이령', area_kind: 'protected_area', category_label: '명승' }),
            area({ name: '북한산 국립공원', area_kind: 'national_park' }),
            area({ name: '남한산성', area_kind: 'protected_area', category_label: null }),
          ],
        })}
      />,
    );
    const chips = screen.getAllByTestId('feature-detail-card-body-containing-area');
    expect(chips.map((chip) => chip.textContent)).toEqual([
      '우이령 · 명승 안',
      '북한산 국립공원 안',
      // 지정 종류를 모르면 이름만 — 일괄 "보호지역"을 지어 붙이지 않는다.
      '남한산성 안',
    ]);
    const list = screen.getByRole('list', { name: '이 장소가 속한 구역' });
    expect(list.querySelectorAll('li')).toHaveLength(3);
  });

  it('국립공원 이름에 종류어가 없으면 덧붙이고, 모르는 종류는 이름만 쓴다', () => {
    render(
      <FeatureDetailCardBody
        card={placeCard({
          containing_areas: [
            area({ name: '지리산', area_kind: 'national_park' }),
            area({ name: '광안리 관광특구', area_kind: 'tourism_district' }),
          ],
        })}
      />,
    );
    const chips = screen.getAllByTestId('feature-detail-card-body-containing-area');
    expect(chips.map((chip) => chip.textContent)).toEqual([
      '지리산 국립공원 안',
      '광안리 관광특구 안',
    ]);
  });

  it('위험지역만 경고 스타일이고, live region 없이 sr-only로 경고를 전한다', () => {
    render(
      <FeatureDetailCardBody
        card={placeCard({
          containing_areas: [
            area({ name: '낙석', area_kind: 'hazard_zone' }),
            area({ name: '설악산 국립공원', area_kind: 'national_park' }),
          ],
        })}
      />,
    );
    const chips = screen.getAllByTestId('feature-detail-card-body-containing-area');
    const hazard = chips[0]!;
    const park = chips[1]!;
    expect(hazard).toHaveAttribute('data-area-kind', 'hazard_zone');
    expect(hazard).toHaveTextContent('경고: 낙석 위험지역 안');
    expect(hazard.className).toContain('text-error-text');
    expect(park.className).not.toContain('text-error-text');
    // 정적 속성이다 — 카드를 다시 그릴 때마다 화면낭독기가 끼어들면 안 된다.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('구역이 없으면 아무것도 그리지 않는다', () => {
    render(<FeatureDetailCardBody card={placeCard({ containing_areas: [] })} />);
    expect(screen.queryByTestId('feature-detail-card-body-containing-areas')).toBeNull();
  });
});

describe('FeatureDetailCardBody', () => {
  it('초기 카드에서도 부분 정보 안내를 표시한다', () => {
    render(<FeatureDetailCardBody card={placeCard({ degraded_providers: ['category_labels'] })} />);
    expect(screen.getByText('일부 상세 정보를 불러오지 못했습니다.')).toBeInTheDocument();
  });

  it('행사 카드도 보강 요청 없이 부분 정보 안내를 표시한다', () => {
    const card = {
      ...placeCard({ degraded_providers: ['category_labels'] }),
      kind: 'event',
      start_date: null,
      end_date: null,
      venue: null,
    } as FeatureDetailCard;
    render(<FeatureDetailCardBody card={card} />);
    expect(screen.getByText('일부 상세 정보를 불러오지 못했습니다.')).toBeInTheDocument();
  });

  it('place 카드의 일반 필드를 렌더한다', () => {
    render(<FeatureDetailCardBody card={placeCard()} />);
    expect(screen.getByTestId('feature-detail-card-body-address')).toHaveTextContent(
      '부산 광안로 1',
    );
    expect(screen.getByTestId('feature-detail-card-body-phone')).toHaveTextContent('051-000-0000');
    expect(screen.getByTestId('feature-detail-card-body-hours')).toHaveTextContent('09:00-22:00');
    expect(screen.getByTestId('feature-detail-card-body-category')).toHaveTextContent('카페');
    // 코드(`category`)는 화면에 보이지 않는다(2026-11-02 prod e2e — 상세 부제가 `01070300`이었다).
    expect(screen.queryByText('02020100')).not.toBeInTheDocument();
  });

  it('category_label이 없으면 카테고리 줄을 숨긴다(코드를 대신 보이지 않는다)', () => {
    render(
      <FeatureDetailCardBody card={placeCard({ category: '01070300', category_label: null })} />,
    );
    expect(screen.queryByTestId('feature-detail-card-body-category')).not.toBeInTheDocument();
    expect(screen.queryByText('01070300')).not.toBeInTheDocument();
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
    render(<FeatureDetailCardBody card={placeCard({ enrichment })} enrichmentRequested />);
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
      {
        provider: 'naver',
        matched: false,
        name: null,
        address: null,
        phone: null,
        provider_url: null,
        external_id: null,
      },
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
      category_label: null,
      address_line: null,
      marker_color: 'P-02',
      marker_icon: 'fuel',
      homepage_url: null,
      enrichment: [],
      degraded_providers: [],
      containing_areas: [],
      unit: '원/L',
      items: [{ name: '휘발유', price: '1650' }],
    } as Extract<FeatureDetailCard, { kind: 'price' }>;
    render(<FeatureDetailCardBody card={price} />);
    expect(screen.getByTestId('feature-detail-card-body-price')).toHaveTextContent('휘발유');
    // place 전용 enrichment 버튼은 없다.
    expect(
      screen.queryByTestId('feature-detail-card-body-load-enrichment'),
    ).not.toBeInTheDocument();
  });

  it('renders multi-line structured opening hours one line per weekday', () => {
    render(
      <FeatureDetailCardBody
        card={placeCard({ business_hours: '월요일: 09:00~18:00\n일요일: 휴무' })}
      />,
    );
    const hours = screen.getByTestId('feature-detail-card-body-hours');
    expect(hours).toHaveTextContent('월요일: 09:00~18:00');
    expect(hours).toHaveTextContent('일요일: 휴무');
    expect(hours.querySelector('.whitespace-pre-line')?.textContent).toBe(
      '월요일: 09:00~18:00\n일요일: 휴무',
    );
  });
});
