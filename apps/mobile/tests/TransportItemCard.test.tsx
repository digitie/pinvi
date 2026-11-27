import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { TransportItem } from '@pinvi/schemas';

vi.mock('../lib/api', () => ({ apiClient: { request: async () => ({}) } }));

const { TransportItemCard } = await import('../components/TransportLayers');

const FUEL: TransportItem = {
  layer: 'fuel_station',
  feature_id: 'f_fuel',
  category: '06020000',
  marker_icon: 'fuel',
  marker_color: 'P-08',
  coord: { lon: 127, lat: 37.5 },
  name: 'PinVi 셀프주유소',
  address: { road: '서울 강남구 테헤란로 1', jibun: null },
  brand_code: 'GSC',
  brand_name: 'GS칼텍스',
  is_self: true,
  has_carwash: false,
  has_cvs: true,
  prices: [
    {
      product_key: 'diesel',
      product_code: 'D047',
      product_name: null,
      price: null,
      collected_at: '2026-10-23T09:00:00+09:00',
    },
    {
      product_key: 'gasoline',
      product_code: 'B027',
      product_name: '휘발유',
      price: 1689,
      collected_at: '2026-10-23T09:00:00+09:00',
    },
    {
      product_key: 'lpg',
      product_code: 'K015',
      product_name: 'LPG',
      price: 0,
      collected_at: '2026-10-23T09:00:00+09:00',
    },
    {
      product_key: 'kerosene',
      product_code: 'C004',
      product_name: null,
      price: 1300,
      collected_at: '2026-10-01T09:00:00+09:00',
    },
  ],
};

afterEach(() => {
  vi.useRealTimers();
});

describe('TransportItemCard — 주유소', () => {
  it('웹 상세와 같은 규칙: 판매 중인 유종만, 원/L, 오래됨, 상표, 편의시설', () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-10-23T12:00:00+09:00'));
    render(
      <TransportItemCard item={FUEL} state={{ results: [], receivedAt: null }} onClose={vi.fn()} />,
    );
    expect(screen.getByText('GS칼텍스')).toBeTruthy();
    expect(screen.getByTestId('transport-fuel-price-B027').textContent).toContain('1,689원/L');
    // 등유는 7일보다 오래 확인되지 않았다.
    expect(screen.getByTestId('transport-fuel-price-C004').textContent).toContain('오래됨');
    expect(screen.getByTestId('transport-fuel-price-B027').textContent).not.toContain('오래됨');
    // 경유(null)·LPG(0)는 행이 없고 "판매 안 함"도 없다.
    expect(screen.queryByTestId('transport-fuel-price-D047')).toBeNull();
    expect(screen.queryByTestId('transport-fuel-price-K015')).toBeNull();
    expect(screen.queryByText(/판매 안 함/)).toBeNull();
    expect(screen.getByText('편의시설 · 셀프 · 편의점')).toBeTruthy();
  });

  it('판매 중인 유종이 없으면 안내 한 줄', () => {
    const item = {
      ...FUEL,
      prices: FUEL.layer === 'fuel_station' ? FUEL.prices.map((p) => ({ ...p, price: null })) : [],
    };
    render(
      <TransportItemCard item={item} state={{ results: [], receivedAt: null }} onClose={vi.fn()} />,
    );
    expect(screen.getByText('등록된 유효 유가가 없습니다.')).toBeTruthy();
  });
});
