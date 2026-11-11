'use client';

import { withOccurrenceKeys } from '@/lib/occurrenceKeys';
import { providerLabel } from '@/lib/weatherProviderLabels';
import type { TripWeatherCard, TripWeatherResolution, WeatherMetric } from '@pinvi/schemas';
import { CloudSun, Wind } from 'lucide-react';
import { useMemo } from 'react';

const WEATHER_LABELS: Record<string, string> = {
  TEMP: '기온',
  T3H: '기온',
  FEELS_LIKE: '체감온도',
  HUMIDITY: '습도',
  WIND_SPEED: '바람',
  PRECIP_PROB: '강수확률',
  PRECIP: '강수량',
  CLOUD_COVER: '운량',
  WEATHER_CODE: '날씨 코드',
  T1H: '기온',
  TMP: '기온',
  TMN: '최저',
  TMX: '최고',
  SKY: '하늘',
  PTY: '강수형태',
  VEC: '풍향',
  WIND_DIRECTION: '풍향',
  POP: '강수확률',
  PCP: '강수량',
  RN1: '1시간 강수량',
  REH: '습도',
  WSD: '바람',
  PM10: '미세',
  PM25: '초미세',
};

const CURRENT_STYLE_RE = /observed|nowcast|current/i;
const FORECAST_STYLE_RE = /ultra|short|mid|forecast/i;
const DUST_RE = /pm10|pm25|미세|초미세|dust|air.?quality|cai|khai/i;
const WEATHER_RE =
  /temp|기온|T1H|TMP|TMN|TMX|sky|하늘|pty|강수|pop|pcp|reh|습도|wsd|바람|weather|날씨|FEELS_LIKE|HUMIDITY|WIND_SPEED|PRECIP|CLOUD_COVER/i;
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
  // 같은 물리량은 제공자와 무관하게 같은 라벨로 보인다(기상청 "하늘상태"·외부 null 이름 모두 "하늘").
  const key = metric.metric_key.toUpperCase();
  return WEATHER_LABELS[key] || metric.metric_name?.trim() || '기타 날씨';
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1);
}

function displayUnit(unit: string | null | undefined): string {
  if (unit === 'deg_c') return '°C';
  if (unit === 'deg_f') return '°F';
  if (unit === 'ug/m3') return 'μg/m³';
  if (unit === 'deg') return '°';
  if (unit === 'code' || unit === 'index') return '';
  return unit ?? '';
}

// 같은 물리량의 alias만 묶는다. 체감온도는 실제 기온과 다르고 강수량/확률도 별개다.
const SUMMARY_ALIAS: Record<string, string> = {
  T1H: 'TEMP',
  TMP: 'TEMP',
  T3H: 'TEMP',
  PRECIP_PROB: 'POP',
  PRECIP: 'PCP',
  HUMIDITY: 'REH',
  WIND_SPEED: 'WSD',
};
const SUMMARY_ORDER = [
  'TEMP',
  'TMN',
  'TMX',
  'SKY',
  'PTY',
  'POP',
  'PCP',
  'RN1',
  'FEELS_LIKE',
  'CLOUD_COVER',
  'REH',
  'WSD',
  'PM10',
  'PM25',
];
const PROVIDER_ORDER = [
  'python-kma-api',
  'python-airkorea-api',
  'python-khoa-api',
  'python-krforest-api',
  'python-krex-api',
  'openweathermap',
  'weatherapi',
  'open_meteo',
  'wttr_in',
];
function rank(order: string[], value: string): number {
  const index = order.indexOf(value);
  return index < 0 ? order.length : index;
}
function metricInstant(metric: WeatherMetric): number {
  return Date.parse(
    metric.effective_at ?? metric.valid_at ?? metric.observed_at ?? metric.valid_from ?? '',
  );
}
function summaryKey(metric: WeatherMetric): string {
  const key = metric.metric_key.toUpperCase();
  return SUMMARY_ALIAS[key] ?? key;
}
function canonicalUnit(unit: string | null | undefined): string | null {
  if (unit === 'deg_c' || unit === '°C' || unit === '℃') return 'deg_c';
  if (unit === 'deg_f' || unit === '°F') return 'deg_f';
  if (unit === 'ug/m3' || unit === 'μg/m³') return 'ug/m3';
  return unit ?? null;
}
function isWeatherMetric(metric: WeatherMetric): boolean {
  return (
    Object.hasOwn(WEATHER_LABELS, metric.metric_key.toUpperCase()) ||
    WEATHER_RE.test(metricHaystack(metric))
  );
}
function representativeOrder(a: WeatherMetric, b: WeatherMetric): number {
  // 같은 지표는 기상청 우선(제공자 순서) → 날짜 안의 대표 시각(관측은 최신, 예보는 가장 이른
  // 유효 시각). 외부 제공자의 더 이른 슬롯이 기상청 값을 밀어내지 않는다. 평균/범위로 합치지 않는다.
  const aCurrent = CURRENT_STYLE_RE.test(a.forecast_style);
  const bCurrent = CURRENT_STYLE_RE.test(b.forecast_style);
  if (aCurrent !== bCurrent) return aCurrent ? -1 : 1;
  const direction = aCurrent ? -1 : 1;
  return (
    rank(PROVIDER_ORDER, a.provider ?? '') - rank(PROVIDER_ORDER, b.provider ?? '') ||
    (metricInstant(a) - metricInstant(b)) * direction ||
    a.forecast_style.localeCompare(b.forecast_style) ||
    a.metric_key.localeCompare(b.metric_key) ||
    (a.value_text ?? String(a.value_number)).localeCompare(b.value_text ?? String(b.value_number))
  );
}

// 기상청 자료개방포털의 SKY 코드표. 과거 자료의 2(구름조금)도 보존한다.
// https://data.kma.go.kr/data/rmt/rmtList.do?code=400&pgmNo=570&tabNo=2
const KMA_SKY_LABELS: Record<number, string> = {
  1: '맑음',
  2: '구름조금',
  3: '구름많음',
  4: '흐림',
};
// 기상청 동네예보 PTY(강수형태) 코드표. 5~7은 초단기 전용.
const KMA_PTY_LABELS: Record<number, string> = {
  0: '없음',
  1: '비',
  2: '비/눈',
  3: '눈',
  4: '소나기',
  5: '빗방울',
  6: '빗방울눈날림',
  7: '눈날림',
};
const KMA_CODE_TABLES: Record<string, Record<number, string>> = {
  SKY: KMA_SKY_LABELS,
  PTY: KMA_PTY_LABELS,
};
function formatMetric(metric: WeatherMetric): string | null {
  const text = metric.value_text?.trim();
  // 원문 설명은 보존한다. 알려진 문자열 코드만 숫자 코드와 같은 표로 해석한다.
  const table =
    metric.provider === 'python-kma-api'
      ? KMA_CODE_TABLES[metric.metric_key.toUpperCase()]
      : undefined;
  const code = text ? (/^\d$/.test(text) ? Number(text) : null) : metric.value_number;
  const coded = table && code != null ? table[code] : null;
  const value =
    coded ||
    text ||
    (metric.value_number != null
      ? `${formatNumber(metric.value_number)}${displayUnit(metric.unit)}`
      : null) ||
    metric.severity ||
    null;

  if (!value) return null;
  const suffix = metric.severity && metric.severity !== value ? ` ${metric.severity}` : '';
  return `${metricLabel(metric)} ${value}${suffix}`;
}

interface MetricGroup {
  items: string[];
  /** 실제 표시된 값의 출처만 담는다(잘려나간 값의 출처는 포함하지 않는다). */
  providers: string[];
}

function toGroup(metrics: WeatherMetric[]): MetricGroup {
  const representatives = new Map<string, WeatherMetric>();
  for (const metric of [...metrics].sort(representativeOrder)) {
    // 다른 단위는 변환·병합하지 않는다. 각 단위의 대표 사실을 따로 유지한다.
    const key = JSON.stringify([summaryKey(metric), canonicalUnit(metric.unit)]);
    if (!representatives.has(key) && formatMetric(metric) != null) representatives.set(key, metric);
  }
  const shown = [...representatives.values()]
    .sort(
      (a, b) =>
        rank(SUMMARY_ORDER, summaryKey(a)) - rank(SUMMARY_ORDER, summaryKey(b)) ||
        summaryKey(a).localeCompare(summaryKey(b)) ||
        (canonicalUnit(a.unit) ?? '').localeCompare(canonicalUnit(b.unit) ?? ''),
    )
    .map((metric) => ({ metric, text: formatMetric(metric)! }))
    .slice(0, 8);
  return {
    items: shown.map((entry) => entry.text),
    providers: Array.from(
      new Set(
        shown
          .map((entry) => providerLabel(entry.metric.provider))
          .filter((value): value is string => value != null),
      ),
    ),
  };
}

/** 세 구간 요약(ADR-077 Map 경로의 지난 일자) — 아침·점심·저녁 순. */
const DAILY_SUMMARY_STYLE = 'daily_summary';
const DAILY_SLOTS: ReadonlyArray<[string, string]> = [
  ['morning', '아침'],
  ['noon', '점심'],
  ['evening', '저녁'],
];

function slotValue(metrics: WeatherMetric[], key: string): number | null {
  const metric = metrics.find((item) => item.metric_key === key);
  return metric?.value_number ?? null;
}

function toDailyGroup(metrics: WeatherMetric[]): MetricGroup {
  const items: string[] = [];
  for (const [slot, slotLabel] of DAILY_SLOTS) {
    const slotMetrics = metrics.filter((metric) => metric.timeline_bucket === slot);
    if (slotMetrics.length === 0) continue;
    const min = slotValue(slotMetrics, 'SLOT_TEMP_MIN');
    const max = slotValue(slotMetrics, 'SLOT_TEMP_MAX');
    const humidity = slotValue(slotMetrics, 'SLOT_HUMIDITY_AVG');
    const precip = slotValue(slotMetrics, 'SLOT_PRECIP_SUM');
    const parts: string[] = [];
    if (min != null && max != null) parts.push(`${formatNumber(min)}~${formatNumber(max)}°C`);
    else if (min != null || max != null) parts.push(`${formatNumber((min ?? max) as number)}°C`);
    if (humidity != null) parts.push(`습도 ${formatNumber(humidity)}%`);
    if (precip != null) parts.push(`강수 ${formatNumber(precip)}mm`);
    if (parts.length > 0) items.push(`${slotLabel} ${parts.join(' ')}`);
  }
  return {
    items,
    providers: Array.from(
      new Set(
        metrics
          .map((metric) => providerLabel(metric.provider))
          .filter((value): value is string => value != null),
      ),
    ),
  };
}

function pickMetrics(metrics: WeatherMetric[], date: string) {
  const sameDate = metrics.filter((metric) => metricDate(metric) === date);
  const daily = sameDate.filter((metric) => metric.forecast_style === DAILY_SUMMARY_STYLE);
  const matched = sameDate.filter((metric) => metric.forecast_style !== DAILY_SUMMARY_STYLE);
  const dust = matched.filter((metric) => DUST_RE.test(metricHaystack(metric)));
  const nonDust = matched.filter((metric) => !DUST_RE.test(metricHaystack(metric)));
  const current = nonDust.filter(
    (metric) => CURRENT_STYLE_RE.test(metric.forecast_style) && isWeatherMetric(metric),
  );
  const forecast = nonDust.filter(
    (metric) =>
      !CURRENT_STYLE_RE.test(metric.forecast_style) &&
      (FORECAST_STYLE_RE.test(metric.forecast_style) || isWeatherMetric(metric)),
  );

  return {
    current: toGroup(current),
    forecast: toGroup(forecast),
    dust: toGroup(dust),
    daily: toDailyGroup(daily),
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
      { key: 'current', label: '현재', icon: CloudSun, ...picked.current },
      { key: 'forecast', label: '예보', icon: CloudSun, ...picked.forecast },
      { key: 'dust', label: '미세먼지', icon: Wind, ...picked.dust },
      { key: 'daily', label: '시간대별', icon: CloudSun, ...picked.daily },
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
        className={compact ? 'px-0 py-1' : 'rounded-sm bg-surface-soft px-3 py-2'}
        aria-label={label}
        data-testid="trip-weather-status"
      >
        <p className="text-xs text-muted">{statusText}</p>
      </section>
    );
  }

  return (
    <section
      className={compact ? 'space-y-1 px-0 py-1' : 'space-y-2 rounded-sm bg-surface-soft px-3 py-2'}
      aria-label={label}
      data-testid="trip-weather-summary"
    >
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs font-semibold text-muted">{label}</p>
        {card.is_stale && (
          <span
            className="rounded-sm border border-hairline px-1.5 py-0.5 text-xs text-muted"
            title="일부 날씨 정보의 업데이트가 지연되었습니다."
            role="status"
          >
            오래된 정보 포함
          </span>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {groups.map((group) => {
          const Icon = group.icon;
          return (
            <span
              key={group.key}
              className="inline-flex max-w-full flex-wrap items-center gap-1 rounded-sm bg-canvas px-2 py-1 text-xs text-body"
            >
              <Icon className="h-3 w-3 shrink-0 text-primary" aria-hidden="true" />
              <span className="shrink-0 font-semibold text-ink">{group.label}</span>
              <span className="flex min-w-0 flex-wrap gap-x-2 gap-y-1">
                {withOccurrenceKeys(group.items, (item) => item).map(({ item, key }) => (
                  <span key={key} data-testid="weather-summary-metric">
                    {item}
                  </span>
                ))}
              </span>
              {group.providers.length > 0 && (
                <span
                  className="min-w-0 break-words text-muted"
                  title={`출처: ${group.providers.join(', ')}`}
                >
                  ({group.providers.join(', ')})
                </span>
              )}
            </span>
          );
        })}
      </div>
    </section>
  );
}
