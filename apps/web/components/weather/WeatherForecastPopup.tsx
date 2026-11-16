'use client';

import { Dialog } from '@/components/ui/Dialog';
import { WeatherIcon } from '@/components/weather/WeatherIcon';
import { useMinuteNow } from '@/lib/usePoiWeather';
import { providerLabel } from '@/lib/weatherProviderLabels';
import {
  activeAlerts,
  conditionLabel,
  currentWeather,
  dailyForecast,
  formatTemp,
  hourlyForecast,
  kstDateKey,
  kstHour,
  todayRange,
  type CurrentWeather,
  type DailyWeather,
  type HourlyWeather,
  type WeatherAlert,
} from '@/lib/weatherNow';
import type { FeatureWeatherCard } from '@pinvi/schemas';
import { AlertTriangle, Droplet, Loader2, RefreshCw } from 'lucide-react';
import { useMemo } from 'react';

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];
const DAY_MS = 86_400_000;
const KST_MS = 9 * 3_600_000;

function dayLabel(date: string, today: string): string {
  const [y, m, d] = date.split('-').map(Number) as [number, number, number];
  const offset = Math.round((Date.UTC(y, m - 1, d) - Date.parse(`${today}T00:00:00Z`)) / DAY_MS);
  if (offset === 0) return '오늘';
  if (offset === 1) return '내일';
  if (offset === 2) return '모레';
  return `${WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]} ${m}.${d}`;
}

function formatKstClock(epochMs: number): string {
  const date = new Date(epochMs + KST_MS);
  return `${String(date.getUTCHours()).padStart(2, '0')}:${String(date.getUTCMinutes()).padStart(2, '0')}`;
}

function formatKstMoment(value: number | null): string {
  if (value == null) return '';
  const date = new Date(value + KST_MS);
  return `${date.getUTCMonth() + 1}.${date.getUTCDate()} ${formatKstClock(value)}`;
}

function alertRange(alert: WeatherAlert): string | null {
  if (alert.from == null && alert.until == null) return null;
  return `${formatKstMoment(alert.from)} ~ ${formatKstMoment(alert.until)}`.trim();
}

function currentDetails(current: CurrentWeather): string {
  return [
    current.feelsLike != null ? `체감 ${formatTemp(current.feelsLike)}` : null,
    current.humidity != null ? `습도 ${Math.round(current.humidity)}%` : null,
    current.windSpeed != null ? `바람 ${current.windSpeed.toFixed(1)}m/s` : null,
    current.pop != null ? `강수확률 ${Math.round(current.pop)}%` : null,
  ]
    .filter(Boolean)
    .join(' · ');
}

function CurrentSection({
  current,
  range,
}: {
  current: CurrentWeather;
  range: { max: number; min: number } | null;
}) {
  return (
    <section
      className="flex items-center gap-3"
      aria-label="현재 날씨"
      data-testid="weather-current"
    >
      <WeatherIcon condition={current.condition} night={current.night} className="h-12 w-12" />
      <div className="min-w-0">
        <p className="flex items-baseline gap-2">
          <span
            className="text-4xl font-bold text-ink tabular-nums"
            data-testid="weather-current-temp"
          >
            {formatTemp(current.temp)}
          </span>
          <span className="text-base font-semibold text-ink">
            {conditionLabel(current.condition)}
          </span>
        </p>
        {range && (
          <p className="text-sm text-body tabular-nums" data-testid="weather-today-range">
            최고 {formatTemp(range.max)} · 최저 {formatTemp(range.min)}
          </p>
        )}
        <p className="text-xs text-muted tabular-nums">{currentDetails(current)}</p>
      </div>
    </section>
  );
}

function AlertsSection({ alerts }: { alerts: WeatherAlert[] }) {
  return (
    <section
      className="space-y-1 rounded-sm bg-error-bg px-3 py-2"
      aria-label="기상 특보"
      data-testid="weather-alerts"
    >
      {alerts.map((alert) => {
        const range = alertRange(alert);
        return (
          <p
            key={`${alert.title}|${alert.severity ?? ''}`}
            className="flex items-start gap-1.5 text-sm text-error-text"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>
              <span className="font-semibold">{alert.title}</span>
              {alert.severity && alert.severity !== alert.title ? ` (${alert.severity})` : ''}
              {range ? <span className="block text-xs">{range}</span> : null}
            </span>
          </p>
        );
      })}
    </section>
  );
}

function HourlySection({ hours, now }: { hours: HourlyWeather[]; now: number }) {
  return (
    <section aria-label="시간별 예보" data-testid="weather-hourly">
      <h3 className="mb-1 text-xs font-semibold text-muted">시간별 예보</h3>
      <ol className="flex gap-1 overflow-x-auto pb-1">
        {hours.map((hour, index) => (
          <li
            key={hour.at}
            className="flex w-12 shrink-0 flex-col items-center gap-1 rounded-sm py-1 text-xs"
            data-testid="weather-hour"
          >
            <span className="text-muted">
              {index === 0 && hour.at <= now ? '지금' : `${kstHour(hour.at)}시`}
            </span>
            <WeatherIcon
              condition={hour.condition}
              night={hour.night}
              className="h-5 w-5"
              label={conditionLabel(hour.condition)}
            />
            <span className="font-semibold text-ink tabular-nums">{formatTemp(hour.temp)}</span>
            <span
              className={`flex items-center gap-0.5 tabular-nums ${
                hour.pop != null && hour.pop >= 50 ? 'text-primary' : 'text-muted'
              }`}
            >
              <Droplet className="h-3 w-3" aria-hidden="true" />
              {hour.pop != null ? `${Math.round(hour.pop)}%` : '-'}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function DailySection({ days, today }: { days: DailyWeather[]; today: string }) {
  return (
    <section aria-label="일별 예보" data-testid="weather-daily">
      <h3 className="mb-1 text-xs font-semibold text-muted">일별 예보</h3>
      <ol className="divide-y divide-hairline">
        {days.map((day) => (
          <li
            key={day.date}
            className="flex items-center gap-2 py-1.5 text-sm"
            data-testid="weather-day"
          >
            <span className="w-16 shrink-0 font-semibold text-ink">
              {dayLabel(day.date, today)}
            </span>
            <WeatherIcon
              condition={day.condition}
              className="h-5 w-5"
              label={conditionLabel(day.condition)}
            />
            <span className="flex w-12 items-center gap-0.5 text-xs text-primary tabular-nums">
              {day.popMax != null && (
                <>
                  <Droplet className="h-3 w-3" aria-hidden="true" />
                  {Math.round(day.popMax)}%
                </>
              )}
            </span>
            <span className="ml-auto tabular-nums">
              <span className="text-primary">{formatTemp(day.min)}</span>
              <span className="text-muted"> / </span>
              <span className="text-error-text">{formatTemp(day.max)}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function SourceFooter({
  card,
  loading,
  onRefresh,
}: {
  card: FeatureWeatherCard | null;
  loading: boolean;
  onRefresh?: () => void;
}) {
  const sources = useMemo(
    () =>
      Array.from(
        new Set(
          (card?.metrics ?? [])
            .map((metric) => providerLabel(metric.provider))
            .filter((value): value is string => value != null),
        ),
      ),
    [card],
  );
  const parts = [
    sources.length > 0 ? `출처: ${sources.join(', ')}` : null,
    card?.latest_at ? `${formatKstClock(Date.parse(card.latest_at))} 기준` : null,
    card?.is_stale ? '일부 지연' : null,
  ].filter(Boolean);
  return (
    <footer className="flex items-center gap-2 text-xs text-muted">
      <span className="min-w-0 flex-1">{parts.join(' · ')}</span>
      {onRefresh && (
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="inline-flex min-h-11 items-center gap-1 rounded-sm px-2 text-xs font-semibold text-ink hover:bg-surface-soft disabled:opacity-60"
          data-testid="weather-refresh"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          )}
          새로고침
        </button>
      )}
    </footer>
  );
}

function emptyText(loading: boolean, failed: boolean): string {
  if (loading) return '날씨를 불러오는 중입니다.';
  if (failed) return '날씨를 불러오지 못했습니다.';
  return '이 장소의 날씨 정보가 없습니다.';
}

export interface WeatherForecastBodyProps {
  card: FeatureWeatherCard | null;
  loading?: boolean;
  failed?: boolean;
  onRefresh?: () => void;
  /** 테스트용 기준 시각. */
  now?: number;
}

/**
 * 현재 날씨 + 특보 + 시간별(기온·강수확률) 띠 + 일별 최고/최저 — 네이버 날씨 모바일 화면의 정보 순서를
 * 따른다. 날씨 팝업과 장소 정보 패널의 날씨 항목이 같은 본문을 쓴다.
 */
export function WeatherForecastBody({
  card,
  loading = false,
  failed = false,
  onRefresh,
  now,
}: WeatherForecastBodyProps) {
  const clock = useMinuteNow();
  const at = now ?? clock;
  const view = useMemo(
    () => ({
      current: currentWeather(card, at),
      range: todayRange(card, at),
      hours: hourlyForecast(card, at, 24),
      days: dailyForecast(card, at, 7),
      alerts: activeAlerts(card, at),
    }),
    [card, at],
  );
  const { current, range, hours, days, alerts } = view;
  const empty = !current && hours.length === 0 && days.length === 0 && alerts.length === 0;
  return (
    <div className="space-y-4">
      {current && <CurrentSection current={current} range={range} />}
      {alerts.length > 0 && <AlertsSection alerts={alerts} />}
      {hours.length > 0 && <HourlySection hours={hours} now={at} />}
      {days.length > 0 && <DailySection days={days} today={kstDateKey(at)} />}
      {empty && (
        <p className="text-sm text-muted" data-testid="weather-empty" role="status">
          {emptyText(loading, failed)}
        </p>
      )}
      <SourceFooter card={card} loading={loading} onRefresh={onRefresh} />
    </div>
  );
}

export interface WeatherForecastPopupProps extends WeatherForecastBodyProps {
  open: boolean;
  onClose: () => void;
  placeName: string;
}

/** 장소 날씨 예보 팝업 — 모바일은 하단 시트, 데스크톱은 중앙 다이얼로그다. */
export function WeatherForecastPopup({
  open,
  onClose,
  placeName,
  ...body
}: WeatherForecastPopupProps) {
  if (!open) return null;
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={`${placeName} 날씨`}
      size="sm"
      variant="sheet"
      testId="weather-forecast-popup"
    >
      <WeatherForecastBody {...body} />
    </Dialog>
  );
}
