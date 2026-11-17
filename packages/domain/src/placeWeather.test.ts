import { describe, expect, it } from 'vitest';
import { placeCurrentWeather, placeWeatherCards } from './placeWeather';
import type {
  FeatureWeatherCard,
  TripViewDay,
  TripWeatherCard,
  WeatherMetric,
} from '@pinvi/schemas';

const NOW = Date.parse('2026-11-16T12:00:00+09:00');
const at = (offsetMinutes: number) => new Date(NOW + offsetMinutes * 60_000).toISOString();

const metric = (partial: Partial<WeatherMetric> & { metric_key: string }): WeatherMetric => ({
  forecast_style: 'nowcast',
  provider: 'python-kma-api',
  observed_at: at(-10),
  ...partial,
});
const dayCard = (metrics: WeatherMetric[]): TripWeatherCard => ({
  asof: at(0),
  latest_at: null,
  is_stale: false,
  source_styles: ['nowcast'],
  metrics,
});

describe('placeCurrentWeather(마커 이름 옆 날씨)', () => {
  it('일자 카드로 판정한다 — 강수형태(PTY)가 하늘상태보다 먼저, 장소 목록 배지와 같은 규칙', () => {
    const weather = placeCurrentWeather(
      null,
      dayCard([
        metric({ metric_key: 'PTY', value_number: 3 }),
        metric({ metric_key: 'T1H', value_number: -1.6, unit: 'deg_c' }),
      ]),
      NOW,
    );
    expect(weather?.condition).toBe('snow');
    expect(weather?.temp).toBeCloseTo(-1.6);
  });

  it('장소 현재 카드(목록 배지가 받은 값)가 있으면 일자 카드보다 먼저다', () => {
    const poiCard: FeatureWeatherCard = {
      feature_id: 'poi:1',
      ...dayCard([metric({ metric_key: 'PTY', value_number: 1 })]),
    };
    const weather = placeCurrentWeather(
      poiCard,
      dayCard([metric({ metric_key: 'PTY', value_number: 3 })]),
      NOW,
    );
    expect(weather?.condition).toBe('rain');
  });

  it('장소 현재 카드가 비었으면(빈 응답) 일자 카드로 내려간다', () => {
    const emptyPoiCard: FeatureWeatherCard = { feature_id: 'poi:1', ...dayCard([]) };
    const weather = placeCurrentWeather(
      emptyPoiCard,
      dayCard([metric({ metric_key: 'PTY', value_number: 3 })]),
      NOW,
    );
    expect(weather?.condition).toBe('snow');
  });

  it('날씨를 알 수 없으면 null — 아이콘을 그리지 않는다(값을 지어내지 않는다)', () => {
    expect(placeCurrentWeather(null, null, NOW)).toBeNull();
    expect(placeCurrentWeather(null, dayCard([]), NOW)).toBeNull();
    // 시각이 없는 지표만 있으면 현재로 볼 수 없다.
    expect(
      placeCurrentWeather(
        null,
        dayCard([metric({ metric_key: 'REH', value_number: 80, observed_at: null })]),
        NOW,
      ),
    ).toBeNull();
  });
});

describe('placeWeatherCards', () => {
  it('일자의 weather_by_feature_id가 found인 POI만 그 일자 카드를 받는다', () => {
    const card = dayCard([metric({ metric_key: 'SKY', value_number: 1 })]);
    const poi = (poiId: string, featureId: string | null) => ({
      poi_id: poiId,
      feature_id: featureId,
    });
    const days = [
      {
        day_index: 1,
        pois: [poi('p1', 'f1'), poi('p2', 'f2'), poi('p3', null)],
        weather_cards: { c1: card },
        weather_by_feature_id: {
          f1: { state: 'found', card_key: 'c1' },
          f2: { state: 'no_data' },
        },
      },
    ] as unknown as TripViewDay[];
    expect(placeWeatherCards(days)).toEqual({ p1: card });
  });
});
