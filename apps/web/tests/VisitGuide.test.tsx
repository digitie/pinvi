import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { FeatureDetailCard, VisitGuide as Guide } from '@pinvi/schemas';
import { FeatureDetailCardBody } from '@/components/map/FeatureDetailCardBody';
import { VisitGuide } from '@/components/map/VisitGuide';

const T = 'guide';

function guide(over: Partial<Guide> = {}): Guide {
  return {
    provider: 'tourapi',
    attribution: '한국관광공사',
    reference_date: null,
    usage_hours: null,
    rest_days: null,
    parking: null,
    parking_fee: null,
    fees: [],
    fee_text: null,
    discount: null,
    reservation: null,
    inquiry: null,
    transport: null,
    facilities: null,
    capacity: null,
    accommodation_available: null,
    pet_note: null,
    accessibility: [],
    pet_policy: null,
    ...over,
  };
}

describe('VisitGuide', () => {
  it('원천 문장을 줄바꿈 그대로 텍스트로 그리고 요금은 구조화 값을 적는다', () => {
    render(
      <VisitGuide
        guide={guide({
          usage_hours: '09:00~18:00\n(입장마감 17:00)',
          rest_days: '매주 월요일',
          fees: [
            { audience: 'adult', amount_krw: 2000 },
            { audience: 'youth', amount_krw: 1000 },
            { audience: 'child', amount_krw: 0 },
          ],
          fee_text: '<b>단체</b> 할인',
          parking: '가능',
        })}
        testId={T}
      />,
    );
    const hours = screen.getByTestId(`${T}-usage_hours`);
    expect(hours).toHaveTextContent('이용시간');
    const hoursText = within(hours).getByText(/09:00~18:00/);
    expect(hoursText.textContent).toBe('09:00~18:00\n(입장마감 17:00)');
    expect(hoursText.className).toContain('whitespace-pre-line');
    const fees = screen.getByTestId(`${T}-fees`);
    // 요금 원문이 함께 있으면 0원이 조건부일 수 있어 "무료"로 해석하지 않는다.
    expect(fees).toHaveTextContent('성인 2,000원 · 청소년 1,000원 · 어린이 0원');
    // HTML 꼴 문자열은 해석하지 않는다.
    expect(within(fees).getByText('<b>단체</b> 할인')).toBeInTheDocument();
    expect(fees.querySelector('b')).toBeNull();
    expect(screen.getByTestId(`${T}-attribution`)).toHaveTextContent('출처: 한국관광공사');
  });

  it('요금 원문이 없으면 0원을 무료로 적는다', () => {
    render(
      <VisitGuide
        guide={guide({
          fees: [
            { audience: 'adult', amount_krw: 2000 },
            { audience: 'youth', amount_krw: 1000 },
            { audience: 'child', amount_krw: 0 },
          ],
        })}
        testId={T}
      />,
    );
    expect(screen.getByTestId(`${T}-fees`)).toHaveTextContent(
      '성인 2,000원 · 청소년 1,000원 · 어린이 무료',
    );
  });

  it('펼치기 전에는 aria-controls가 없는 패널을 가리키지 않는다', () => {
    render(
      <VisitGuide
        guide={guide({
          accessibility: [{ group: 'hearing', facility: 'guide', label: '안내', text: '수어' }],
        })}
        testId={T}
      />,
    );
    const toggle = screen.getByTestId(`${T}-accessibility-toggle`);
    expect(toggle).not.toHaveAttribute('aria-controls');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-controls', screen.getByTestId(`${T}-accessibility`).id);
  });

  it('omit으로 준 이용시간·휴무는 그리지 않는다', () => {
    render(
      <VisitGuide
        guide={guide({ usage_hours: '09:00~18:00', rest_days: '월요일', parking: '가능' })}
        testId={T}
        omit={['usage_hours', 'rest_days']}
      />,
    );
    expect(screen.queryByTestId(`${T}-usage_hours`)).toBeNull();
    expect(screen.queryByTestId(`${T}-rest_days`)).toBeNull();
    expect(screen.getByTestId(`${T}-parking`)).toHaveTextContent('가능');
  });

  it('무장애 배지는 글자·아이콘이 있는 펼침 버튼이고 분류별로 보인다', () => {
    render(
      <VisitGuide
        guide={guide({
          accessibility: [
            { group: 'physical', facility: 'parking', label: '주차', text: '장애인 주차 2면' },
            { group: 'visual', facility: 'braile_block', label: '점자블록', text: '입구' },
          ],
        })}
        testId={T}
      />,
    );
    const toggle = screen.getByTestId(`${T}-accessibility-toggle`);
    expect(toggle).toHaveTextContent('무장애 안내');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId(`${T}-accessibility`)).toBeNull();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const region = screen.getByTestId(`${T}-accessibility`);
    expect(toggle).toHaveAttribute('aria-controls', region.id);
    expect(within(region).getByRole('region', { name: '지체장애' })).toHaveTextContent(
      '주차: 장애인 주차 2면',
    );
    expect(within(region).getByRole('region', { name: '시각장애' })).toHaveTextContent(
      '점자블록: 입구',
    );
    expect(screen.queryByTestId(`${T}-pet-toggle`)).toBeNull();
  });

  it('반려동물 배지는 동반 안내가 있을 때만이고 pet_note는 표 줄로 그린다', () => {
    render(
      <VisitGuide
        guide={guide({
          pet_note: '소형견 가능',
          pet_policy: {
            companion_type: '일부구역 동반가능',
            allowed_pets: null,
            requirements: '목줄 착용',
            notes: null,
          },
        })}
        testId={T}
      />,
    );
    expect(screen.getByTestId(`${T}-pet_note`)).toHaveTextContent('소형견 가능');
    fireEvent.click(screen.getByTestId(`${T}-pet-toggle`));
    const pet = screen.getByTestId(`${T}-pet`);
    expect(pet).toHaveTextContent('동반 구분');
    expect(pet).toHaveTextContent('일부구역 동반가능');
    expect(pet).toHaveTextContent('목줄 착용');
    expect(pet).not.toHaveTextContent('동반 가능 동물');
  });

  it('기준일이 있으면 출처 줄에 적고, 보여 줄 것이 없으면 아무것도 그리지 않는다', () => {
    const { container, rerender } = render(
      <VisitGuide
        guide={guide({
          provider: 'krforest_recreation_forest',
          attribution: '공공데이터포털 전국휴양림표준데이터',
          reference_date: '2026-03-01',
          accommodation_available: true,
        })}
        testId={T}
      />,
    );
    expect(screen.getByTestId(`${T}-accommodation`)).toHaveTextContent('가능');
    expect(screen.getByTestId(`${T}-attribution`)).toHaveTextContent('기준일 2026-03-01');
    rerender(<VisitGuide guide={guide()} testId={T} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('FeatureDetailCardBody — 이용 안내', () => {
  function placeCard(visitGuide: Guide | null): Extract<FeatureDetailCard, { kind: 'place' }> {
    return {
      kind: 'place',
      feature_id: 'f1',
      name: '국립현대미술관',
      coord: null,
      category: null,
      category_label: null,
      address_line: null,
      marker_color: 'P-02',
      marker_icon: 'attraction',
      homepage_url: null,
      enrichment: [],
      degraded_providers: [],
      containing_areas: [],
      phone: null,
      business_hours: null,
      introduction: null,
      visit_guide: visitGuide,
    };
  }

  it('이용 안내 블록을 제목과 함께 그린다', () => {
    render(<FeatureDetailCardBody card={placeCard(guide({ inquiry: '02-0000-0000' }))} />);
    const section = screen.getByRole('region', { name: '이용 안내' });
    expect(
      within(section).getByTestId('feature-detail-card-body-visit-guide-inquiry'),
    ).toHaveTextContent('02-0000-0000');
  });

  it('출처뿐인 안내는 블록을 만들지 않는다', () => {
    render(<FeatureDetailCardBody card={placeCard(guide())} />);
    expect(screen.queryByTestId('feature-detail-card-body-visit-guide-section')).toBeNull();
  });
});
