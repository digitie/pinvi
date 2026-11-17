import type { FeatureWeatherCard, TripWeatherCard } from '@pinvi/schemas';

/** 지금 비 오는(KMA 실황 PTY=1) 장소 카드 — 기온 12.4도. 시각은 지금 기준이라 언제 돌려도 "현재"다. */
export function rainyMetrics(now = Date.now()) {
  const at = new Date(Math.floor(now / 3_600_000) * 3_600_000).toISOString();
  return [
    {
      provider: 'python-kma-api',
      forecast_style: 'nowcast',
      metric_key: 'T1H',
      value_number: 12.4,
      unit: 'deg_c',
      valid_at: at,
    },
    {
      provider: 'python-kma-api',
      forecast_style: 'nowcast',
      metric_key: 'PTY',
      value_number: 1,
      unit: 'code',
      valid_at: at,
    },
  ] as FeatureWeatherCard['metrics'];
}

export function rainyPoiCard(featureId = 'poi:x'): FeatureWeatherCard {
  return { feature_id: featureId, is_stale: false, source_styles: [], metrics: rainyMetrics() };
}

export function rainyDayCard(): TripWeatherCard {
  return {
    asof: new Date().toISOString(),
    latest_at: null,
    is_stale: false,
    source_styles: [],
    metrics: rainyMetrics(),
  };
}
