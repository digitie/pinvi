import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { FeatureWeatherCard, TripViewPoi } from '@pinvi/schemas';
import { PoiWeatherBadge, WeatherBadge } from '@/components/weather/WeatherBadge';
import { WeatherForecastPopup } from '@/components/weather/WeatherForecastPopup';
import { TripPoiList } from '@/components/trips/TripPoiList';
import { __resetPoiWeatherForTest, refreshPoiWeather } from '@/lib/usePoiWeather';

const NOW = Date.parse('2026-11-16T03:00:00Z'); // 12:00 KST

const CARD: FeatureWeatherCard = {
  feature_id: 'f_1',
  is_stale: false,
  latest_at: '2026-11-16T03:00:00Z',
  source_styles: ['nowcast', 'short', 'advisory'],
  metrics: [
    { forecast_style: 'nowcast', metric_key: 'T1H', value_number: 11.3, unit: 'deg_c', provider: 'python-kma-api', valid_at: '2026-11-16T03:00:00Z' },
    { forecast_style: 'ultra_short', metric_key: 'SKY', value_number: 1, unit: 'code', provider: 'python-kma-api', valid_at: '2026-11-16T03:00:00Z' },
    { forecast_style: 'short', metric_key: 'TMP', value_number: 13, unit: 'deg_c', provider: 'python-kma-api', valid_at: '2026-11-16T05:00:00Z' },
    { forecast_style: 'short', metric_key: 'POP', value_number: 60, unit: '%', provider: 'python-kma-api', valid_at: '2026-11-16T05:00:00Z' },
    { forecast_style: 'short', metric_key: 'TMP', value_number: 4, unit: 'deg_c', provider: 'python-kma-api', valid_at: '2026-11-16T12:00:00Z' },
    { forecast_style: 'short', metric_key: 'TMP', value_number: 8, unit: 'deg_c', provider: 'python-kma-api', valid_at: '2026-11-17T03:00:00Z' },
    { forecast_style: 'advisory', metric_key: 'WRN', value_text: '강풍주의보', severity: '주의보', provider: 'python-kma-api', valid_until: '2026-11-17T00:00:00Z' },
  ],
};

beforeEach(() => {
  // Date만 고정한다 — 타이머까지 가짜로 바꾸면 waitFor·Promise가 멈춘다.
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(NOW);
});
afterEach(() => {
  __resetPoiWeatherForTest();
  vi.useRealTimers();
});

describe('WeatherBadge', () => {
  it('shows icon, current temperature and today max/min', () => {
    const onOpen = vi.fn();
    render(<WeatherBadge card={CARD} now={NOW} onOpen={onOpen} />);
    const badge = screen.getByTestId('weather-badge');
    expect(within(badge).getByTestId('weather-badge-temp')).toHaveTextContent('11°');
    expect(within(badge).getByTestId('weather-badge-range')).toHaveTextContent('13°/4°');
    expect(badge).toHaveAccessibleName(/현재 맑음.*기상 특보 1건/);
    expect(badge.querySelector('[data-weather-condition="clear"]')).not.toBeNull();
    fireEvent.click(badge);
    expect(onOpen).toHaveBeenCalledOnce();
  });

  it('renders nothing when there is no usable weather (quiet failure)', () => {
    const { container } = render(
      <WeatherBadge card={{ ...CARD, metrics: [] }} now={NOW} onOpen={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe('WeatherForecastPopup', () => {
  it('shows current, alerts, hourly strip with POP and daily max/min', () => {
    render(
      <WeatherForecastPopup open onClose={() => {}} placeName="하회마을" card={CARD} now={NOW} onRefresh={() => {}} />,
    );
    expect(screen.getByText('하회마을 날씨')).toBeInTheDocument();
    expect(screen.getByTestId('weather-current-temp')).toHaveTextContent('11°');
    expect(screen.getByTestId('weather-today-range')).toHaveTextContent('최고 13° · 최저 4°');
    expect(screen.getByTestId('weather-alerts')).toHaveTextContent('강풍주의보');
    const hours = screen.getAllByTestId('weather-hour');
    expect(hours[0]).toHaveTextContent('14시');
    expect(hours[0]).toHaveTextContent('60%');
    const days = screen.getAllByTestId('weather-day');
    expect(days.map((day) => day.textContent)).toEqual([
      expect.stringContaining('오늘'),
      expect.stringContaining('내일'),
    ]);
    expect(screen.getByText(/출처: 기상청/)).toBeInTheDocument();
  });

  it('tells the user when nothing could be loaded', () => {
    render(
      <WeatherForecastPopup open onClose={() => {}} placeName="x" card={null} failed now={NOW} />,
    );
    expect(screen.getByTestId('weather-empty')).toHaveTextContent('날씨를 불러오지 못했습니다.');
  });
});

describe('PoiWeatherBadge + shared cache', () => {
  it('loads once per place, opens the popup and refreshes on demand', async () => {
    const loader = vi.fn(async () => CARD);
    __resetPoiWeatherForTest(loader);
    render(
      <>
        <PoiWeatherBadge tripId="t1" poiId="p1" placeName="하회마을" />
        <PoiWeatherBadge tripId="t1" poiId="p1" placeName="하회마을" />
      </>,
    );
    await waitFor(() => expect(screen.getAllByTestId('weather-badge')).toHaveLength(2));
    expect(loader).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getAllByTestId('weather-badge')[0]!);
    expect(await screen.findByTestId('weather-forecast-popup')).toBeInTheDocument();
    await act(async () => {
      refreshPoiWeather('t1');
    });
    await waitFor(() => expect(loader).toHaveBeenCalledTimes(2));
  });

  it('stays empty when the request fails', async () => {
    __resetPoiWeatherForTest(async () => {
      throw new Error('503');
    });
    const { container } = render(<PoiWeatherBadge tripId="t1" poiId="p2" placeName="x" />);
    await waitFor(() => expect(screen.queryByTestId('weather-badge-loading')).toBeNull());
    expect(container.querySelector('[data-testid="weather-badge"]')).toBeNull();
  });

  it('limits concurrent requests', async () => {
    let inFlight = 0;
    let peak = 0;
    const resolvers: Array<() => void> = [];
    __resetPoiWeatherForTest(
      () =>
        new Promise<FeatureWeatherCard>((resolve) => {
          inFlight += 1;
          peak = Math.max(peak, inFlight);
          resolvers.push(() => {
            inFlight -= 1;
            resolve(CARD);
          });
        }),
    );
    render(
      <>
        {['a', 'b', 'c', 'd'].map((id) => (
          <PoiWeatherBadge key={id} tripId="t1" poiId={id} placeName={id} />
        ))}
      </>,
    );
    await waitFor(() => expect(resolvers.length).toBe(2));
    expect(peak).toBe(2);
    await act(async () => {
      resolvers.splice(0).forEach((resolve) => resolve());
    });
    await waitFor(() => expect(resolvers.length).toBe(2));
    await act(async () => {
      resolvers.splice(0).forEach((resolve) => resolve());
    });
    expect(peak).toBe(2);
  });
});

describe('TripPoiList current weather', () => {
  const poi = {
    poi_id: 'p9',
    feature_id: 'f_9',
    sort_order: 'a0',
    title: '경복궁',
    feature: {},
    marker_color: null,
    marker_icon: null,
    display_marker_color: null,
    feature_resolution_state: 'found',
    user_note: null,
    planned_arrival_at: null,
    planned_departure_at: null,
    budget_amount: null,
    actual_amount: null,
    currency: 'KRW',
    user_url: null,
    rise_set: null,
    feature_link_broken_at: null,
    version: 1,
    created_at: '2026-11-16T00:00:00Z',
    updated_at: '2026-11-16T00:00:00Z',
  } as unknown as TripViewPoi;

  it('renders the badge next to the place name only when enabled', async () => {
    const loader = vi.fn(async () => CARD);
    __resetPoiWeatherForTest(loader);
    const { rerender } = render(<TripPoiList pois={[poi]} tripId="t9" />);
    expect(loader).not.toHaveBeenCalled();
    rerender(<TripPoiList pois={[poi]} tripId="t9" showCurrentWeather />);
    await waitFor(() => expect(screen.getByTestId('weather-badge')).toBeInTheDocument());
    expect(loader).toHaveBeenCalledWith('t9', 'p9');
  });

  it('opening the badge does not select the row', async () => {
    __resetPoiWeatherForTest(async () => CARD);
    const onSelectPoi = vi.fn();
    render(<TripPoiList pois={[poi]} tripId="t9" showCurrentWeather onSelectPoi={onSelectPoi} />);
    fireEvent.click(await screen.findByTestId('weather-badge'));
    expect(onSelectPoi).not.toHaveBeenCalled();
    expect(await screen.findByTestId('weather-forecast-popup')).toBeInTheDocument();
  });
});
