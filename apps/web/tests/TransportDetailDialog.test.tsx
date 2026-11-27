import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
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
    brand_code: 'SKE',
    brand_name: 'SK에너지',
    phone: '02-000-0000',
    is_self: true,
    is_24h: false,
    has_carwash: true,
    has_cvs: null,
    lpg_available: false,
    source_last_seen_at: '2026-10-23T09:00:00+09:00',
    prices: [
      {
        product_key: 'gasoline',
        product_code: 'B027',
        product_name: '휘발유',
        price: 1689,
        collected_at: '2026-10-23T09:00:00+09:00',
        provider_updated_at: '2026-10-23T06:00:00+09:00',
      },
      {
        product_key: 'diesel',
        product_code: 'D047',
        product_name: null,
        price: null,
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
        product_key: 'premium_gasoline',
        product_code: 'B034',
        product_name: '고급휘발유',
        price: 1950,
        // 7일보다 오래 확인되지 않은 값 — "오래됨".
        collected_at: '2026-10-10T09:00:00+09:00',
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

afterEach(() => {
  vi.useRealTimers();
});

beforeEach(() => {
  // '오래됨'(7일) 판정은 응답을 받은 시각 기준 — fixture 시각 근처로 시계를 고정한다(Date만).
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-23T12:00:00+09:00'));
  detail.mockReset();
  fuelPriceHistory.mockReset();
});

describe('TransportDetailDialog', () => {
  it('주유소 현재가·신선도·오래된 정보를 보이고 취급하지 않는 유종은 그리지 않는다', async () => {
    detail.mockResolvedValue(FUEL);
    render(
      <TransportDetailDialog
        target={{ layer: 'fuel_station', featureId: 'f_fuel', title: '주유소' }}
        onClose={vi.fn()}
      />,
    );
    const prices = await screen.findByTestId('transport-fuel-prices');
    // transport 공개 유가 화면과 같은 이름·순서·단위. 경유(null)·LPG(0)는 행 자체가 없다.
    const rows = within(prices).getAllByTestId('transport-fuel-price');
    expect(rows.map((row) => row.getAttribute('data-product'))).toEqual(['B027', 'B034']);
    expect(rows[0]).toHaveTextContent('휘발유1,689원/L');
    expect(rows[1]).toHaveTextContent('고급유');
    expect(rows[1]).toHaveTextContent('오래됨');
    expect(within(rows[0]!).queryByTestId('transport-fuel-price-old')).toBeNull();
    expect(prices).not.toHaveTextContent('경유');
    expect(prices).not.toHaveTextContent('LPG');
    expect(prices).not.toHaveTextContent('판매 안 함');
    expect(prices.textContent).not.toMatch(/(^|\s)-(\s|$)/);
    // 상표 로고(오피넷 원본)와 이름, 편의시설(true만, transport 순서), 데이터 출처.
    expect(screen.getByTestId('fuel-brand')).toHaveTextContent('SK에너지');
    expect(screen.getByTestId('fuel-brand-icon')).toHaveAttribute('data-brand-code', 'SKE');
    expect(screen.getByTestId('fuel-brand-icon').querySelector('img')).toHaveAttribute(
      'src',
      '/fuel-brands/sk.gif',
    );
    expect(screen.getByTestId('fuel-facilities')).toHaveTextContent('편의시설 · 셀프 · 세차');
    const source = screen.getByTestId('fuel-data-source');
    expect(source).toHaveTextContent('전국 주유소·유가 정보');
    expect(source).toHaveTextContent('기준정보 반영');
    expect(source).toHaveTextContent('휘발유 제공기관 공시');
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

  it('일시 장애 이유면 잠시 후 다시 시도하라고 보인다', async () => {
    detail.mockResolvedValue(FUEL);
    fuelPriceHistory.mockResolvedValue({ ...UNAVAILABLE_HISTORY, reason: 'upstream_timeout' });
    render(
      <TransportDetailDialog
        target={{ layer: 'fuel_station', featureId: 'f_fuel', title: '주유소' }}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(await screen.findByTestId('transport-price-history-open'));
    const message = await screen.findByTestId('transport-price-history-unavailable');
    expect(message).toHaveTextContent('잠시 후 다시 시도해 주세요.');
    expect(message).toHaveAttribute('data-reason', 'upstream_timeout');
  });

  it('판매 중인 유종이 하나도 없으면 빈 행 대신 안내 한 줄', async () => {
    const item = FUEL.item as Extract<TransportDetailResponse['item'], { layer: 'fuel_station' }>;
    detail.mockResolvedValue({
      ...FUEL,
      item: { ...item, prices: item.prices.map((p) => ({ ...p, price: null })) },
    });
    render(
      <TransportDetailDialog
        target={{ layer: 'fuel_station', featureId: 'f_fuel', title: '주유소' }}
        onClose={vi.fn()}
      />,
    );
    const empty = await screen.findByTestId('transport-fuel-prices');
    expect(empty).toHaveTextContent('등록된 유효 유가가 없습니다.');
    expect(empty).toHaveAttribute('data-empty', 'true');
    expect(screen.queryByTestId('transport-fuel-price')).toBeNull();
  });

  it('가격 추이는 판매하지 않던 점을 빼고 transport 이름으로 보인다', async () => {
    detail.mockResolvedValue(FUEL);
    fuelPriceHistory.mockResolvedValue({
      ...UNAVAILABLE_HISTORY,
      status: 'available',
      reason: null,
      items: [
        {
          product_key: 'diesel',
          product_name: '자동차용경유',
          price: null,
          observed_at: '2026-10-22T00:00:00Z',
        },
        {
          product_key: 'gasoline',
          product_name: null,
          price: 1680,
          observed_at: '2026-10-22T00:00:00Z',
        },
        {
          product_key: 'gasoline',
          product_name: null,
          price: 0,
          observed_at: '2026-10-21T00:00:00Z',
        },
      ],
    });
    render(
      <TransportDetailDialog
        target={{ layer: 'fuel_station', featureId: 'f_fuel', title: '주유소' }}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(await screen.findByTestId('transport-price-history-open'));
    const history = await screen.findByTestId('transport-price-history');
    expect(history).toHaveTextContent('휘발유');
    expect(history).toHaveTextContent('1,680원/L');
    expect(history).not.toHaveTextContent('경유');
    expect(within(history).getAllByRole('listitem')).toHaveLength(1);
  });

  it('휴게소 주유소도 판매 중인 유종만, 정유사 로고와 함께', async () => {
    detail.mockResolvedValue({
      item: {
        layer: 'rest_area',
        feature_id: 'f_rest',
        category: '06040101',
        marker_icon: 'fast-food',
        marker_color: 'P-06',
        coord: null,
        name: '망향휴게소',
        address: { road: null, jibun: null },
        fuel_prices: {
          gasoline_price: 1650,
          diesel_price: null,
          lpg_price: null,
          oil_company: 'GS칼텍스',
          observed_at: '2026-10-23T08:00:00+09:00',
        },
      },
      freshness: FRESHNESS,
    } satisfies TransportDetailResponse);
    render(
      <TransportDetailDialog
        target={{ layer: 'rest_area', featureId: 'f_rest', title: '망향휴게소' }}
        onClose={vi.fn()}
      />,
    );
    const prices = await screen.findByTestId('transport-fuel-prices');
    expect(within(prices).getAllByTestId('transport-fuel-price')).toHaveLength(1);
    expect(prices).toHaveTextContent('휘발유1,650원/L');
    expect(prices).not.toHaveTextContent('경유');
    expect(screen.getByTestId('fuel-brand-icon')).toHaveAttribute('data-brand-code', 'GSC');
  });

  it('교통 돌발은 transport처럼 노선 배지·유형·처리 상태·내용 순서로 보인다', async () => {
    detail.mockResolvedValue({
      item: {
        layer: 'highway_incident',
        feature_id: 'f_inc',
        category: '99000000',
        marker_icon: 'roadblock',
        marker_color: 'P-13',
        coord: { lon: 127.1, lat: 37.2 },
        title: '경부선 사고',
        message: '2차로 사고 처리 중',
        incident_type: '사고',
        process_status: '처리중',
        route_no: '0010',
        route_name: '경부선',
        direction: '서울',
        point_name: '기흥IC',
        congestion_length: 1.5,
        occurred_at: '2026-10-23T08:40:00+09:00',
      },
      freshness: FRESHNESS,
    } satisfies TransportDetailResponse);
    render(
      <TransportDetailDialog
        target={{ layer: 'highway_incident', featureId: 'f_inc', title: '경부선 사고' }}
        onClose={vi.fn()}
      />,
    );
    expect(await screen.findByTestId('transport-incident-route')).toHaveTextContent(
      '0010 · 경부선',
    );
    expect(screen.getByTestId('transport-incident-status')).toHaveTextContent('사고 · 처리중');
    expect(screen.getByTestId('transport-incident-message')).toHaveTextContent(
      '2차로 사고 처리 중',
    );
    expect(screen.getByText('서울 방향')).toBeInTheDocument();
    expect(screen.getByText('1.5 km')).toBeInTheDocument();
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
