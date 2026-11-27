'use client';

import type { RestAreaFood, RestAreaMenuItem } from '@pinvi/schemas';

/** 화면에 먼저 보이는 대표·추천 메뉴 수. 나머지는 접어 둔다. */
const FEATURED_VISIBLE = 6;
const SEASONAL_VISIBLE = 4;

const TAG_LABEL: Record<RestAreaMenuItem['tags'][number], string> = {
  best: '대표',
  premium: '프리미엄',
  recommended: '추천',
};
const SEASON_LABEL: Record<'summer' | 'winter', string> = { summer: '여름', winter: '겨울' };

const won = new Intl.NumberFormat('ko-KR');

function priceText(price: number | null | undefined): string {
  return price == null ? '가격 정보 없음' : `${won.format(price)}원`;
}

/** 수집 시각의 한국 날짜(YYYY-MM-DD) — 화면의 "기준일". */
function kstDate(iso: string): string | null {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString('sv-SE', { timeZone: 'Asia/Seoul' });
}

function priceRange(food: RestAreaFood): string | null {
  const { price_min: min, price_median: median, price_max: max } = food;
  if (min == null || max == null) return null;
  const range = min === max ? `${won.format(min)}원` : `${won.format(min)}~${won.format(max)}원`;
  return median == null ? range : `${range} · 중앙 ${won.format(median)}원`;
}

function MenuList({
  items,
  testId,
  label,
  visible,
}: {
  items: RestAreaMenuItem[];
  testId: string;
  label: (item: RestAreaMenuItem) => string | null;
  visible: number;
}) {
  const shown = items.slice(0, visible);
  const rest = items.slice(visible);
  const row = (item: RestAreaMenuItem, index: number) => {
    const badge = label(item);
    return (
      <li
        key={`${item.name}-${index}`}
        className="flex items-baseline justify-between gap-2 py-0.5"
      >
        <span className="min-w-0 text-body">
          {item.name}
          {badge && <span className="ml-1 text-xs text-muted">{badge}</span>}
        </span>
        <span className="shrink-0 font-semibold text-ink">{priceText(item.price)}</span>
      </li>
    );
  };
  return (
    <div data-testid={testId}>
      <ul className="text-sm">{shown.map(row)}</ul>
      {rest.length > 0 && (
        <details className="text-sm">
          <summary className="focus-ring min-h-11 cursor-pointer py-2 text-muted">
            {rest.length}개 더 보기
          </summary>
          <ul>{rest.map((item, index) => row(item, index + visible))}</ul>
        </details>
      )}
    </div>
  );
}

export interface RestAreaFoodSectionProps {
  food: RestAreaFood | null | undefined;
}

/**
 * 휴게소 먹거리(한국도로공사 0502 — Map ADR-127). 휴게소 상세와, 같은 방향 휴게소와 짝지은 고속도로 주유소
 * 상세에 쓴다. 데이터만 보여 준다(요약 문장을 만들지 않는다). 값이 없으면 아무것도 그리지 않는다.
 */
export function RestAreaFoodSection({ food }: RestAreaFoodSectionProps) {
  if (!food || food.menu_count === 0) return null;
  const range = priceRange(food);
  const baseDate = kstDate(food.source_collected_at);
  const paired = food.paired_distance_m != null;
  return (
    <section
      className="space-y-2 rounded-sm border border-hairline p-2"
      aria-label="휴게소 먹거리"
      data-testid="rest-area-food"
    >
      <div>
        <h3 className="text-sm font-semibold text-ink">
          {paired ? `${food.rest_area_name} 먹거리` : '먹거리'}
        </h3>
        {paired && (
          <p className="text-xs text-muted" data-testid="rest-area-food-paired">
            이 주유소가 있는 휴게소 · {Math.round(food.paired_distance_m ?? 0)}m
          </p>
        )}
      </div>
      {food.featured.length > 0 && (
        <MenuList
          items={food.featured}
          testId="rest-area-food-featured"
          visible={FEATURED_VISIBLE}
          label={(item) => item.tags.map((tag) => TAG_LABEL[tag]).join('·') || null}
        />
      )}
      {range && (
        <p className="text-sm text-body" data-testid="rest-area-food-price-range">
          <span className="text-muted">가격대 </span>
          {range}
          <span className="text-muted"> (메뉴 {food.menu_count}개)</span>
        </p>
      )}
      {food.seasonal.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-muted">계절 메뉴</p>
          <MenuList
            items={food.seasonal}
            testId="rest-area-food-seasonal"
            visible={SEASONAL_VISIBLE}
            label={(item) =>
              item.season === 'summer' || item.season === 'winter'
                ? SEASON_LABEL[item.season]
                : null
            }
          />
        </div>
      )}
      <p className="text-xs text-muted" data-testid="rest-area-food-source">
        출처: {food.attribution}
        {baseDate ? ` · 기준일 ${baseDate}` : ''}
      </p>
    </section>
  );
}
