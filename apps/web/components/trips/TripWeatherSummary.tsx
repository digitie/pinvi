'use client';

import { useEffect, useMemo, useState } from 'react';
import { CloudSun, Wind } from 'lucide-react';
import { featureApi } from '@pinvi/api-client';
import type { FeatureWeatherCard, WeatherMetric } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';

const WEATHER_LABELS: Record<string, string> = {
  T1H: '기온',
  TMP: '기온',
  TMN: '최저',
  TMX: '최고',
  SKY: '하늘',
  PTY: '강수',
  POP: '강수확률',
  PCP: '강수량',
  REH: '습도',
  WSD: '바람',
  PM10: '미세',
  PM25: '초미세',
};

const CURRENT_STYLE_RE = /observed|nowcast|current/i;
const FORECAST_STYLE_RE = /ultra|short|mid|forecast/i;
const DUST_RE = /pm10|pm25|미세|초미세|dust|air.?quality|cai|khai/i;
const WEATHER_RE =
  /temp|기온|T1H|TMP|TMN|TMX|sky|하늘|pty|강수|pop|pcp|reh|습도|wsd|바람|weather|날씨/i;

function metricDate(metric: WeatherMetric): string | null {
  return (
    metric.valid_at?.slice(0, 10) ??
    metric.observed_at?.slice(0, 10) ??
    metric.issued_at?.slice(0, 10) ??
    null
  );
}

function weatherAsof(date: string): string {
  return `${date}T23:59:59+09:00`;
}

function metricHaystack(metric: WeatherMetric): string {
  return [
    metric.metric_key,
    metric.metric_name,
    metric.forecast_style,
    metric.timeline_bucket,
    metric.unit,
  ]
    .filter(Boolean)
    .join(' ');
}

function metricLabel(metric: WeatherMetric): string {
  const key = metric.metric_key.toUpperCase();
  return metric.metric_name ?? WEATHER_LABELS[key] ?? metric.metric_key;
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1);
}

function formatMetric(metric: WeatherMetric): string | null {
  const value =
    metric.value_text ??
    (metric.value_number != null
      ? `${formatNumber(metric.value_number)}${metric.unit ? metric.unit : ''}`
      : null) ??
    metric.severity ??
    null;

  if (!value) return null;
  const suffix = metric.severity && metric.severity !== value ? ` ${metric.severity}` : '';
  return `${metricLabel(metric)} ${value}${suffix}`;
}

function pickMetrics(metrics: WeatherMetric[], date: string) {
  const matched = metrics.filter((metric) => metricDate(metric) === date);
  const dust = matched.filter((metric) => DUST_RE.test(metricHaystack(metric)));
  const nonDust = matched.filter((metric) => !DUST_RE.test(metricHaystack(metric)));
  const current = nonDust.filter(
    (metric) =>
      CURRENT_STYLE_RE.test(metric.forecast_style) && WEATHER_RE.test(metricHaystack(metric)),
  );
  const forecast = nonDust.filter(
    (metric) =>
      !CURRENT_STYLE_RE.test(metric.forecast_style) &&
      (FORECAST_STYLE_RE.test(metric.forecast_style) || WEATHER_RE.test(metricHaystack(metric))),
  );

  return {
    current: current
      .map(formatMetric)
      .filter((value): value is string => value != null)
      .slice(0, 2),
    forecast: forecast
      .map(formatMetric)
      .filter((value): value is string => value != null)
      .slice(0, 2),
    dust: dust
      .map(formatMetric)
      .filter((value): value is string => value != null)
      .slice(0, 2),
  };
}

export interface TripWeatherSummaryProps {
  featureId?: string | null;
  date?: string | null;
  label?: string;
  compact?: boolean;
}

export function TripWeatherSummary({
  featureId,
  date,
  label = '날씨',
  compact = false,
}: TripWeatherSummaryProps) {
  const [card, setCard] = useState<FeatureWeatherCard | null>(null);

  useEffect(() => {
    if (!featureId || !date) {
      setCard(null);
      return;
    }

    let active = true;
    setCard(null);
    void featureApi(apiClient)
      .weather(featureId, { asof: weatherAsof(date) })
      .then((next) => {
        if (active) setCard(next);
      })
      .catch(() => {
        if (active) setCard(null);
      });

    return () => {
      active = false;
    };
  }, [date, featureId]);

  const groups = useMemo(() => {
    if (!card || !date) return [];
    const picked = pickMetrics(card.metrics, date);
    return [
      { key: 'current', label: '현재', items: picked.current, icon: CloudSun },
      { key: 'forecast', label: '예보', items: picked.forecast, icon: CloudSun },
      { key: 'dust', label: '미세먼지', items: picked.dust, icon: Wind },
    ].filter((group) => group.items.length > 0);
  }, [card, date]);

  if (!featureId || !date || groups.length === 0) return null;

  return (
    <section
      className={
        compact
          ? 'space-y-1 rounded-sm bg-surface-soft/70 px-2 py-1.5'
          : 'space-y-2 rounded-sm bg-surface-soft px-3 py-2'
      }
      aria-label={label}
      data-testid="trip-weather-summary"
    >
      <p className="text-[11px] font-semibold text-muted">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {groups.map((group) => {
          const Icon = group.icon;
          return (
            <span
              key={group.key}
              className="inline-flex max-w-full items-center gap-1 rounded-sm bg-white px-2 py-1 text-[11px] text-body"
            >
              <Icon className="h-3 w-3 shrink-0 text-primary" aria-hidden="true" />
              <span className="shrink-0 font-semibold text-ink">{group.label}</span>
              <span className="min-w-0 truncate">{group.items.join(' · ')}</span>
            </span>
          );
        })}
      </div>
    </section>
  );
}
