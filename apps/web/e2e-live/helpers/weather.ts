/**
 * Shared utilities for the weather (WX) live specs.
 * UI text/selectors cite PinVi main 620b6046:
 *  - apps/web/components/trips/TripWeatherSummary.tsx (status texts, group labels, testids)
 *  - apps/web/components/trips/TripDayHeader.tsx (rise/set testids + #615 pending wording)
 *  - apps/web/components/trips/TripDetail.tsx (day tab role=tab, aria-label `${n}일차`, 날짜 날씨 label)
 *  - apps/web/components/trips/TripPoiList.tsx (trip-poi-list, 장소 날씨 label)
 *  - packages/schemas/src/trip.ts (TripViewDay/weather schema)
 */
import { expect, test, type Locator, type Page, type Response } from '@playwright/test';
import { apiBaseURL, openPanel, deleteAllE2eTrips, deleteTrip, e2ePrefix, requireEnv, waitForRequest } from './live';

export const TEXT = {
  noData: '이 날짜의 날씨 정보가 없습니다.',
  unavailable: '날씨 서비스를 일시적으로 사용할 수 없습니다.',
  retired: '장소 상태가 종료되어 날씨를 확인할 수 없습니다.',
  suppressed: '비공개 장소는 날씨를 확인할 수 없습니다.',
  missing: '장소 정보를 찾을 수 없어 날씨를 확인할 수 없습니다.',
  dayLabel: '날짜 날씨',
  poiLabel: '장소 날씨',
  group: { current: '현재', forecast: '예보', dust: '미세먼지', daily: '시간대별' },
  risePending: {
    pending_coord: '좌표가 있는 장소를 추가하면 일출·일몰을 표시합니다',
    pending_date: '날짜를 정하면 일출·일몰을 표시합니다',
    pending_fetch: '일출·일몰 준비 중',
  },
  risePendingReadOnly: { pending_fetch: '일출·일몰 준비 중', other: '일출·일몰 정보 없음' },
  sharedHeader: '공유된 여행 · 읽기 전용',
} as const;

export const STATUS_TEXT: Record<string, string> = {
  no_data: TEXT.noData,
  unavailable: TEXT.unavailable,
  retired: TEXT.retired,
  suppressed: TEXT.suppressed,
  missing: TEXT.missing,
};

/** Weather comes through Map REST (PINVI_KOR_TRAVEL_MAP_WEATHER_ENABLED) — strict Map-path assertions when '1'. */
export const WEATHER_VIA_MAP = (process.env.PINVI_E2E_WEATHER_VIA_MAP ?? '1') === '1';
export const TRIP_VIEW_BUDGET_MS = Number(process.env.PINVI_E2E_TRIP_VIEW_BUDGET_MS ?? '6000');
export const SEED_SUN_TRIP_TITLE = process.env.PINVI_E2E_SEED_SUN_TRIP ?? '[e2e-seed] weather-sun';

export const TEMP_RANGE = { min: -30, max: 45 } as const;
export const TEMP_KEY_RE = /^(T1H|TMP|TMN|TMX|T3H|TEMP|FEELS_LIKE|SLOT_TEMP_(MIN|MAX|AVG))$/i;
export const TEMP_UNIT_RE = /deg_c|℃|°C/i;
export const HUMIDITY_KEY_RE = /^(REH|HUMIDITY|SLOT_HUMIDITY_AVG)$/i;
export const POP_KEY_RE = /^(POP|PRECIP_PROB)$/i;
export const PROVIDER_LABELS = [
  '기상청',
  '환경공단',
  '국립해양조사원',
  '산림청',
  '한국도로공사',
  'OpenWeatherMap',
  'WeatherAPI',
  'Open-Meteo',
  'wttr.in',
];

// ───────────────────────────── dates (KST) ─────────────────────────────
const KST_DATE = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

export function kstToday(): string {
  return KST_DATE.format(new Date()); // en-CA → YYYY-MM-DD
}

export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00.000Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export const D = (offset: number) => addDays(kstToday(), offset);

export function wxTitle(id: string): string {
  return `${e2ePrefix} ${id} ${Date.now().toString(36)}`;
}

// ───────────────────────────── trip view JSON ─────────────────────────────
export interface WxMetric {
  metric_key: string;
  metric_name?: string | null;
  forecast_style: string;
  value_number?: number | null;
  value_text?: string | null;
  unit?: string | null;
  provider?: string | null;
  severity?: string | null;
  effective_at?: string | null;
  valid_at?: string | null;
  observed_at?: string | null;
  valid_from?: string | null;
  timeline_bucket?: string | null;
}
export interface WxCard {
  asof: string;
  latest_at: string | null;
  is_stale: boolean;
  source_styles: string[];
  metrics: WxMetric[];
}
export type WxResolution = { state: 'found'; card_key: string } | { state: string };

/** `card_key` of a `found` resolution; throws with the actual state otherwise (contract invariant). */
export function cardKeyOf(res: WxResolution | undefined): string {
  if (!res || !('card_key' in res) || res.state !== 'found') {
    throw new Error(`weather resolution 이 found 가 아니다: ${res?.state ?? 'undefined'}`);
  }
  return res.card_key;
}
export interface WxPoi {
  poi_id: string;
  feature_id: string | null;
  title: string | null;
  feature: Record<string, unknown>;
  created_at: string;
  rise_set: { status: string } | null;
}
export interface WxDay {
  day_index: number;
  date: string | null;
  effective_date: string | null;
  rise_set: {
    status: string;
    sunrise_at: string | null;
    sunset_at: string | null;
    locdate?: string | null;
  } | null;
  rise_set_reference: string | null;
  weather_cards: Record<string, WxCard>;
  weather_by_feature_id: Record<string, WxResolution>;
  pois: WxPoi[];
}
export interface WxTripView {
  trip: { trip_id: string; title: string; start_date: string | null; end_date: string | null };
  days: WxDay[];
}

export function tripViewPattern(tripId: string): RegExp {
  return new RegExp(`/trips/${tripId}(\\?|$)`);
}

async function unwrap(page: Page, tripId: string, resPromise: Promise<Response>) {
  const res = await resPromise;
  expect(res.status(), 'GET /trips/{id} 는 200 이어야 한다').toBe(200);
  let body: ({ data?: WxTripView } & WxTripView) | null = null;
  try {
    body = (await res.json()) as { data?: WxTripView } & WxTripView;
  } catch {
    // The page navigated/reloaded after this response (body discarded) — read the same trip view
    // with the page's cookies instead. Same endpoint, same data; only the timing differs.
    const api = await apiBaseURL(page);
    const again = await page.context().request.get(`${api}/trips/${tripId}`);
    expect(again.status(), 'GET /trips/{id} (re-read)').toBe(200);
    body = (await again.json()) as { data?: WxTripView } & WxTripView;
  }
  return (body.data ?? body) as WxTripView;
}

/** Navigate to /trips/{id} and capture the trip view JSON the page itself requested (no route mocks). */
export async function loadTripView(page: Page, tripId: string): Promise<WxTripView> {
  const pending = waitForRequest(page, tripViewPattern(tripId));
  await page.goto(`/trips/${tripId}`);
  return unwrap(page, tripId, pending);
}

export async function reloadTripView(page: Page, tripId: string): Promise<WxTripView> {
  const pending = waitForRequest(page, tripViewPattern(tripId));
  await page.reload();
  return unwrap(page, tripId, pending);
}

export function dayOf(view: WxTripView, dayIndex: number): WxDay {
  const day = view.days.find((d) => d.day_index === dayIndex);
  if (!day) throw new Error(`trip view 에 ${dayIndex}일차가 없다`);
  return day;
}

export function poiCoord(poi: WxPoi): { lon: number; lat: number } | null {
  const f = poi.feature as Record<string, unknown>;
  const coord = (f.coord ?? f.coordinate ?? f.location) as Record<string, unknown> | undefined;
  const pick = (o: Record<string, unknown> | undefined) => {
    if (!o) return null;
    const lon = Number(o.lon ?? o.longitude);
    const lat = Number(o.lat ?? o.latitude);
    return Number.isFinite(lon) && Number.isFinite(lat) ? { lon, lat } : null;
  };
  return pick(coord) ?? pick(f);
}

export function poiName(poi: WxPoi): string {
  const f = poi.feature as Record<string, unknown>;
  return String(poi.title ?? f.name ?? f.title ?? '장소');
}

export function centroid(coords: { lon: number; lat: number }[]) {
  const n = coords.length;
  return {
    lon: coords.reduce((s, c) => s + c.lon, 0) / n,
    lat: coords.reduce((s, c) => s + c.lat, 0) / n,
  };
}

export function metricsForDate(card: WxCard, isoDate: string): WxMetric[] {
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
  return card.metrics.filter((m) => {
    const inst = m.effective_at ?? m.valid_at ?? m.observed_at ?? m.valid_from ?? null;
    if (!inst) return false;
    const t = new Date(inst);
    return !Number.isNaN(t.getTime()) && fmt.format(t) === isoDate;
  });
}

export function numericValues(metrics: WxMetric[], keyRe: RegExp, unitRe?: RegExp): number[] {
  return metrics
    .filter(
      (m) =>
        typeof m.value_number === 'number' &&
        (keyRe.test(m.metric_key) || (unitRe != null && unitRe.test(m.unit ?? ''))),
    )
    .map((m) => m.value_number as number);
}

export function tempsInUiText(text: string): number[] {
  const out: number[] = [];
  const re = /(-?\d+(?:\.\d+)?)\s*(?:~\s*(-?\d+(?:\.\d+)?)\s*)?(deg_c|℃|°C)/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    out.push(Number(m[1]));
    if (m[2] != null) out.push(Number(m[2]));
  }
  return out;
}

// ───────────────────────────── UI locators ─────────────────────────────
/** Click the day tab and return the surrounding <article> (TripDetail day row; the active body renders inside it). */
export async function openDay(page: Page, dayIndex: number): Promise<Locator> {
  await openPanel(page); // mobile: day tabs live in the drawer
  const tab = page.getByRole('tab', { name: `${dayIndex}일차`, exact: true });
  await expect(tab).toBeVisible();
  await tab.click();
  await expect(tab).toHaveAttribute('aria-selected', 'true');
  return tab.locator('xpath=ancestor::article[1]');
}

/** Shared (read-only) view: tabs are plain buttons role=tab with text `${n}일차`; the header is a sibling, not inside an article. */
export async function openSharedDay(page: Page, dayIndex: number): Promise<void> {
  const tab = page.getByRole('tab', { name: `${dayIndex}일차` });
  await expect(tab).toBeVisible();
  await tab.click();
  await expect(tab).toHaveAttribute('aria-selected', 'true');
}

export const daySection = (scope: Locator | Page) => scope.getByLabel(TEXT.dayLabel).first();
export const poiRow = (scope: Locator | Page, name: string) =>
  scope.getByTestId('trip-poi-list').locator('li').filter({ hasText: name }).first();
export const poiSection = (row: Locator) => row.getByLabel(TEXT.poiLabel).first();
export const riseSuccess = (scope: Locator | Page) => scope.getByTestId('trip-day-rise-set').first();
export const risePending = (scope: Locator | Page) =>
  scope.getByTestId('trip-day-rise-set-pending').first();

export type WeatherKind = 'summary' | 'status';
export async function weatherKind(section: Locator): Promise<WeatherKind> {
  await expect(section).toBeVisible();
  const id = await section.getAttribute('data-testid');
  if (id === 'trip-weather-summary') return 'summary';
  if (id === 'trip-weather-status') return 'status';
  throw new Error(`알 수 없는 weather 섹션 testid: ${id}`);
}

/** UI ↔ JSON consistency for one (day, feature). Never asserts exact values — only state→text mapping. */
export async function expectWeatherConsistent(
  section: Locator,
  resolution: WxResolution | undefined,
  cards: Record<string, WxCard>,
  isoDate: string,
): Promise<WeatherKind> {
  expect(resolution, 'weather_by_feature_id 에 이 feature 가 있어야 한다').toBeTruthy();
  const kind = await weatherKind(section);
  if (resolution!.state === 'found') {
    const card = cards[cardKeyOf(resolution)];
    expect(card, 'found 는 참조하는 card 가 있어야 한다(계약 불변식)').toBeTruthy();
    if (kind === 'status') {
      await expect(section).toContainText(TEXT.noData);
      expect(metricsForDate(card!, isoDate).length, '카드에 그 날짜 metric 이 없을 때만 no_data 문구').toBe(0);
    } else {
      await expect(section).toContainText(/현재|예보|미세먼지|시간대별/);
    }
  } else {
    expect(kind, `${resolution!.state} 는 status 섹션`).toBe('status');
    await expect(section).toContainText(STATUS_TEXT[resolution!.state] ?? '');
  }
  return kind;
}

export function parseRiseSet(text: string): { sunrise: string | null; sunset: string | null; reference: string | null } {
  const sunrise = /일출\s*(\d{1,2}:\d{2})/.exec(text)?.[1] ?? null;
  const sunset = /일몰\s*(\d{1,2}:\d{2})/.exec(text)?.[1] ?? null;
  const rest = text.replace(/일출\s*\d{1,2}:\d{2}|일몰\s*\d{1,2}:\d{2}/g, '').replace(/\s+/g, ' ').trim();
  const reference = /^(.*?)\s*기준$/.exec(rest)?.[1]?.trim() || null;
  return { sunrise, sunset, reference };
}

// ───────────────────────────── lifecycle ─────────────────────────────
export function pageErrorGuard(page: Page): () => string[] {
  const errors: string[] = [];
  page.on('pageerror', (err) => errors.push(String(err?.message ?? err)));
  return () => errors;
}

/** Per-file registry: trips created in a test are deleted in afterEach (also on failure). */
export function useTripCleanup() {
  const created: string[] = [];
  test.afterEach(async ({ page }, testInfo) => {
    const ids = created.splice(0);
    let failed = false;
    for (const id of ids) {
      try {
        await deleteTrip(page, id);
      } catch (err) {
        failed = true;
        testInfo.annotations.push({ type: 'cleanup', description: `deleteTrip(${id}) 실패: ${String(err)}` });
      }
    }
    if (failed) {
      // Last-resort sweep of '[e2e]' trips only (helpers contract) — never touches other data.
      const n = await deleteAllE2eTrips(page).catch(() => -1);
      testInfo.annotations.push({ type: 'cleanup', description: `deleteAllE2eTrips → ${n}` });
    }
  });
  return {
    track(id: string) {
      created.push(id);
      return id;
    },
  };
}

/**
 * For `test.skip(onMobile, …)` / `test.skip(onDesktop, …)` — fixture-based so the condition is
 * safe at collection time too (the `mobile` project sets `isMobile: true`).
 */
export const onMobile = ({ isMobile }: { isMobile: boolean }) => isMobile;
export const onDesktop = ({ isMobile }: { isMobile: boolean }) => !isMobile;

export function annotate(description: string) {
  test.info().annotations.push({ type: 'wx', description });
}

export { requireEnv };
