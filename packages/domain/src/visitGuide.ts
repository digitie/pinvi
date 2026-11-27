/**
 * 장소 이용 안내(Map visitor_info 투영 `VisitGuide`) 공용 표시 규칙 — 웹 `VisitGuide`·모바일 `VisitGuide`와
 * 그것을 항목으로 두는 웹 `PlaceInfoPanel`·모바일 `PlaceSheet`이 같은 줄·같은 배지를 쓴다.
 * 원천 문장은 해석하지 않고 그대로 보인다(요금만 원천이 숫자로 준 것을 원 단위로 적는다).
 */
import type {
  AccessibilityGroup,
  AccessibilityItem,
  FeeAudience,
  VisitFee,
  VisitGuide,
} from '@pinvi/schemas';

export const FEE_AUDIENCE_LABEL: Record<FeeAudience, string> = {
  adult: '성인',
  youth: '청소년',
  child: '어린이',
};

export const ACCESSIBILITY_GROUP_LABEL: Record<AccessibilityGroup, string> = {
  physical: '지체장애',
  visual: '시각장애',
  hearing: '청각장애',
  infant_family: '영유아 가족',
};

const ACCESSIBILITY_ORDER: AccessibilityGroup[] = [
  'physical',
  'visual',
  'hearing',
  'infant_family',
];
const FEE_ORDER: FeeAudience[] = ['adult', 'youth', 'child'];

/** 1234567 → "1,234,567" (런타임 Intl 차이에 기대지 않는다). */
function groupThousands(amount: number): string {
  return String(Math.trunc(amount)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/** 구조화 요금 → "성인 2,000원 · 청소년 1,000원 · 어린이 무료". 비어 있으면 null. */
export function formatFees(fees: readonly VisitFee[]): string | null {
  const sorted = FEE_ORDER.flatMap((audience) => fees.filter((fee) => fee.audience === audience));
  if (sorted.length === 0) return null;
  return sorted
    .map(
      (fee) =>
        `${FEE_AUDIENCE_LABEL[fee.audience]} ${
          fee.amount_krw === 0 ? '무료' : `${groupThousands(fee.amount_krw)}원`
        }`,
    )
    .join(' · ');
}

export interface VisitGuideRow {
  key: string;
  label: string;
  /** 표시할 줄들 — 각 줄은 원천 문장 그대로(줄바꿈 포함 가능, 텍스트로만 그린다). */
  lines: string[];
}

/** 이용 안내 표 줄(값이 있는 것만, 고정 순서). 배지(무장애·반려동물 상세)는 따로 그린다. */
export function visitGuideRows(guide: VisitGuide): VisitGuideRow[] {
  const rows: VisitGuideRow[] = [];
  const push = (key: string, label: string, ...values: (string | null | undefined)[]) => {
    const lines = values.filter((value): value is string => Boolean(value));
    if (lines.length > 0) rows.push({ key, label, lines });
  };
  push('usage_hours', '이용시간', guide.usage_hours);
  push('rest_days', '휴무일', guide.rest_days);
  push('fees', '요금', formatFees(guide.fees), guide.fee_text);
  push('discount', '할인', guide.discount);
  push('parking', '주차', guide.parking);
  push('parking_fee', '주차 요금', guide.parking_fee);
  push('reservation', '예약', guide.reservation);
  push('inquiry', '문의', guide.inquiry);
  push('transport', '교통', guide.transport);
  push('facilities', '시설', guide.facilities);
  push('capacity', '수용 인원', guide.capacity);
  if (guide.accommodation_available !== null) {
    push('accommodation', '숙박', guide.accommodation_available ? '가능' : '불가');
  }
  push('pet_note', '반려동물', guide.pet_note);
  return rows;
}

export interface AccessibilityGroupView {
  group: AccessibilityGroup;
  label: string;
  items: AccessibilityItem[];
}

/** 무장애 안내를 분류별로 묶는다(고정 순서, 빈 분류 없음). */
export function groupAccessibility(items: readonly AccessibilityItem[]): AccessibilityGroupView[] {
  return ACCESSIBILITY_ORDER.map((group) => ({
    group,
    label: ACCESSIBILITY_GROUP_LABEL[group],
    items: items.filter((item) => item.group === group),
  })).filter((view) => view.items.length > 0);
}

export interface PetPolicyLine {
  key: 'companion_type' | 'allowed_pets' | 'requirements' | 'notes';
  label: string;
  text: string;
}

/** 반려동물 동반 안내 줄(값이 있는 것만). */
export function petPolicyLines(guide: VisitGuide): PetPolicyLine[] {
  const policy = guide.pet_policy;
  if (!policy) return [];
  const all: PetPolicyLine[] = [
    { key: 'companion_type', label: '동반 구분', text: policy.companion_type ?? '' },
    { key: 'allowed_pets', label: '동반 가능 동물', text: policy.allowed_pets ?? '' },
    { key: 'requirements', label: '필요 사항', text: policy.requirements ?? '' },
    { key: 'notes', label: '기타', text: policy.notes ?? '' },
  ];
  return all.filter((line) => line.text);
}

/** 무장애 배지 — 원문을 해석하지 않고 항목이 하나라도 있으면 보인다. */
export function hasAccessibilityBadge(guide: VisitGuide): boolean {
  return guide.accessibility.length > 0;
}

/** 반려동물 배지 — 동반 안내(pet_policy)가 있으면 보인다(pet_note 한 줄은 배지가 아니라 표 줄이다). */
export function hasPetBadge(guide: VisitGuide): boolean {
  return petPolicyLines(guide).length > 0;
}

/** 보여 줄 이용 안내가 있는가 — 없으면 블록·항목을 만들지 않는다. */
export function visitGuideHasContent(guide: VisitGuide | null | undefined): guide is VisitGuide {
  if (!guide) return false;
  return visitGuideRows(guide).length > 0 || hasAccessibilityBadge(guide) || hasPetBadge(guide);
}
