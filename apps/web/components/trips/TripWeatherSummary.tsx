'use client';

import React, { useMemo } from 'react';
import { CloudSun, Wind } from 'lucide-react';
import type { TripWeatherCard, TripWeatherResolution, WeatherMetric } from '@pinvi/schemas';

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
const SEOUL_DATE_FORMATTER = new Intl.DateTimeFormat('en', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

function metricDate(metric: WeatherMetric): string | null {
  const instant =
    metric.effective_at ?? metric.valid_at ?? metric.observed_at ?? metric.valid_from ?? null;
  if (!instant) return null;
  const value = new Date(instant);
  if (Number.isNaN(value.getTime())) return null;
  const parts = Object.fromEntries(
    SEOUL_DATE_FORMATTER.formatToParts(value).map(({ type, value: part }) => [type, part]),
  );
  return parts.year && parts.month && parts.day
    ? `${parts.year}-${parts.month}-${parts.day}`
    : null;
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
  weather?: TripWeatherResolution | null;
  weatherCards?: Record<string, TripWeatherCard>;
  date?: string | null;
  label?: string;
  compact?: boolean;
}

export function TripWeatherSummary({
  weather,
  weatherCards = {},
  date,
  label = '날씨',
  compact = false,
}: TripWeatherSummaryProps) {
  const card = weather?.state === 'found' ? (weatherCards[weather.card_key] ?? null) : null;

  const groups = useMemo(() => {
    if (!card || !date) return [];
    const picked = pickMetrics(card.metrics, date);
    return [
      { key: 'current', label: '현재', items: picked.current, icon: CloudSun },
      { key: 'forecast', label: '예보', items: picked.forecast, icon: CloudSun },
      { key: 'dust', label: '미세먼지', items: picked.dust, icon: Wind },
    ].filter((group) => group.items.length > 0);
  }, [card, date]);

  if (!date || !weather) return null;
  if (weather.state !== 'found' || !card || groups.length === 0) {
    const statusText =
      weather.state === 'found'
        ? card
          ? '이 날짜의 날씨 정보가 없습니다.'
          : '날씨 서비스를 일시적으로 사용할 수 없습니다.'
        : {
            no_data: '이 날짜의 날씨 정보가 없습니다.',
            retired: '장소 상태가 종료되어 날씨를 확인할 수 없습니다.',
            suppressed: '비공개 장소는 날씨를 확인할 수 없습니다.',
            missing: '장소 정보를 찾을 수 없어 날씨를 확인할 수 없습니다.',
            unavailable: '날씨 서비스를 일시적으로 사용할 수 없습니다.',
          }[weather.state];
    return (
      <section
        className={
          compact
            ? 'rounded-sm bg-surface-soft/70 px-2 py-1.5'
            : 'rounded-sm bg-surface-soft px-3 py-2'
        }
        aria-label={label}
        data-testid="trip-weather-status"
      >
        <p className="text-xs text-muted">{statusText}</p>
      </section>
    );
  }

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
      <p className="text-xs font-semibold text-muted">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {groups.map((group) => {
          const Icon = group.icon;
          return (
            <span
              key={group.key}
              className="inline-flex max-w-full items-center gap-1 rounded-sm bg-canvas px-2 py-1 text-xs text-body"
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
