import { describe, expect, it } from 'vitest';
import type { FeatureWeatherCard, WeatherMetric } from '@pinvi/schemas';
import {
  activeAlerts,
  conditionFromText,
  currentWeather,
  dailyForecast,
  hourlyForecast,
  kstDateKey,
  todayRange,
} from '@/lib/weatherNow';

// 2026-11-16 19:00 KST (10:00Z) — prod 샘플과 같은 시각대.
const NOW = Date.parse('2026-11-16T10:00:00Z');
const KMA = 'python-kma-api';

function m(partial: Partial<WeatherMetric> & Pick<WeatherMetric, 'metric_key' | 'forecast_style'>): WeatherMetric {
  return { provider: KMA, unit: null, ...partial };
}

function card(metrics: WeatherMetric[]): FeatureWeatherCard {
  return { feature_id: 'poi:x', is_stale: false, source_styles: [], metrics };
}

const at = (iso: string) => ({ valid_at: iso });

describe('currentWeather', () => {
  it('prefers KMA nowcast temperature over other observed providers', () => {
    const weather = currentWeather(
      card([
        m({ forecast_style: 'nowcast', metric_key: 'T1H', value_number: 11.3, unit: 'deg_c', ...at('2026-11-16T10:00:00Z') }),
        m({ forecast_style: 'observed', metric_key: 'T1H', value_number: 7.8, unit: '℃', provider: 'python-krforest-api', ...at('2026-11-16T09:00:00Z') }),
        m({ forecast_style: 'observed', metric_key: 'T1H', value_number: 9, unit: 'deg_c', provider: 'openweathermap', ...at('2026-11-16T09:30:00Z') }),
        m({ forecast_style: 'nowcast', metric_key: 'REH', value_number: 76, unit: '%', ...at('2026-11-16T10:00:00Z') }),
        m({ forecast_style: 'ultra_short', metric_key: 'SKY', value_number: 3, unit: 'code', ...at('2026-11-16T10:00:00Z') }),
        m({ forecast_style: 'ultra_short', metric_key: 'PTY', value_number: 0, unit: 'code', ...at('2026-11-16T10:00:00Z') }),
      ]),
      NOW,
    );
    expect(weather?.temp).toBe(11.3);
    expect(weather?.condition).toBe('cloudy');
    expect(weather?.humidity).toBe(76);
    expect(weather?.night).toBe(true);
    expect(weather?.provider).toBe(KMA);
  });

  it('turns KMA PTY precipitation into rain/snow regardless of sky', () => {
    const weather = currentWeather(
      card([
        m({ forecast_style: 'nowcast', metric_key: 'T1H', value_number: 1, unit: 'deg_c', ...at('2026-11-16T10:00:00Z') }),
        m({ forecast_style: 'nowcast', metric_key: 'PTY', value_number: 3, unit: 'code', ...at('2026-11-16T10:00:00Z') }),
        m({ forecast_style: 'ultra_short', metric_key: 'SKY', value_number: 1, unit: 'code', ...at('2026-11-16T10:00:00Z') }),
      ]),
      NOW,
    );
    expect(weather?.condition).toBe('snow');
  });

  it('falls back to external weather codes when KMA sky is missing', () => {
    const owm = currentWeather(
      card([
        m({ forecast_style: 'observed', metric_key: 'T1H', value_number: 5, unit: 'deg_c', provider: 'openweathermap', ...at('2026-11-16T09:30:00Z') }),
        m({ forecast_style: 'observed', metric_key: 'WEATHER_CODE', value_number: 501, unit: 'code', provider: 'openweathermap', ...at('2026-11-16T09:30:00Z') }),
      ]),
      NOW,
    );
    expect(owm?.condition).toBe('rain');
    const weatherapi = currentWeather(
      card([
        m({ forecast_style: 'observed', metric_key: 'T1H', value_number: 5, unit: 'deg_c', provider: 'weatherapi', ...at('2026-11-16T09:30:00Z') }),
        m({ forecast_style: 'observed', metric_key: 'WEATHER_CODE', value_number: 1213, unit: 'code', provider: 'weatherapi', ...at('2026-11-16T09:30:00Z') }),
      ]),
      NOW,
    );
    expect(weatherapi?.condition).toBe('snow');
  });

  it('ignores non-celsius temperatures and returns null when nothing usable exists', () => {
    expect(
      currentWeather(
        card([m({ forecast_style: 'observed', metric_key: 'T1H', value_number: 50, unit: 'deg_f', ...at('2026-11-16T10:00:00Z') })]),
        NOW,
      ),
    ).toBeNull();
    expect(currentWeather(card([]), NOW)).toBeNull();
    expect(currentWeather(null, NOW)).toBeNull();
  });
});

describe('hourly/daily forecast', () => {
  const metrics: WeatherMetric[] = [
    // 오늘 밤 KST 20시(11Z) — 기상청과 외부가 같은 시각을 주면 기상청 값.
    m({ forecast_style: 'short', metric_key: 'TMP', value_number: 6, unit: 'deg_c', ...at('2026-11-16T11:00:00Z') }),
    m({ forecast_style: 'short', metric_key: 'TMP', value_number: 9, unit: 'deg_c', provider: 'openweathermap', ...at('2026-11-16T11:00:00Z') }),
    m({ forecast_style: 'short', metric_key: 'POP', value_number: 30, unit: '%', ...at('2026-11-16T11:00:00Z') }),
    m({ forecast_style: 'short', metric_key: 'SKY', value_number: 4, unit: 'code', ...at('2026-11-16T11:00:00Z') }),
    // 내일 KST 12시(03Z) 비.
    m({ forecast_style: 'short', metric_key: 'TMP', value_number: 12, unit: 'deg_c', ...at('2026-11-17T03:00:00Z') }),
    m({ forecast_style: 'short', metric_key: 'PTY', value_number: 1, unit: 'code', ...at('2026-11-17T03:00:00Z') }),
    m({ forecast_style: 'short', metric_key: 'POP', value_number: 80, unit: '%', ...at('2026-11-17T03:00:00Z') }),
    // 내일 KST 06시(전날 21Z) 맑음, 기온 2.
    m({ forecast_style: 'short', metric_key: 'TMP', value_number: 2, unit: 'deg_c', ...at('2026-11-16T21:00:00Z') }),
    m({ forecast_style: 'short', metric_key: 'SKY', value_number: 1, unit: 'code', ...at('2026-11-16T21:00:00Z') }),
    // 기상청 TMX가 있으면 시간별 최고보다 우선.
    m({ forecast_style: 'short', metric_key: 'TMX', value_number: 14, unit: 'deg_c', ...at('2026-11-17T06:00:00Z') }),
    // 오늘 이미 지난 관측.
    m({ forecast_style: 'observed', metric_key: 'T1H', value_number: 13, unit: 'deg_c', ...at('2026-11-16T05:00:00Z') }),
    // 중기예보 문장.
    m({ forecast_style: 'mid', metric_key: 'SKY', value_text: '구름많고 눈', provider: KMA, ...at('2026-11-20T03:00:00Z') }),
    m({ forecast_style: 'mid', metric_key: 'TMN', value_number: -3, unit: 'deg_c', ...at('2026-11-20T03:00:00Z') }),
    m({ forecast_style: 'mid', metric_key: 'TMX', value_number: 4, unit: 'deg_c', ...at('2026-11-20T03:00:00Z') }),
  ];

  it('builds an hourly strip with provider priority and POP', () => {
    const hours = hourlyForecast(card(metrics), NOW, 24);
    expect(hours.map((hour) => hour.temp)).toEqual([6, 2, 12]);
    expect(hours[0]).toMatchObject({ condition: 'overcast', pop: 30, night: true });
    expect(hours[2]).toMatchObject({ condition: 'rain', pop: 80, night: false });
  });

  it('aggregates daily max/min, POP and a representative condition', () => {
    const days = dailyForecast(card(metrics), NOW, 7);
    expect(days.map((day) => day.date)).toEqual(['2026-11-16', '2026-11-17', '2026-11-20']);
    expect(days[0]).toMatchObject({ max: 13, min: 6, popMax: 30 });
    expect(days[1]).toMatchObject({ max: 14, min: 2, popMax: 80, condition: 'rain' });
    expect(days[2]).toMatchObject({ max: 4, min: -3, condition: 'snow' });
    expect(todayRange(card(metrics), NOW)).toEqual({ max: 13, min: 6 });
  });

  it('uses the only value for both ends and returns null without temperatures', () => {
    expect(
      todayRange(
        card([m({ forecast_style: 'short', metric_key: 'TMP', value_number: 6, unit: 'deg_c', ...at('2026-11-16T11:00:00Z') })]),
        NOW,
      ),
    ).toEqual({ max: 6, min: 6 });
    expect(todayRange(card([]), NOW)).toBeNull();
  });
});

describe('alerts and helpers', () => {
  it('keeps only unexpired, de-duplicated advisories', () => {
    const alerts = activeAlerts(
      card([
        m({ forecast_style: 'advisory', metric_key: 'WRN', value_text: '강풍주의보', severity: '주의보', valid_until: '2026-11-17T00:00:00Z' }),
        m({ forecast_style: 'advisory', metric_key: 'WRN', value_text: '강풍주의보', severity: '주의보', valid_until: '2026-11-17T00:00:00Z' }),
        m({ forecast_style: 'advisory', metric_key: 'WRN', value_text: '건조주의보', valid_until: '2026-11-16T01:00:00Z' }),
      ]),
      NOW,
    );
    expect(alerts.map((alert) => alert.title)).toEqual(['강풍주의보']);
  });

  it('parses KMA mid-term sentences', () => {
    expect(conditionFromText('흐리고 비/눈')).toBe('sleet');
    expect(conditionFromText('구름많고 소나기')).toBe('shower');
    expect(conditionFromText('맑음')).toBe('clear');
    expect(conditionFromText('')).toBeNull();
  });

  it('computes KST dates across the UTC midnight boundary', () => {
    expect(kstDateKey(Date.parse('2026-11-16T15:30:00Z'))).toBe('2026-11-17');
  });
});
