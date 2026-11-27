import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import type { RestAreaFood } from '@pinvi/schemas';

import { RestAreaFoodSection } from '@/components/map/RestAreaFoodSection';

const FOOD: RestAreaFood = {
  rest_area_name: '행담도휴게소',
  std_rest_code: '000341',
  route_name: '서해안선',
  menu_count: 62,
  price_min: 3000,
  price_median: 9000,
  price_max: 16000,
  featured: [
    { name: '어묵우동', price: 7500, tags: ['best'], season: 'all_year' },
    { name: '한우국밥', price: 13000, tags: ['premium', 'recommended'], season: null },
    { name: '돈까스', price: 9500, tags: ['recommended'], season: 'all_year' },
    { name: '라면', price: 5000, tags: ['recommended'], season: 'all_year' },
    { name: '비빔밥', price: 9000, tags: ['recommended'], season: 'all_year' },
    { name: '김밥', price: 4000, tags: ['recommended'], season: 'all_year' },
    { name: '호두과자', price: null, tags: ['best'], season: 'all_year' },
  ],
  seasonal: [{ name: '냉모밀', price: 8000, tags: [], season: 'summer' }],
  menu_updated_on: '2026-01-09',
  // KST 2026-11-28 03:50 — 기준일은 한국 날짜다.
  source_collected_at: '2026-11-27T18:50:00Z',
  attribution: '한국도로공사',
  paired_distance_m: null,
};

describe('RestAreaFoodSection', () => {
  it('shows featured menus, price range, seasonal menus and the source with the KST base date', () => {
    render(<RestAreaFoodSection food={FOOD} />);
    const section = screen.getByTestId('rest-area-food');
    expect(within(section).getByRole('heading', { name: '먹거리' })).toBeTruthy();
    const featured = screen.getByTestId('rest-area-food-featured');
    expect(featured.textContent).toContain('어묵우동');
    expect(featured.textContent).toContain('대표');
    expect(featured.textContent).toContain('7,500원');
    expect(featured.textContent).toContain('프리미엄·추천');
    // 6개만 펼치고 나머지는 접는다.
    expect(within(featured).getByText('1개 더 보기')).toBeTruthy();
    expect(featured.textContent).toContain('가격 정보 없음');
    expect(screen.getByTestId('rest-area-food-price-range').textContent).toBe(
      '가격대 3,000~16,000원 · 중앙 9,000원 (메뉴 62개)',
    );
    const seasonal = screen.getByTestId('rest-area-food-seasonal');
    expect(seasonal.textContent).toContain('냉모밀');
    expect(seasonal.textContent).toContain('여름');
    expect(screen.getByTestId('rest-area-food-source').textContent).toBe(
      '출처: 한국도로공사 · 기준일 2026-11-28',
    );
    expect(screen.queryByTestId('rest-area-food-paired')).toBeNull();
  });

  it('names the paired rest area on a highway fuel station', () => {
    render(<RestAreaFoodSection food={{ ...FOOD, paired_distance_m: 54.6 }} />);
    expect(screen.getByRole('heading', { name: '행담도휴게소 먹거리' })).toBeTruthy();
    expect(screen.getByTestId('rest-area-food-paired').textContent).toBe(
      '이 주유소가 있는 휴게소 · 55m',
    );
  });

  it('renders nothing without menus', () => {
    const { container } = render(<RestAreaFoodSection food={null} />);
    expect(container.innerHTML).toBe('');
    const empty = render(<RestAreaFoodSection food={{ ...FOOD, menu_count: 0 }} />);
    expect(empty.container.innerHTML).toBe('');
  });

  it('omits the price range when prices are missing', () => {
    render(
      <RestAreaFoodSection
        food={{ ...FOOD, price_min: null, price_median: null, price_max: null, seasonal: [] }}
      />,
    );
    expect(screen.queryByTestId('rest-area-food-price-range')).toBeNull();
    expect(screen.queryByTestId('rest-area-food-seasonal')).toBeNull();
  });
});
