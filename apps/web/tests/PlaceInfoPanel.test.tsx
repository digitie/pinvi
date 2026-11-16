import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { PoiPlaceDetails, TripViewPoi } from '@pinvi/schemas';

const api = vi.hoisted(() => ({
  placeDetails: vi.fn(),
  refreshPlaceDetails: vi.fn(),
  kakaoPhone: vi.fn(),
  weather: vi.fn(),
}));

vi.mock('@pinvi/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@pinvi/api-client')>();
  return { ...actual, poiApi: () => api };
});

import { ApiError } from '@pinvi/api-client';
import { PlaceInfoPanel } from '@/components/trips/PlaceInfoPanel';
import { __clearKakaoPhoneCacheForTest } from '@/lib/usePlaceDetails';
import { __resetPoiWeatherForTest } from '@/lib/usePoiWeather';

const NOW = Date.parse('2026-11-16T03:00:00Z'); // 월요일 12:00 KST
const POI_ID = '11111111-1111-4111-8111-111111111111';

const poi = {
  poi_id: POI_ID,
  feature_id: 'f_hahoe',
  sort_order: 'a0',
  title: '하회마을',
  feature: {},
  marker_color: null,
  marker_icon: null,
  display_marker_color: null,
  feature_resolution_state: 'found',
  user_note: '입장권 현장 구매',
  planned_arrival_at: null,
  planned_departure_at: null,
  budget_amount: null,
  actual_amount: null,
  currency: 'KRW',
  user_url: 'https://blog.example/hahoe',
  rise_set: null,
  feature_link_broken_at: null,
  version: 1,
  created_at: '2026-11-16T00:00:00Z',
  updated_at: '2026-11-16T00:00:00Z',
} as unknown as TripViewPoi;

function details(overrides: Partial<PoiPlaceDetails> = {}): PoiPlaceDetails {
  return {
    poi_id: POI_ID,
    status: 'ready',
    opening_hours: ['월요일: 09:00~18:00', '화요일: 휴무'],
    closed_days: '매주 화요일',
    phone: '054-853-0109',
    website: 'https://www.hahoe.or.kr',
    sources: { opening_hours: 'kor_travel_map', phone: 'kor_travel_map' },
    fetched_at: '2026-11-16T02:00:00Z',
    refresh_available_at: '2026-11-16T02:01:00Z',
    ...overrides,
  };
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(NOW);
  api.placeDetails.mockReset();
  api.refreshPlaceDetails.mockReset();
  api.kakaoPhone.mockReset();
  api.kakaoPhone.mockResolvedValue({ provider: 'kakao', matched: false });
  __clearKakaoPhoneCacheForTest();
  __resetPoiWeatherForTest(async () => ({
    feature_id: 'f_hahoe',
    is_stale: false,
    source_styles: ['nowcast', 'advisory'],
    metrics: [
      {
        forecast_style: 'nowcast',
        metric_key: 'T1H',
        value_number: 9,
        unit: 'deg_c',
        provider: 'python-kma-api',
        valid_at: '2026-11-16T03:00:00Z',
      },
      {
        forecast_style: 'advisory',
        metric_key: 'WRN',
        value_text: '건조주의보',
        provider: 'python-kma-api',
      },
    ],
  }));
});
afterEach(() => {
  __resetPoiWeatherForTest();
  vi.useRealTimers();
});

function renderPanel(onClose = vi.fn()) {
  render(
    <PlaceInfoPanel
      tripId="t1"
      poi={poi}
      coord={{ lon: 128.5181, lat: 36.5397 }}
      onClose={onClose}
    />,
  );
  return onClose;
}

describe('PlaceInfoPanel', () => {
  it('shows a brief summary and keeps every section collapsed by default', async () => {
    api.placeDetails.mockResolvedValue(details());
    const onClose = renderPanel();
    const panel = screen.getByTestId('place-info-panel');
    expect(within(panel).getByTestId('place-info-title')).toHaveTextContent('하회마을');
    expect(await within(panel).findByTestId('weather-badge')).toBeInTheDocument();
    expect(await within(panel).findByTestId('place-info-today-hours')).toHaveTextContent(
      '월요일: 09:00~18:00',
    );
    expect(within(panel).getByTestId('place-info-alert')).toHaveTextContent('건조주의보');
    for (const key of ['weather', 'hours', 'memo', 'links', 'maps']) {
      expect(within(panel).getByTestId(`place-info-${key}-toggle`)).toHaveAttribute(
        'aria-expanded',
        'false',
      );
      expect(within(panel).queryByTestId(`place-info-${key}`)).toBeNull();
    }
    expect(api.placeDetails).toHaveBeenCalledWith('t1', POI_ID, expect.anything());
    fireEvent.click(within(panel).getByTestId('place-info-close'));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('expands one section at a time: weather, hours, memo, links, map links', async () => {
    api.placeDetails.mockResolvedValue(details());
    renderPanel();
    fireEvent.click(screen.getByTestId('place-info-weather-toggle'));
    expect(await screen.findByTestId('weather-alerts')).toHaveTextContent('건조주의보');

    fireEvent.click(screen.getByTestId('place-info-hours-toggle'));
    expect(screen.queryByTestId('place-info-weather')).toBeNull();
    const hours = await screen.findByTestId('place-info-hours');
    expect(await within(hours).findByTestId('place-info-opening-hours')).toHaveTextContent(
      '화요일: 휴무',
    );
    expect(within(hours).getByTestId('place-info-closed-days')).toHaveTextContent('매주 화요일');
    expect(within(hours).getByTestId('place-info-phone')).toHaveAttribute('href', 'tel:0548530109');
    expect(within(hours).getByTestId('place-info-website')).toHaveAttribute(
      'href',
      'https://www.hahoe.or.kr',
    );
    expect(within(hours).getByTestId('place-info-hours-source')).toHaveTextContent(
      '출처: 공공데이터',
    );

    fireEvent.click(screen.getByTestId('place-info-memo-toggle'));
    expect(screen.queryByTestId('place-info-hours')).toBeNull();
    expect(screen.getByTestId('place-info-memo')).toHaveTextContent('입장권 현장 구매');

    fireEvent.click(screen.getByTestId('place-info-links-toggle'));
    expect(screen.getByTestId('place-info-user-url')).toHaveAttribute(
      'href',
      'https://blog.example/hahoe',
    );

    fireEvent.click(screen.getByTestId('place-info-maps-toggle'));
    expect(screen.getByTestId('place-info-map-naver').getAttribute('href')).toContain(
      'map.naver.com',
    );
    expect(screen.getByTestId('place-info-map-kakao').getAttribute('href')).toContain(
      'map.kakao.com/link/map/',
    );
    expect(screen.getByTestId('place-info-map-google').getAttribute('href')).toContain(
      'query=36.5397,128.5181',
    );
  });

  it('shows nothing alarming when details are unavailable', async () => {
    api.placeDetails.mockResolvedValue(
      details({
        status: 'unavailable',
        opening_hours: [],
        closed_days: null,
        phone: null,
        website: null,
        sources: {},
        fetched_at: null,
      }),
    );
    renderPanel();
    fireEvent.click(screen.getByTestId('place-info-hours-toggle'));
    expect(await screen.findByTestId('place-info-hours-empty')).toHaveTextContent(
      '확인된 영업 정보가 없습니다.',
    );
    expect(screen.queryByTestId('place-info-today-hours')).toBeNull();
  });

  it('refetches on demand and reports loading, success, rate limit and permission errors', async () => {
    api.placeDetails.mockResolvedValue(details({ phone: '054-000-0000' }));
    let resolveRefresh: (value: PoiPlaceDetails) => void = () => {};
    api.refreshPlaceDetails.mockImplementationOnce(
      () =>
        new Promise<PoiPlaceDetails>((resolve) => {
          resolveRefresh = resolve;
        }),
    );
    renderPanel();
    fireEvent.click(screen.getByTestId('place-info-hours-toggle'));
    expect(await screen.findByTestId('place-info-phone')).toHaveTextContent('054-000-0000');
    const button = screen.getByTestId('place-info-refetch');
    fireEvent.click(button);
    await waitFor(() => expect(button).toBeDisabled());
    resolveRefresh(details({ phone: '054-111-2222' }));
    expect(await screen.findByTestId('place-info-refetch-done')).toBeInTheDocument();
    expect(screen.getByTestId('place-info-phone')).toHaveTextContent('054-111-2222');
    expect(api.refreshPlaceDetails).toHaveBeenCalledWith('t1', POI_ID);

    api.refreshPlaceDetails.mockRejectedValueOnce(
      new ApiError('RATE_LIMITED', 'x', 429, undefined, 42),
    );
    fireEvent.click(button);
    expect(await screen.findByTestId('place-info-refetch-error')).toHaveTextContent(
      '42초 뒤에 다시 읽어올 수 있습니다.',
    );
    // 실패해도 기존 값은 그대로다.
    expect(screen.getByTestId('place-info-phone')).toHaveTextContent('054-111-2222');

    api.refreshPlaceDetails.mockRejectedValueOnce(new ApiError('FORBIDDEN', 'x', 403));
    fireEvent.click(button);
    await waitFor(() =>
      expect(screen.getByTestId('place-info-refetch-error')).toHaveTextContent(
        '편집할 수 있는 사람만',
      ),
    );
  });

  it('does not ask Kakao when a stored phone exists', async () => {
    api.placeDetails.mockResolvedValue(details());
    renderPanel();
    fireEvent.click(screen.getByTestId('place-info-hours-toggle'));
    expect(await screen.findByTestId('place-info-phone')).toHaveTextContent('054-853-0109');
    expect(api.kakaoPhone).not.toHaveBeenCalled();
    expect(screen.queryByTestId('place-info-kakao-phone')).toBeNull();
  });

  it('shows a live Kakao phone (attributed, not stored) only when the hours section is opened', async () => {
    api.placeDetails.mockResolvedValue(details({ phone: null }));
    api.kakaoPhone.mockResolvedValue({
      provider: 'kakao',
      matched: true,
      phone: '054-852-3588',
      provider_url: 'http://place.map.kakao.com/8146617',
    });
    renderPanel();
    await screen.findByTestId('place-info-today-hours');
    expect(api.kakaoPhone).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('place-info-hours-toggle'));
    const live = await screen.findByTestId('place-info-kakao-phone');
    expect(live).toHaveTextContent('전화 (카카오)');
    expect(within(live).getByTestId('place-info-kakao-phone-number')).toHaveAttribute(
      'href',
      'tel:0548523588',
    );
    expect(within(live).getByTestId('place-info-kakao-link')).toHaveAttribute(
      'href',
      'http://place.map.kakao.com/8146617',
    );
    expect(api.kakaoPhone).toHaveBeenCalledWith('t1', POI_ID, expect.anything());
    // 접었다 다시 펼쳐도 메모리 캐시를 쓴다.
    fireEvent.click(screen.getByTestId('place-info-hours-toggle'));
    fireEvent.click(screen.getByTestId('place-info-hours-toggle'));
    expect(await screen.findByTestId('place-info-kakao-phone')).toBeInTheDocument();
    expect(api.kakaoPhone).toHaveBeenCalledTimes(1);
  });

  it('shows nothing extra when Kakao has no confident match', async () => {
    api.placeDetails.mockResolvedValue(details({ phone: null }));
    renderPanel();
    fireEvent.click(screen.getByTestId('place-info-hours-toggle'));
    await waitFor(() => expect(api.kakaoPhone).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId('place-info-kakao-phone')).toBeNull();
  });
});
