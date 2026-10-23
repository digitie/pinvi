import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { FuelPriceHistoryResponse, TransportDetailResponse } from '@pinvi/schemas';

const detail = vi.fn();
const fuelPriceHistory = vi.fn();
vi.mock('@/lib/api', () => ({ apiClient: {} }));
vi.mock('@pinvi/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@pinvi/api-client')>();
  return { ...actual, transportApi: () => ({ detail, fuelPriceHistory }) };
});

import { ApiError } from '@pinvi/api-client';
import { TransportDetailDialog } from '@/components/map/TransportDetailDialog';

const FRESHNESS = {
  source_collected_at: '2026-10-23T09:00:00+09:00',
  loaded_at: '2026-10-23T09:05:00+09:00',
  age_seconds: 600,
  max_age_seconds: 172800,
  stale: true,
};

const FUEL: TransportDetailResponse = {
  item: {
    layer: 'fuel_station',
    feature_id: 'f_fuel',
    category: '06020000',
    marker_icon: 'fuel',
    marker_color: 'P-08',
    coord: { lon: 127.0, lat: 37.5 },
    name: 'PinVi 셀프주유소',
    address: { road: '서울 강남구 테헤란로 1', jibun: null },
    brand_name: 'SK에너지',
    phone: '02-000-0000',
    is_self: true,
    prices: [
      {
        product_key: 'gasoline',
        product_code: 'B027',
        product_name: '휘발유',
        price: 1689,
        collected_at: '2026-10-23T09:00:00+09:00',
      },
      {
        product_key: 'diesel',
        product_code: 'D047',
        product_name: null,
        price: null,
        collected_at: '2026-10-23T09:00:00+09:00',
      },
    ],
  },
  freshness: FRESHNESS,
};

const UNAVAILABLE_HISTORY: FuelPriceHistoryResponse = {
  feature_id: 'f_fuel',
  status: 'unavailable',
  reason: 'disabled',
  truncated: false,
  items: [],
  current_prices: [],
  freshness: FRESHNESS,
};

beforeEach(() => {
  detail.mockReset();
  fuelPriceHistory.mockReset();
});

describe('TransportDetailDialog', () => {
  it('주유소 현재가·판매 안 함·신선도·오래된 정보를 보인다', async () => {
    detail.mockResolvedValue(FUEL);
    render(
      <TransportDetailDialog
        target={{ layer: 'fuel_station', featureId: 'f_fuel', title: '주유소' }}
        onClose={vi.fn()}
      />,
    );
    const prices = await screen.findByTestId('transport-fuel-prices');
    expect(prices).toHaveTextContent('휘발유1,689원');
    expect(prices).toHaveTextContent('경유판매 안 함');
    expect(screen.getByTestId('transport-detail-freshness')).toHaveTextContent('10분 전 갱신');
    expect(screen.getByTestId('transport-detail-freshness')).toHaveTextContent('오래된 정보');
    expect(detail).toHaveBeenCalledWith('fuel_station', 'f_fuel', expect.anything());
  });

  it('가격 추이가 unavailable이면 아직 제공되지 않음을 보인다', async () => {
    detail.mockResolvedValue(FUEL);
    fuelPriceHistory.mockResolvedValue(UNAVAILABLE_HISTORY);
    render(
      <TransportDetailDialog
        target={{ layer: 'fuel_station', featureId: 'f_fuel', title: '주유소' }}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(await screen.findByTestId('transport-price-history-open'));
    const message = await screen.findByTestId('transport-price-history-unavailable');
    expect(message).toHaveTextContent('가격 추이는 아직 제공되지 않습니다.');
    expect(message).toHaveAttribute('data-reason', 'disabled');
  });

  it('Map 장애는 대화상자 안의 오류로만 보인다', async () => {
    detail.mockRejectedValue(
      new ApiError('TRANSPORT_UNAVAILABLE', '교통 정보를 일시적으로 불러올 수 없습니다.', 503),
    );
    render(
      <TransportDetailDialog
        target={{ layer: 'airport', featureId: 'f_air', title: '김포국제공항' }}
        onClose={vi.fn()}
      />,
    );
    expect(await screen.findByTestId('transport-detail-error')).toHaveTextContent(
      '교통 정보를 일시적으로 불러올 수 없습니다.',
    );
  });

  it('target이 없으면 그리지 않는다', () => {
    const { container } = render(<TransportDetailDialog target={null} onClose={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
    expect(detail).not.toHaveBeenCalled();
  });
});
