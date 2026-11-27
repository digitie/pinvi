import { describe, expect, it } from 'vitest';
import type { VisitGuide } from '@pinvi/schemas';
import {
  formatFees,
  groupAccessibility,
  hasAccessibilityBadge,
  hasPetBadge,
  petPolicyLines,
  visitGuideHasContent,
  visitGuideRows,
} from './visitGuide';

function guide(over: Partial<VisitGuide> = {}): VisitGuide {
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

describe('visitGuide', () => {
  it('구조화 요금을 성인·청소년·어린이 순으로, 0원은 무료로 적는다', () => {
    expect(
      formatFees([
        { audience: 'child', amount_krw: 0 },
        { audience: 'adult', amount_krw: 2000 },
        { audience: 'youth', amount_krw: 1000 },
      ]),
    ).toBe('성인 2,000원 · 청소년 1,000원 · 어린이 무료');
    expect(formatFees([{ audience: 'adult', amount_krw: 1234567 }])).toBe('성인 1,234,567원');
    expect(formatFees([])).toBeNull();
  });

  it('값이 있는 줄만 고정 순서로 만들고 요금은 구조화 값과 원문을 함께 둔다', () => {
    const rows = visitGuideRows(
      guide({
        parking: '가능',
        usage_hours: '09:00~18:00\n(입장마감 17:00)',
        fees: [{ audience: 'adult', amount_krw: 3000 }],
        fee_text: '단체 할인 있음',
        accommodation_available: false,
        pet_note: '불가',
      }),
    );
    expect(rows.map((row) => row.key)).toEqual([
      'usage_hours',
      'fees',
      'parking',
      'accommodation',
      'pet_note',
    ]);
    expect(rows[0]!.lines).toEqual(['09:00~18:00\n(입장마감 17:00)']);
    expect(rows[1]!.lines).toEqual(['성인 3,000원', '단체 할인 있음']);
    expect(rows[3]!.lines).toEqual(['불가']);
  });

  it('무장애 안내를 분류별로 묶고 배지는 항목이 있을 때만이다', () => {
    const g = guide({
      accessibility: [
        { group: 'visual', facility: 'braile_block', label: '점자블록', text: '입구' },
        { group: 'physical', facility: 'parking', label: '주차', text: '2면' },
        { group: 'physical', facility: 'route', label: '접근로', text: '경사로' },
      ],
    });
    expect(groupAccessibility(g.accessibility).map((v) => [v.label, v.items.length])).toEqual([
      ['지체장애', 2],
      ['시각장애', 1],
    ]);
    expect(hasAccessibilityBadge(g)).toBe(true);
    expect(hasAccessibilityBadge(guide())).toBe(false);
  });

  it('반려동물 배지는 동반 안내가 있을 때만, pet_note 한 줄은 배지가 아니다', () => {
    expect(hasPetBadge(guide({ pet_note: '가능' }))).toBe(false);
    const g = guide({
      pet_policy: {
        companion_type: '일부구역',
        allowed_pets: null,
        requirements: '목줄',
        notes: null,
      },
    });
    expect(hasPetBadge(g)).toBe(true);
    expect(petPolicyLines(g).map((line) => line.label)).toEqual(['동반 구분', '필요 사항']);
  });

  it('출처뿐이면 내용이 없다', () => {
    expect(visitGuideHasContent(null)).toBe(false);
    expect(visitGuideHasContent(guide())).toBe(false);
    expect(visitGuideHasContent(guide({ inquiry: '043-000-0000' }))).toBe(true);
  });
});
