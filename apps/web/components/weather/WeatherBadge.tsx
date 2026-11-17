'use client';

import { WeatherForecastPopup } from '@/components/weather/WeatherForecastPopup';
import { WeatherIcon } from '@/components/weather/WeatherIcon';
import { useMinuteNow, usePoiWeather } from '@/lib/usePoiWeather';
import {
  activeAlerts,
  conditionLabel,
  currentWeather,
  formatTemp,
  todayRange,
} from '@pinvi/domain';
import type { FeatureWeatherCard } from '@pinvi/schemas';
import { AlertTriangle } from 'lucide-react';
import { useMemo, useState } from 'react';

export interface WeatherBadgeProps {
  card: FeatureWeatherCard | null;
  loading?: boolean;
  /** 생략하면 버튼이 아니라 표시만 한다. */
  onOpen?: () => void;
  /** 테스트·스토리용 기준 시각. */
  now?: number;
  className?: string;
}

/** 아이콘 + 현재 기온 + 오늘 최고/최저. 보일 값이 없으면 아무것도 그리지 않는다(조용한 실패). */
export function WeatherBadge({
  card,
  loading = false,
  onOpen,
  now,
  className = '',
}: WeatherBadgeProps) {
  const clock = useMinuteNow();
  const at = now ?? clock;
  const current = useMemo(() => currentWeather(card, at), [card, at]);
  const range = useMemo(() => todayRange(card, at), [card, at]);
  const alertCount = useMemo(() => activeAlerts(card, at).length, [card, at]);

  if (!current) {
    if (!loading) return null;
    return (
      <span
        className={`inline-block h-4 w-14 animate-pulse rounded-sm bg-surface-soft ${className}`}
        aria-hidden="true"
        data-testid="weather-badge-loading"
      />
    );
  }
  const label = [
    `현재 ${conditionLabel(current.condition)}`,
    current.temp != null ? `${Math.round(current.temp)}도` : null,
    range ? `최고 ${Math.round(range.max)}도 최저 ${Math.round(range.min)}도` : null,
    alertCount > 0 ? `기상 특보 ${alertCount}건` : null,
  ]
    .filter(Boolean)
    .join(', ');
  const body = (
    <>
      <WeatherIcon condition={current.condition} night={current.night} className="h-4 w-4" />
      <span className="font-semibold text-ink" data-testid="weather-badge-temp">
        {formatTemp(current.temp)}
      </span>
      {range && (
        <span className="text-muted" data-testid="weather-badge-range">
          {formatTemp(range.max)}/{formatTemp(range.min)}
        </span>
      )}
      {alertCount > 0 && (
        <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-error-text" aria-hidden="true" />
      )}
    </>
  );
  const base = `inline-flex shrink-0 items-center gap-1 rounded-sm px-1 py-0.5 text-xs tabular-nums ${className}`;
  if (!onOpen) {
    return (
      <span className={base} aria-label={label} role="img" data-testid="weather-badge">
        {body}
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        onOpen();
      }}
      className={`${base} hover:bg-surface-soft focus-visible:outline-2 focus-visible:outline-primary`}
      aria-label={`${label} — 날씨 예보 열기`}
      aria-haspopup="dialog"
      data-testid="weather-badge"
    >
      {body}
    </button>
  );
}

export interface PoiWeatherBadgeProps {
  tripId: string;
  poiId: string;
  placeName: string;
  className?: string;
}

/** 여행 장소 하나의 날씨 배지 + 눌렀을 때 여는 예보 팝업. */
export function PoiWeatherBadge({ tripId, poiId, placeName, className }: PoiWeatherBadgeProps) {
  const weather = usePoiWeather(tripId, poiId);
  const [open, setOpen] = useState(false);
  const card = 'card' in weather ? weather.card : null;
  return (
    <>
      <WeatherBadge
        card={card}
        loading={weather.status === 'loading' || weather.status === 'idle'}
        onOpen={() => setOpen(true)}
        className={className}
      />
      <WeatherForecastPopup
        open={open}
        onClose={() => setOpen(false)}
        placeName={placeName}
        card={card}
        loading={weather.status === 'loading'}
        failed={weather.status === 'error'}
        onRefresh={weather.refresh}
      />
    </>
  );
}
