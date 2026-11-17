/**
 * 장소 날씨 카드(`GET /trips/{id}/pois/{poi}/weather`의 평탄 metric 목록) → 화면용 요약.
 *
 * 장소 목록의 날씨 배지(현재 아이콘·기온 + 오늘 최고/최저)와 날씨 팝업(시간별 띠·일별 최고/최저·
 * 강수확률·특보), 지도 마커 옆 작은 날씨 아이콘이 모두 이 모듈을 쓴다 — 같은 사실이 표면마다 다른
 * 아이콘·숫자로 보이지 않게 한 곳에 둔다.
 *
 * 규칙:
 * - 같은 시각·같은 물리량을 여러 제공자가 주면 제공자 우선순위(기상청 우선)로 하나만 고른다.
 *   평균·보간하지 않는다(없는 값을 지어내지 않는다).
 * - 상태(맑음/흐림/비…)는 기상청 PTY(강수형태) > SKY(하늘상태) > 외부 제공자 날씨 코드 > 운량 순으로
 *   판단한다. 판단할 근거가 없으면 `unknown`이다.
 * - 기온은 섭씨 단위(`deg_c`/`℃`/`°C`)만 쓴다. 다른 단위는 변환하지 않고 버린다.
 */
import type { FeatureWeatherCard, WeatherMetric } from '@pinvi/schemas';

export type WeatherConditionKind =
  | 'clear'
  | 'partly'
  | 'cloudy'
  | 'overcast'
  | 'rain'
  | 'shower'
  | 'sleet'
  | 'snow'
  | 'thunder'
  | 'fog'
  | 'unknown';

export const CONDITION_LABELS: Record<WeatherConditionKind, string> = {
  clear: '맑음',
  partly: '구름조금',
  cloudy: '구름많음',
  overcast: '흐림',
  rain: '비',
  shower: '소나기',
  sleet: '비/눈',
  snow: '눈',
  thunder: '뇌우',
  fog: '안개',
  unknown: '날씨 정보 없음',
};

export function conditionLabel(condition: WeatherConditionKind): string {
  return CONDITION_LABELS[condition];
}

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
const KMA = 'python-kma-api';
const HOUR_MS = 3_600_000;
const KST_OFFSET_MS = 9 * HOUR_MS;
const CURRENT_STYLES = new Set(['nowcast', 'observed']);
const FORECAST_STYLES = new Set(['ultra_short', 'short', 'mid']);
const TEMP_KEYS = new Set(['T1H', 'TMP', 'TEMP', 'T3H']);
const CELSIUS_UNITS = new Set(['deg_c', '℃', '°C']);
/** 강수 상태의 심각도 순서 — 하루 대표 상태를 고를 때 더 나쁜 쪽을 보인다. */
const PRECIP_SEVERITY: WeatherConditionKind[] = ['thunder', 'snow', 'sleet', 'rain', 'shower'];

function providerRank(provider: string | null | undefined): number {
  const index = PROVIDER_ORDER.indexOf(provider ?? '');
  return index < 0 ? PROVIDER_ORDER.length : index;
}

export function metricTime(metric: WeatherMetric): number | null {
  const instant = metric.valid_at ?? metric.observed_at ?? metric.valid_from ?? null;
  if (!instant) return null;
  const value = Date.parse(instant);
  return Number.isNaN(value) ? null : value;
}

/** KST 날짜 키(`YYYY-MM-DD`). */
export function kstDateKey(epochMs: number): string {
  return new Date(epochMs + KST_OFFSET_MS).toISOString().slice(0, 10);
}

/** KST 시(0~23). */
export function kstHour(epochMs: number): number {
  return new Date(epochMs + KST_OFFSET_MS).getUTCHours();
}

function isNight(epochMs: number): boolean {
  const hour = kstHour(epochMs);
  return hour < 6 || hour >= 18;
}

function numberOf(metric: WeatherMetric | undefined): number | null {
  if (!metric) return null;
  if (metric.value_number != null && Number.isFinite(metric.value_number))
    return metric.value_number;
  const text = metric.value_text?.trim();
  if (text && /^-?\d+(\.\d+)?$/.test(text)) return Number(text);
  return null;
}

function tempOf(metric: WeatherMetric | undefined): number | null {
  if (!metric) return null;
  if (metric.unit && !CELSIUS_UNITS.has(metric.unit)) return null;
  return numberOf(metric);
}

/** 같은 키 후보 중 제공자 우선순위가 가장 높은 것 하나. */
function best(candidates: WeatherMetric[]): WeatherMetric | undefined {
  let chosen: WeatherMetric | undefined;
  for (const metric of candidates) {
    if (!chosen || providerRank(metric.provider) < providerRank(chosen.provider)) chosen = metric;
  }
  return chosen;
}

function fromKmaPty(code: number | null): WeatherConditionKind | null {
  switch (code) {
    case 1:
    case 5:
      return 'rain';
    case 2:
    case 6:
      return 'sleet';
    case 3:
    case 7:
      return 'snow';
    case 4:
      return 'shower';
    default:
      return null;
  }
}

function fromKmaSky(code: number | null): WeatherConditionKind | null {
  switch (code) {
    case 1:
      return 'clear';
    case 2:
      return 'partly';
    case 3:
      return 'cloudy';
    case 4:
      return 'overcast';
    default:
      return null;
  }
}

/** 기상청 중기예보처럼 하늘·강수가 문장으로 오는 경우("구름많고 비", "흐리고 눈"). */
export function conditionFromText(text: string | null | undefined): WeatherConditionKind | null {
  const value = text?.trim();
  if (!value) return null;
  if (/뇌우|낙뢰|천둥/.test(value)) return 'thunder';
  if (/비\/눈|눈\/비|진눈깨비/.test(value)) return 'sleet';
  if (/소나기/.test(value)) return 'shower';
  if (/눈/.test(value)) return 'snow';
  if (/비|빗방울/.test(value)) return 'rain';
  if (/안개|박무|연무/.test(value)) return 'fog';
  if (/흐림|흐리/.test(value)) return 'overcast';
  if (/구름많/.test(value)) return 'cloudy';
  if (/구름조금/.test(value)) return 'partly';
  if (/맑/.test(value)) return 'clear';
  return null;
}

/** OpenWeatherMap condition id. https://openweathermap.org/weather-conditions */
function fromOpenWeatherMap(code: number): WeatherConditionKind | null {
  if (code >= 200 && code < 300) return 'thunder';
  if (code >= 300 && code < 400) return 'shower';
  if (code === 511 || (code >= 611 && code <= 616)) return 'sleet';
  if (code >= 500 && code < 600) return code >= 520 ? 'shower' : 'rain';
  if (code >= 600 && code < 700) return 'snow';
  if (code >= 700 && code < 800) return 'fog';
  if (code === 800) return 'clear';
  if (code === 801) return 'partly';
  if (code === 802) return 'cloudy';
  if (code === 803 || code === 804) return 'overcast';
  return null;
}

/** WeatherAPI.com condition code. https://www.weatherapi.com/docs/weather_conditions.json */
function fromWeatherApi(code: number): WeatherConditionKind | null {
  if (code === 1000) return 'clear';
  if (code === 1003) return 'partly';
  if (code === 1006) return 'cloudy';
  if (code === 1009) return 'overcast';
  if (code === 1030 || code === 1135 || code === 1147) return 'fog';
  if (code === 1087 || (code >= 1273 && code <= 1282)) return 'thunder';
  if ([1069, 1072, 1168, 1171, 1198, 1201, 1204, 1207, 1237, 1249, 1252, 1261, 1264].includes(code))
    return 'sleet';
  if (code === 1066 || code === 1114 || code === 1117 || (code >= 1210 && code <= 1225))
    return 'snow';
  if (code === 1255 || code === 1258) return 'snow';
  if (code === 1240 || code === 1243 || code === 1246) return 'shower';
  if (code === 1063 || (code >= 1150 && code <= 1195)) return 'rain';
  return null;
}

function fromWeatherCode(metric: WeatherMetric | undefined): WeatherConditionKind | null {
  const code = numberOf(metric);
  if (code == null || !metric) return conditionFromText(metric?.value_text);
  if (metric.provider === 'openweathermap') return fromOpenWeatherMap(code);
  if (metric.provider === 'weatherapi') return fromWeatherApi(code);
  return null;
}

function fromCloudCover(metric: WeatherMetric | undefined): WeatherConditionKind | null {
  const value = numberOf(metric);
  if (value == null || metric?.unit !== '%') return null;
  if (value <= 20) return 'clear';
  if (value <= 50) return 'partly';
  if (value <= 85) return 'cloudy';
  return 'overcast';
}

/** 한 시각 슬롯의 metric 묶음 → 상태. */
function conditionOf(byKey: Map<string, WeatherMetric[]>): WeatherConditionKind | null {
  const pty = best((byKey.get('PTY') ?? []).filter((metric) => metric.provider === KMA));
  const precip = fromKmaPty(numberOf(pty));
  if (precip) return precip;
  const sky = best(byKey.get('SKY') ?? []);
  const skyKind =
    sky?.provider === KMA
      ? (fromKmaSky(numberOf(sky)) ?? conditionFromText(sky.value_text))
      : conditionFromText(sky?.value_text);
  if (skyKind) return skyKind;
  const codes = [...(byKey.get('WEATHER_CODE') ?? [])].sort(
    (a, b) => providerRank(a.provider) - providerRank(b.provider),
  );
  for (const code of codes) {
    const kind = fromWeatherCode(code);
    if (kind) return kind;
  }
  return fromCloudCover(best(byKey.get('CLOUD_COVER') ?? []));
}

interface Slot {
  at: number;
  byKey: Map<string, WeatherMetric[]>;
}

function addToSlot(slots: Map<number, Slot>, at: number, metric: WeatherMetric) {
  let slot = slots.get(at);
  if (!slot) {
    slot = { at, byKey: new Map() };
    slots.set(at, slot);
  }
  const key = TEMP_KEYS.has(metric.metric_key.toUpperCase())
    ? 'TEMP'
    : metric.metric_key.toUpperCase();
  const list = slot.byKey.get(key);
  if (list) list.push(metric);
  else slot.byKey.set(key, [metric]);
}

/** 예보 metric을 정시 슬롯으로 묶는다. */
function forecastSlots(metrics: WeatherMetric[]): Slot[] {
  const slots = new Map<number, Slot>();
  for (const metric of metrics) {
    if (!FORECAST_STYLES.has(metric.forecast_style)) continue;
    const at = metricTime(metric);
    if (at == null) continue;
    addToSlot(slots, Math.floor(at / HOUR_MS) * HOUR_MS, metric);
  }
  return [...slots.values()].sort((a, b) => a.at - b.at);
}

export interface HourlyWeather {
  at: number;
  temp: number | null;
  condition: WeatherConditionKind;
  night: boolean;
  /** 강수확률(%) */
  pop: number | null;
  /** 강수량(mm) */
  precip: number | null;
}

function slotToHourly(slot: Slot): HourlyWeather {
  return {
    at: slot.at,
    temp: tempOf(best(slot.byKey.get('TEMP') ?? [])),
    condition: conditionOf(slot.byKey) ?? 'unknown',
    night: isNight(slot.at),
    pop: numberOf(best(slot.byKey.get('POP') ?? [])),
    precip: numberOf(best([...(slot.byKey.get('PCP') ?? []), ...(slot.byKey.get('RN1') ?? [])])),
  };
}

/** 지금 시각부터 `hours`시간의 시간별 예보(기온이 있는 슬롯만). */
export function hourlyForecast(
  card: FeatureWeatherCard | null | undefined,
  now: number,
  hours = 24,
): HourlyWeather[] {
  if (!card) return [];
  const from = Math.floor(now / HOUR_MS) * HOUR_MS;
  const to = from + hours * HOUR_MS;
  return forecastSlots(card.metrics)
    .filter((slot) => slot.at >= from && slot.at <= to)
    .map(slotToHourly)
    .filter((hour) => hour.temp != null);
}

export interface CurrentWeather {
  temp: number | null;
  condition: WeatherConditionKind;
  night: boolean;
  feelsLike: number | null;
  humidity: number | null;
  windSpeed: number | null;
  pop: number | null;
  observedAt: number | null;
  provider: string | null;
}

/** 관측(실황) 우선, 없으면 가장 가까운 예보 슬롯으로 현재 날씨를 만든다. */
export function currentWeather(
  card: FeatureWeatherCard | null | undefined,
  now: number,
): CurrentWeather | null {
  if (!card || card.metrics.length === 0) return null;
  const recent = card.metrics.filter((metric) => {
    if (!CURRENT_STYLES.has(metric.forecast_style)) return false;
    const at = metricTime(metric);
    return at != null && at <= now + HOUR_MS && at >= now - 3 * HOUR_MS;
  });
  const observed = new Map<string, WeatherMetric[]>();
  for (const metric of recent) {
    const key = TEMP_KEYS.has(metric.metric_key.toUpperCase())
      ? 'TEMP'
      : metric.metric_key.toUpperCase();
    const list = observed.get(key);
    if (list) list.push(metric);
    else observed.set(key, [metric]);
  }
  // 같은 제공자 안에서는 실황(nowcast)이 관측(observed)보다, 최신이 오래된 것보다 앞선다.
  const pick = (key: string): WeatherMetric | undefined =>
    [...(observed.get(key) ?? [])].sort(
      (a, b) =>
        providerRank(a.provider) - providerRank(b.provider) ||
        Number(b.forecast_style === 'nowcast') - Number(a.forecast_style === 'nowcast') ||
        (metricTime(b) ?? 0) - (metricTime(a) ?? 0),
    )[0];
  const nextSlot = forecastSlots(card.metrics).find((slot) => slot.at >= now - HOUR_MS);
  const next = nextSlot ? slotToHourly(nextSlot) : null;

  const tempMetric = pick('TEMP');
  const temp = tempOf(tempMetric) ?? next?.temp ?? null;
  const precipNow = fromKmaPty(numberOf(pick('PTY')));
  const condition =
    precipNow ??
    (next && next.condition !== 'unknown' ? next.condition : null) ??
    conditionOf(observed) ??
    'unknown';
  if (temp == null && condition === 'unknown') return null;
  return {
    temp,
    condition,
    night: isNight(now),
    feelsLike: tempOf(pick('FEELS_LIKE')),
    humidity: numberOf(pick('REH')),
    windSpeed: numberOf(pick('WSD')),
    pop: next?.pop ?? null,
    observedAt: tempMetric ? metricTime(tempMetric) : null,
    provider: tempMetric?.provider ?? null,
  };
}

export interface DailyWeather {
  date: string;
  max: number | null;
  min: number | null;
  popMax: number | null;
  condition: WeatherConditionKind;
}

/** 하루 대표 상태 — 낮(06~21시)에 강수가 있으면 가장 심한 강수, 없으면 가장 잦은 하늘 상태. */
function representative(hours: HourlyWeather[]): WeatherConditionKind {
  const daytime = hours.filter((hour) => {
    const h = kstHour(hour.at);
    return h >= 6 && h <= 21;
  });
  const pool = daytime.length > 0 ? daytime : hours;
  for (const kind of PRECIP_SEVERITY) {
    if (pool.some((hour) => hour.condition === kind)) return kind;
  }
  const counts = new Map<WeatherConditionKind, number>();
  for (const hour of pool) {
    if (hour.condition === 'unknown') continue;
    counts.set(hour.condition, (counts.get(hour.condition) ?? 0) + 1);
  }
  let chosen: WeatherConditionKind = 'unknown';
  let max = 0;
  for (const [kind, count] of counts) {
    if (count > max) {
      chosen = kind;
      max = count;
    }
  }
  return chosen;
}

/** 오늘(KST)부터 날짜별 최고/최저·최대 강수확률·대표 상태. 기상청 TMX/TMN이 있으면 그 값을 쓴다. */
export function dailyForecast(
  card: FeatureWeatherCard | null | undefined,
  now: number,
  days = 7,
): DailyWeather[] {
  if (!card) return [];
  const today = kstDateKey(now);
  const byDate = new Map<
    string,
    { hours: HourlyWeather[]; tmx: WeatherMetric[]; tmn: WeatherMetric[]; temps: number[] }
  >();
  const bucket = (date: string) => {
    let entry = byDate.get(date);
    if (!entry) {
      entry = { hours: [], tmx: [], tmn: [], temps: [] };
      byDate.set(date, entry);
    }
    return entry;
  };
  for (const slot of forecastSlots(card.metrics)) {
    const date = kstDateKey(slot.at);
    if (date < today) continue;
    const entry = bucket(date);
    const hourly = slotToHourly(slot);
    entry.hours.push(hourly);
    if (hourly.temp != null) entry.temps.push(hourly.temp);
    entry.tmx.push(...(slot.byKey.get('TMX') ?? []));
    entry.tmn.push(...(slot.byKey.get('TMN') ?? []));
  }
  // 오늘 이미 지난 시각의 관측 기온도 오늘 최고/최저에 넣는다.
  for (const metric of card.metrics) {
    if (!CURRENT_STYLES.has(metric.forecast_style)) continue;
    if (!TEMP_KEYS.has(metric.metric_key.toUpperCase())) continue;
    const at = metricTime(metric);
    const temp = tempOf(metric);
    if (at == null || temp == null || kstDateKey(at) !== today) continue;
    bucket(today).temps.push(temp);
  }
  return [...byDate.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(0, days)
    .map(([date, entry]) => {
      const tmx = tempOf(best(entry.tmx));
      const tmn = tempOf(best(entry.tmn));
      const pops = entry.hours.map((hour) => hour.pop).filter((pop): pop is number => pop != null);
      return {
        date,
        max: tmx ?? (entry.temps.length > 0 ? Math.max(...entry.temps) : null),
        min: tmn ?? (entry.temps.length > 0 ? Math.min(...entry.temps) : null),
        popMax: pops.length > 0 ? Math.max(...pops) : null,
        condition: representative(entry.hours),
      };
    })
    .filter((day) => day.max != null || day.min != null || day.condition !== 'unknown');
}

/** 오늘(KST) 최고/최저 — 오늘 남은 예보 + 이미 지난 관측 기온. 오늘 기온이 하나도 없으면 null. */
export function todayRange(
  card: FeatureWeatherCard | null | undefined,
  now: number,
): { max: number; min: number } | null {
  const today = dailyForecast(card, now, 1)[0];
  if (!today || today.date !== kstDateKey(now) || today.max == null || today.min == null)
    return null;
  return { max: today.max, min: today.min };
}

export interface WeatherAlert {
  title: string;
  severity: string | null;
  from: number | null;
  until: number | null;
  provider: string | null;
}

/** 지금 유효한 기상 특보(advisory). 만료(`valid_until` 경과)된 것은 뺀다. */
export function activeAlerts(
  card: FeatureWeatherCard | null | undefined,
  now: number,
): WeatherAlert[] {
  if (!card) return [];
  const seen = new Set<string>();
  const alerts: WeatherAlert[] = [];
  for (const metric of card.metrics) {
    if (metric.forecast_style !== 'advisory') continue;
    const until = metric.valid_until ? Date.parse(metric.valid_until) : null;
    if (until != null && !Number.isNaN(until) && until < now) continue;
    const title =
      metric.value_text?.trim() ||
      metric.metric_name?.trim() ||
      metric.metric_key.trim() ||
      '기상 특보';
    const key = `${title}|${metric.severity ?? ''}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const from = metric.valid_from ? Date.parse(metric.valid_from) : null;
    alerts.push({
      title,
      severity: metric.severity ?? null,
      from: from != null && !Number.isNaN(from) ? from : null,
      until: until != null && !Number.isNaN(until) ? until : null,
      provider: metric.provider ?? null,
    });
  }
  return alerts;
}

export function formatTemp(value: number | null | undefined): string {
  if (value == null) return '-';
  return `${Math.round(value)}°`;
}

/** 날씨 상태 → lucide 그림 이름(웹·모바일 공용). 해·구름이 섞인 상태만 밤 그림이 따로 있다. */
const WEATHER_DAY_GLYPHS = {
  clear: 'Sun',
  partly: 'CloudSun',
  cloudy: 'Cloud',
  overcast: 'Cloudy',
  rain: 'CloudRain',
  shower: 'CloudDrizzle',
  sleet: 'CloudHail',
  snow: 'CloudSnow',
  thunder: 'CloudLightning',
  fog: 'CloudFog',
  unknown: 'Thermometer',
} as const satisfies Record<WeatherConditionKind, string>;

const WEATHER_NIGHT_GLYPHS = {
  clear: 'Moon',
  partly: 'CloudMoon',
} as const satisfies Partial<Record<WeatherConditionKind, string>>;

/** 날씨 아이콘으로 쓰는 lucide 그림 이름. */
export type WeatherGlyphName =
  | (typeof WEATHER_DAY_GLYPHS)[WeatherConditionKind]
  | (typeof WEATHER_NIGHT_GLYPHS)[keyof typeof WEATHER_NIGHT_GLYPHS];

/** 날씨 아이콘에 쓰는 모든 lucide 그림 이름(각 앱의 그림 표가 빠짐없이 갖췄는지 시험이 본다). */
export const WEATHER_GLYPH_NAMES: readonly WeatherGlyphName[] = [
  ...new Set<WeatherGlyphName>([
    ...Object.values(WEATHER_DAY_GLYPHS),
    ...Object.values(WEATHER_NIGHT_GLYPHS),
  ]),
];

export function weatherGlyphName(condition: WeatherConditionKind, night = false): WeatherGlyphName {
  if (night && (condition === 'clear' || condition === 'partly'))
    return WEATHER_NIGHT_GLYPHS[condition];
  return WEATHER_DAY_GLYPHS[condition];
}

/**
 * 상태별 색의 의미 — 맑음은 따뜻한 색(warning), 강수는 primary, 뇌우는 error, 그 밖은 muted.
 * 웹은 토큰 class(`text-*`), 모바일은 같은 의미의 hex로 바꿔 쓴다.
 */
export type WeatherTone = 'warning' | 'primary' | 'error' | 'muted';

export const WEATHER_TONES: Record<WeatherConditionKind, WeatherTone> = {
  clear: 'warning',
  partly: 'warning',
  cloudy: 'muted',
  overcast: 'muted',
  rain: 'primary',
  shower: 'primary',
  sleet: 'primary',
  snow: 'primary',
  thunder: 'error',
  fog: 'muted',
  unknown: 'muted',
};
