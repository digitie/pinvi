import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { PoiPlaceDetails, TripViewPoi } from '@pinvi/schemas';

const api = vi.hoisted(() => ({
  placeDetails: vi.fn(),
  refreshPlaceDetails: vi.fn(),
  kakaoPhone: vi.fn(),
  weather: vi.fn(),
}));
const features = vi.hoisted(() => ({ detailCard: vi.fn() }));

vi.mock('@pinvi/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@pinvi/api-client')>();
  return { ...actual, poiApi: () => api, featureApi: () => features };
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
  features.detailCard.mockReset();
  // 기본은 TourAPI 소개가 없는 장소다 — 소개 항목이 생기지 않는다.
  features.detailCard.mockResolvedValue(placeCard(null));
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

function placeCard(introduction: unknown, visitGuide: unknown = null) {
  return {
    kind: 'place',
    feature_id: 'f_hahoe',
    name: '하회마을',
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
    introduction,
    visit_guide: visitGuide,
  };
}

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
  const INTRO_IMAGE = 'https://tong.visitkorea.or.kr/cms/resource/a.jpg';
  function hahoeIntro(overview: string | null) {
    return {
      provider: 'tourapi',
      attribution: '한국관광공사',
      overview,
      reference_date: null,
      images: [
        {
          url: INTRO_IMAGE,
          alt: '하회마을 대표 사진',
          kogl_type: 1,
          no_derivatives: false,
          license_label: '공공누리 제1유형: 출처표시',
          license_url: 'https://www.kogl.or.kr/info/licenseType1.do',
        },
      ],
    };
  }

  it('TourAPI 소개가 있으면 고정 항목 뒤(지도 앱 앞)에 소개 항목을 두고 이미지·소개문·출처를 보인다', async () => {
    api.placeDetails.mockResolvedValue(details());
    features.detailCard.mockResolvedValue(
      placeCard(hahoeIntro('하회마을은 풍산 류씨가 600여 년간 대대로 살아온 동성마을이다.')),
    );
    renderPanel();
    const toggle = await screen.findByTestId('place-info-about-toggle');
    expect(features.detailCard).toHaveBeenCalledWith(
      'f_hahoe',
      expect.anything(),
      expect.anything(),
    );
    // 늦게 생겨도 앞 항목 버튼은 밀리지 않는다 — 날씨·영업 정보·메모·링크 다음, 지도 앱 앞.
    const keys = within(screen.getByTestId('place-info-sections'))
      .getAllByRole('button')
      .map((button) => button.getAttribute('data-testid'));
    expect(keys).toEqual([
      'place-info-weather-toggle',
      'place-info-hours-toggle',
      'place-info-memo-toggle',
      'place-info-links-toggle',
      'place-info-about-toggle',
      'place-info-maps-toggle',
    ]);
    expect(toggle).toHaveTextContent('소개');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    const section = screen.getByTestId('place-info-about');
    expect(section).toHaveAttribute('aria-label', '소개');
    expect(within(section).getByTestId('place-info-introduction-image')).toHaveAttribute(
      'alt',
      '하회마을 대표 사진',
    );
    expect(within(section).getByTestId('place-info-introduction-overview')).toHaveTextContent(
      '풍산 류씨',
    );
    expect(within(section).getByTestId('place-info-introduction-attribution')).toHaveTextContent(
      '출처: 한국관광공사',
    );
  });

  it('이미지만 있는 소개는 이미지가 깨지면 항목째 사라지고 펼침도 풀린다(빈 항목 없음)', async () => {
    api.placeDetails.mockResolvedValue(details());
    features.detailCard.mockResolvedValue(placeCard(hahoeIntro(null)));
    renderPanel();
    fireEvent.click(await screen.findByTestId('place-info-about-toggle'));
    fireEvent.error(screen.getByTestId('place-info-introduction-image'));
    expect(screen.queryByTestId('place-info-about-toggle')).toBeNull();
    expect(screen.queryByTestId('place-info-about')).toBeNull();
    for (const key of ['weather', 'hours', 'memo', 'links', 'maps']) {
      expect(screen.getByTestId(`place-info-${key}-toggle`)).toHaveAttribute(
        'aria-expanded',
        'false',
      );
    }
  });

  it.each([
    ['소개 없음', () => features.detailCard.mockResolvedValue(placeCard(null))],
    ['읽기 실패', () => features.detailCard.mockRejectedValue(new Error('down'))],
  ])('%s이면 응답을 처리한 뒤에도 소개 항목을 만들지 않는다', async (_label, arrange) => {
    api.placeDetails.mockResolvedValue(details());
    arrange();
    renderPanel();
    await waitFor(() => expect(features.detailCard).toHaveBeenCalled());
    // 응답 promise가 처리될 때까지 기다린 뒤 확인한다(늦게 나타나는 회귀를 잡는다).
    await act(async () => {
      await features.detailCard.mock.results[0]?.value?.catch(() => undefined);
    });
    expect(screen.queryByTestId('place-info-about-toggle')).toBeNull();
    expect(screen.queryByTestId('place-info-guide-toggle')).toBeNull();
  });

  it('이용 안내가 있으면 소개 뒤·지도 앱 앞에 이용 안내 항목을 두고 무장애 배지를 펼친다', async () => {
    api.placeDetails.mockResolvedValue(details());
    features.detailCard.mockResolvedValue(
      placeCard(hahoeIntro('소개'), {
        provider: 'tourapi',
        attribution: '한국관광공사',
        reference_date: null,
        usage_hours: '09:00~18:00',
        rest_days: null,
        parking: '가능',
        parking_fee: null,
        fees: [{ audience: 'adult', amount_krw: 5000 }],
        fee_text: null,
        discount: null,
        reservation: null,
        inquiry: null,
        transport: null,
        facilities: null,
        capacity: null,
        accommodation_available: null,
        pet_note: null,
        accessibility: [
          { group: 'physical', facility: 'parking', label: '주차', text: '장애인 주차 2면' },
        ],
        pet_policy: null,
      }),
    );
    renderPanel();
    const toggle = await screen.findByTestId('place-info-guide-toggle');
    const keys = within(screen.getByTestId('place-info-sections'))
      .getAllByRole('button')
      .map((button) => button.getAttribute('data-testid'));
    expect(keys.slice(-3)).toEqual([
      'place-info-about-toggle',
      'place-info-guide-toggle',
      'place-info-maps-toggle',
    ]);
    expect(toggle).toHaveTextContent('이용 안내');
    fireEvent.click(toggle);
    const section = screen.getByTestId('place-info-guide');
    expect(within(section).getByTestId('place-info-visit-guide-fees')).toHaveTextContent(
      '성인 5,000원',
    );
    // 영업 정보 항목이 이미 이용시간을 보이므로 이용 안내에서는 뺀다(같은 원문이 두 번 보이지 않게).
    expect(within(section).queryByTestId('place-info-visit-guide-usage_hours')).toBeNull();
    expect(within(section).getByTestId('place-info-visit-guide-parking')).toHaveTextContent('가능');
    fireEvent.click(within(section).getByTestId('place-info-visit-guide-accessibility-toggle'));
    expect(within(section).getByTestId('place-info-visit-guide-accessibility')).toHaveTextContent(
      '주차: 장애인 주차 2면',
    );
    expect(within(section).getByTestId('place-info-visit-guide-attribution')).toHaveTextContent(
      '출처: 한국관광공사',
    );
  });

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
