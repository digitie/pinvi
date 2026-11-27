import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { FeatureDetailCardSchema } from '@pinvi/schemas';
import { cardIntroduction, cardVisitGuide, visitGuideRows } from '@pinvi/domain';

/**
 * 서버 `build_detail_card` 출력(golden, `apps/api/tests/unit/test_visitor_info_projection.py`가 같은 파일을 서버
 * 투영과 대조한다)을 클라이언트 스키마로 읽는다 — 서버 응답과 클라이언트 스키마가 갈라지면 여기서 드러난다.
 */
interface RawCard {
  introduction: { images: unknown };
  visit_guide: unknown;
}

const golden: unknown[] = JSON.parse(
  readFileSync(join(__dirname, 'fixtures/detail-card-golden.json'), 'utf-8'),
);

describe('detail-card golden(서버 ↔ 클라이언트 스키마 정합)', () => {
  it('서버가 만든 place·축제 카드를 블록 손실 없이 읽는다', () => {
    const [place, festival] = golden.map((raw) => FeatureDetailCardSchema.parse(raw));
    expect(place?.kind).toBe('place');
    expect(festival?.kind).toBe('event');
    // 블록 하나가 모양이 어긋나면 `.catch(null)`로 조용히 사라지므로, 사라지지 않았는지 따로 확인한다.
    expect(cardIntroduction(place)?.images).toHaveLength(2);
    expect(cardIntroduction(place)?.kogl_type).toBe(3);
    expect(cardVisitGuide(place)?.accessibility.length).toBeGreaterThan(0);
    expect(cardVisitGuide(place)?.pet_policy?.allowed_pets).toBe('소형견');
    expect(visitGuideRows(cardVisitGuide(place)!).map((row) => row.key)).toContain('fees');
    expect(cardIntroduction(festival)?.overview).toBe('벚꽃이 피는 봄 축제');
  });

  it('모르는 원천·공공누리 유형·분류가 와도 카드 전체를 버리지 않는다', () => {
    const raw = structuredClone(golden[0]) as {
      introduction: { provider: string; images: { kogl_type: number }[] };
      visit_guide: { accessibility: unknown[]; fees: unknown[] };
    };
    raw.introduction.provider = 'new_source';
    raw.introduction.images[0]!.kogl_type = 9;
    raw.visit_guide.accessibility.push({
      group: 'elderly',
      facility: 'bench',
      label: '쉼터',
      text: '있음',
    });
    raw.visit_guide.fees.push({ audience: 'senior', amount_krw: 0 });
    const card = FeatureDetailCardSchema.parse(raw);
    expect(card.kind).toBe('place');
    // 모르는 원천은 화면에 보이지 않는다(출처 표시 조건을 모른다).
    expect(cardIntroduction(card)).toBeNull();
    const guide = cardVisitGuide(card)!;
    expect(guide.accessibility).toHaveLength(raw.visit_guide.accessibility.length);
    expect(visitGuideRows(guide).find((row) => row.key === 'fees')?.lines[0]).not.toContain(
      'senior',
    );
  });

  it('블록 모양이 깨지면 그 블록만 null이다', () => {
    const raw = structuredClone(golden[0]) as RawCard;
    raw.visit_guide = { provider: 'tourapi' };
    raw.introduction.images = 'broken';
    const card = FeatureDetailCardSchema.parse(raw);
    expect(card.kind === 'place' && card.visit_guide).toBeNull();
    expect(card.kind === 'place' && card.introduction).toBeNull();
    expect(card.name).toBe('산막이옛길');
  });
});
