/**
 * SRCH area-local helpers (not a spec — Playwright testMatch is `*.live.spec.ts`).
 * Everything here is written against the shared `../helpers/live` contract (SPEC.md §Helpers) plus the
 * real PinVi UI (apps/web/components/map/MapSearchBox.tsx, FeatureMapView.tsx, FeatureDetail*.tsx).
 */
import { expect, test, type Locator, type Page, type Response, type TestInfo } from '@playwright/test';
import { isMobile, shot } from './live';

// ──────────────────────────────── project / viewport ────────────────────────────────

/** True under the 390x844 project (viewport-based, shared `isMobile`). */
export function isMobileProject(testInfo: TestInfo): boolean {
  return isMobile(testInfo);
}

/**
 * Cases not tagged `mobile` skip under the mobile project (SPEC rule: only mobile-tagged cases run there).
 * Works both inside a test body (boolean form) and at describe level (callback form) — Playwright allows
 * the callback form only in a describe, and `test.info()` only while a test runs.
 */
function skipWhen(mobile: boolean, reason: string): void {
  let info: TestInfo | null = null;
  try {
    info = test.info();
  } catch {
    info = null;
  }
  if (info) test.skip(isMobile(info) === mobile, reason);
  else test.skip(({ isMobile: m }) => m === mobile, reason);
}

export function desktopOnly(): void {
  skipWhen(true, 'desktop-only case (not tagged mobile)');
}

export function mobileOnly(): void {
  skipWhen(false, 'mobile-only case');
}

// ──────────────────────────────── search API shapes ────────────────────────────────

export type SearchSource = 'feature' | 'my_poi' | 'address' | 'kakao' | 'naver';

export interface SearchRow {
  source: SearchSource;
  name: string;
  coord: { lon: number; lat: number } | null;
  feature_id: string | null;
  poi_id: string | null;
  trip_id: string | null;
  trip_title: string | null;
  external_id: string | null;
  address: string | null;
  road_address: string | null;
  category: string | null;
  category_label?: string | null;
  marker_color: string | null;
  marker_icon: string | null;
  provider_url: string | null;
  phone: string | null;
}

export interface SearchOutcome {
  status: number;
  rows: SearchRow[];
  degraded: string[];
  elapsedMs: number;
  /** `bbox` query param the web sent (`lng_min,lat_min,lng_max,lat_max`) or null. */
  bbox: [number, number, number, number] | null;
  requestUrl: string;
}

export const SOURCE_BADGE: Record<SearchSource, string> = {
  feature: '장소',
  my_poi: '내 여행',
  address: '주소',
  kakao: '카카오',
  naver: '네이버 검색',
};

/** 8-digit Map category code (`01070400`). The UI must never show this to a user (#614). */
export const CATEGORY_CODE_RE = /^\d{8}$/;

/**
 * Leaf names from kor-travel-map `PLACE_CATEGORY_DEFINITIONS` (src/kortravelmap/category/_definitions.py).
 * PinVi `category_label` is the last element of the catalog `path`, so a label must match one of these
 * (tier1..tier4 names). Kept as a loose set; unknown-but-non-numeric labels only soft-fail.
 */
export const KNOWN_CATEGORY_LABELS: ReadonlySet<string> = new Set([
  '미분류', '관광', '식음', '숙박', '온천·스파', '편의', '교통', '의료',
  // 관광
  '테마파크', '놀이공원', '대형 테마파크', '중소형 놀이공원', '워터파크', '동물원·수족관', '동물원', '수족관', '체험형 테마파크',
  '자연경관', '산·계곡', '국립공원', '도립·군립공원', '산림욕장', '강·호수', '해안·섬', '폭포·동굴',
  '수목원·식물원', '수목원', '국립수목원', '공립수목원', '사립수목원', '식물원', '정원',
  '자연명소', '해수욕장', '공원·광장', '전망대', '등대',
  '관광안내', '관광안내소', '공공 관광안내소', '민간 관광안내소',
  '문화시설', '박물관', '국공립 박물관', '사립 박물관', '테마 박물관', '미술관·갤러리', '미술관', '갤러리',
  '공연장', '일반 공연장', '관광공연장', '영화관', '도서관', '지방문화원',
  '국가유산', '전통사찰', '궁궐·왕릉', '사적·기념물', '한옥·민속마을',
  '액티비티', '골프장', '관광궤도', '관광유람선', '레저스포츠', '트레킹·둘레길',
  // 식음
  '음식점', '한식', '양식', '일식', '중식', '아시안', '패스트푸드', '뷔페', '주점', '분식', '베이커리',
  '카페', '커피전문점', '프랜차이즈 카페', '개인 카페', '디저트 카페', '베이커리 카페',
  // 숙박
  '호텔', '관광호텔', '비즈니스호텔', '한옥호텔', '리조트', '휴양콘도미니엄', '종합휴양업',
  '휴양림', '국립휴양림', '산림청 운영', '공립휴양림', '지자체 운영', '사립휴양림', '민간 운영',
  '모텔', '일반 모텔', '펜션', '관광펜션', '농어촌민박', '민박',
  '캠핑장', '오토캠핑장', '일반 사이트', '카라반·캠핑카 사이트', '글램핑·카라반', '글램핑', '카라반 대여',
  '게스트하우스', '한옥체험업', '대피소·산장',
  // 온천·스파 / 편의 / 교통 / 의료
  '온천', '찜질방·사우나', '스파·테라피',
  '편의점', '은행', '마트', '슈퍼마켓', '백화점', '공중화장실',
  '주차장', '주유소', '정류장', '버스정류장', '지하철역', '기차역', '택시승강장', '휴게소', '고속도로 휴게소', '공항',
  '병원', '종합병원', '의원', '치과', '약국',
]);

/** Tier-1 weight used by the Map #1436 "tourism > lodging > food > other, hospitals last" rule. */
export function categoryRankWeight(category: string | null | undefined): number | null {
  if (!category) return null;
  const code = category.trim();
  if (!CATEGORY_CODE_RE.test(code)) return null;
  switch (code.slice(0, 2)) {
    case '01':
      return 0; // 관광
    case '03':
      return 1; // 숙박
    case '02':
      return 2; // 식음
    case '07':
      return 4; // 의료 — last
    default:
      return 3; // 기타
  }
}

// ──────────────────────────────── search box driver ────────────────────────────────

/** The search box locator. On the trip page pass `page.getByTestId('trip-map-place-search')` as scope. */
export function searchBox(page: Page, scope?: Locator): Locator {
  return (scope ?? page).getByTestId('map-search').first();
}

export function searchInput(page: Page, scope?: Locator): Locator {
  return searchBox(page, scope).getByRole('textbox', { name: '장소·주소 검색' });
}

export function searchRows(page: Page, source?: SearchSource, scope?: Locator): Locator {
  const box = searchBox(page, scope);
  return source ? box.getByTestId(`map-search-result-${source}`) : box.locator('ul > li');
}

export function searchAlert(page: Page, scope?: Locator): Locator {
  return searchBox(page, scope).locator('p[role="alert"]');
}

function parseBbox(raw: string | null): [number, number, number, number] | null {
  if (!raw) return null;
  const parts = raw.split(',').map(Number);
  if (parts.length !== 4 || parts.some((n) => !Number.isFinite(n))) return null;
  return [parts[0]!, parts[1]!, parts[2]!, parts[3]!];
}

function isSearchResponse(res: Response, q: string): boolean {
  if (res.request().method() !== 'GET') return false;
  const url = new URL(res.url());
  return url.pathname.endsWith('/search') && (url.searchParams.get('q') ?? '') === q.trim();
}

/**
 * Type `q` into the box and wait for the matching `GET …/search?q=` response (debounce 250ms, request
 * carries limit=8 + optional bbox bias). Returns the parsed envelope and the elapsed time from the moment
 * the text was typed. Does not assert on content — callers do.
 */
export async function runSearch(
  page: Page,
  q: string,
  opts: { scope?: Locator; submitWithEnter?: boolean; timeoutMs?: number } = {},
): Promise<SearchOutcome> {
  const input = searchInput(page, opts.scope);
  await expect(input).toBeVisible();
  await input.click();
  await input.fill('');
  const responsePromise = page.waitForResponse((res) => isSearchResponse(res, q), {
    timeout: opts.timeoutMs ?? 30_000,
  });
  const t0 = Date.now();
  await input.fill(q);
  if (opts.submitWithEnter) await input.press('Enter');
  const res = await responsePromise;
  const elapsedMs = Date.now() - t0;
  let rows: SearchRow[] = [];
  let degraded: string[] = [];
  try {
    const json = (await res.json()) as { data?: { results?: SearchRow[]; degraded_sources?: string[] } };
    rows = json.data?.results ?? [];
    degraded = json.data?.degraded_sources ?? [];
  } catch {
    // non-JSON (e.g. 422 problem body is JSON too, but be defensive)
  }
  const url = new URL(res.url());
  // Let React paint the list / alert before callers look at the DOM.
  const box = searchBox(page, opts.scope);
  await expect(box.locator('ul > li, p[role="alert"]').first()).toBeVisible({ timeout: 10_000 });
  return {
    status: res.status(),
    rows,
    degraded,
    elapsedMs,
    bbox: parseBbox(url.searchParams.get('bbox')),
    requestUrl: res.url(),
  };
}

export function featureRows(rows: SearchRow[]): SearchRow[] {
  return rows.filter((r) => r.source === 'feature');
}

export function insideBbox(row: SearchRow, bbox: [number, number, number, number]): boolean {
  if (!row.coord) return false;
  const [lngMin, latMin, lngMax, latMax] = bbox;
  return row.coord.lon >= lngMin && row.coord.lon <= lngMax && row.coord.lat >= latMin && row.coord.lat <= latMax;
}

export function recordPerf(testInfo: TestInfo, label: string, ms: number, budgetMs: number): void {
  // Budgets are targets, not gates: over budget is recorded; only > 2× budget fails the case.
  testInfo.annotations.push({ type: ms > budgetMs ? 'perf-over-budget' : 'perf', description: `${label}: ${ms}ms (budget ${budgetMs}ms)` });
  expect.soft(ms, `${label} > 2× budget ${budgetMs}ms`).toBeLessThan(budgetMs * 2);
}

// ──────────────────────────────── detail card driver ────────────────────────────────

export interface DetailCard {
  kind: 'place' | 'event' | 'notice' | 'price' | 'weather' | 'route' | 'area';
  feature_id: string;
  name: string;
  category: string | null;
  category_label?: string | null;
  address_line: string | null;
  homepage_url: string | null;
  phone?: string | null;
  business_hours?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  venue?: string | null;
  body?: string | null;
  enrichment: Array<{ provider: 'kakao' | 'naver'; matched: boolean; provider_url: string | null }>;
  degraded_providers: string[];
}

export const modal = {
  root: (page: Page) => page.getByTestId('feature-detail-modal'),
  title: (page: Page) => page.getByTestId('feature-detail-modal-title'),
  close: (page: Page) => page.getByTestId('feature-detail-modal-close'),
  body: (page: Page) => page.getByTestId('feature-detail-card-body'),
  field: (page: Page, name: 'category' | 'address' | 'phone' | 'hours' | 'homepage' | 'period' | 'venue' | 'notice-body' | 'price' | 'load-enrichment' | 'enrichment-degraded') =>
    page.getByTestId(`feature-detail-card-body-${name}`),
};

function isDetailCardResponse(res: Response, withProviders: boolean): boolean {
  if (res.request().method() !== 'GET') return false;
  const url = new URL(res.url());
  if (!/\/features\/[^/]+\/detail-card$/.test(url.pathname)) return false;
  const hasProviders = url.searchParams.has('providers');
  return withProviders ? hasProviders : !hasProviders;
}

/** Click the popup's '상세보기' and wait for the detail-card response + rendered body. Returns card + ms. */
export async function openDetailFromPopup(
  page: Page,
  opts: { scope?: 'explore' | 'trip' } = {},
): Promise<{ card: DetailCard; elapsedMs: number }> {
  const button = page.getByTestId(opts.scope === 'trip' ? 'trip-map-detail-open' : 'feature-map-detail-open');
  await expect(button).toBeVisible({ timeout: 15_000 });
  const responsePromise = page.waitForResponse((res) => isDetailCardResponse(res, false), { timeout: 30_000 });
  const t0 = Date.now();
  await button.click();
  const res = await responsePromise;
  await expect(modal.body(page)).toBeVisible({ timeout: 15_000 });
  const elapsedMs = Date.now() - t0;
  expect(res.status(), 'detail-card HTTP status').toBe(200);
  const json = (await res.json()) as { data: DetailCard };
  return { card: json.data, elapsedMs };
}

/** Search `q` on /map, pick the first row matching `pick` (default: first feature row), open its detail. */
export async function searchPickOpenDetail(
  page: Page,
  q: string,
  pick: (row: SearchRow) => boolean = (r) => r.source === 'feature',
): Promise<{ outcome: SearchOutcome; picked: SearchRow; card: DetailCard; elapsedMs: number }> {
  const outcome = await runSearch(page, q);
  const picked = outcome.rows.find(pick);
  if (!picked) throw new Error(`no search row matched for q=${q}`);
  const index = outcome.rows.indexOf(picked);
  await searchRows(page).nth(index).getByRole('button').first().click();
  const { card, elapsedMs } = await openDetailFromPopup(page);
  return { outcome, picked, card, elapsedMs };
}

// ──────────────────────────────── explore map driver ────────────────────────────────

export const explore = {
  heading: (page: Page) => page.getByRole('heading', { name: '탐색 지도' }),
  map: (page: Page) => page.getByTestId('feature-map'),
  canvas: (page: Page) => page.locator('.maplibregl-canvas').first(),
  legend: (page: Page) => page.getByTestId('feature-map-marker-style'),
  loading: (page: Page) => page.getByTestId('feature-map-loading'),
  empty: (page: Page) => page.getByTestId('feature-map-empty'),
  error: (page: Page) => page.getByTestId('feature-map-error'),
};

export interface InBoundsItem {
  feature_id: string;
  name: string;
  kind: string;
  category?: string | null;
  coord: { lon: number; lat: number } | null;
}

export function isInBoundsResponse(res: Response): boolean {
  return res.request().method() === 'GET' && new URL(res.url()).pathname.endsWith('/features/in-bounds');
}

export async function readInBounds(res: Response): Promise<{ bbox: string | null; items: InBoundsItem[]; clusters: number }> {
  const url = new URL(res.url());
  type Body = { data?: { items?: InBoundsItem[]; clusters?: unknown[] } };
  let json: Body;
  try {
    json = (await res.json()) as Body;
  } catch {
    // body discarded (the page re-rendered/navigated after this response) — the request is a plain GET
    // with the page's cookies, so read the same URL again
    const page = res.frame().page();
    json = (await (await page.context().request.get(res.url())).json()) as Body;
  }
  return { bbox: url.searchParams.get('bbox'), items: json.data?.items ?? [], clusters: json.data?.clusters?.length ?? 0 };
}

/** Go to /map and wait for the first in-bounds response (auto-center settles within 2s). */
export async function gotoExplore(page: Page): Promise<Response> {
  const first = page.waitForResponse(isInBoundsResponse, { timeout: 45_000 });
  await page.goto('/map');
  await expect(explore.heading(page)).toBeVisible();
  await expect(explore.canvas(page)).toBeVisible({ timeout: 30_000 });
  const res = await first;
  await expect(explore.loading(page)).toBeHidden({ timeout: 30_000 });
  return res;
}

/** Scroll-wheel zoom on the canvas centre; positive steps zoom out, negative zoom in. Returns the next in-bounds response. */
export async function wheelZoom(page: Page, steps: number): Promise<Response | null> {
  const box = await explore.canvas(page).boundingBox();
  if (!box) throw new Error('map canvas has no bounding box');
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  await page.mouse.move(cx, cy);
  const next = page.waitForResponse(isInBoundsResponse, { timeout: 30_000 }).catch(() => null);
  const dir = Math.sign(steps);
  for (let i = 0; i < Math.abs(steps); i += 1) {
    await page.mouse.wheel(0, dir * 400);
    await page.waitForTimeout(120);
  }
  return next;
}

/** Drag the map by (dx, dy) pixels. Returns the next in-bounds response (null if viewport cache served it). */
export async function dragMap(page: Page, dx: number, dy: number): Promise<Response | null> {
  if (isMobile(test.info())) return keyboardPan(page, dx, dy);
  const box = await explore.canvas(page).boundingBox();
  if (!box) throw new Error('map canvas has no bounding box');
  const sx = box.x + box.width / 2;
  const sy = box.y + box.height / 2;
  const next = page.waitForResponse(isInBoundsResponse, { timeout: 30_000 }).catch(() => null);
  await page.mouse.move(sx, sy);
  await page.mouse.down();
  await page.mouse.move(sx + dx / 2, sy + dy / 2, { steps: 8 });
  await page.mouse.move(sx + dx, sy + dy, { steps: 8 });
  await page.mouse.up();
  return next;
}

/**
 * Touch projects: mouse drags do not pan maplibre under touch emulation, so pan with the keyboard
 * handler (arrow keys, ~100 px per press) on the focused canvas instead.
 */
async function keyboardPan(page: Page, dx: number, dy: number): Promise<Response | null> {
  const next = page.waitForResponse(isInBoundsResponse, { timeout: 30_000 }).catch(() => null);
  const canvas = explore.canvas(page);
  await canvas.focus();
  const press = async (key: string, n: number) => {
    for (let i = 0; i < n; i += 1) {
      await page.keyboard.press(key);
      await page.waitForTimeout(120);
    }
  };
  // dragging content left (dx < 0) moves the view east → ArrowRight
  await press(dx < 0 ? 'ArrowRight' : 'ArrowLeft', Math.max(1, Math.round(Math.abs(dx) / 100)));
  await press(dy < 0 ? 'ArrowDown' : 'ArrowUp', Math.max(1, Math.round(Math.abs(dy) / 100)));
  return next;
}

/**
 * Zoom out until the search bias bbox covers (clamped) Korea so Map's own order is preserved in the response
 * (region_biased_items: all rows inside → `[*first4, *rest]` == original order). Verified by the caller via
 * `outcome.bbox` width. Wheel-zoom out is capped by the VWorld style minZoom, which is national scale.
 */
export async function zoomToNation(page: Page): Promise<void> {
  await wheelZoom(page, 12);
  await expect(explore.loading(page)).toBeHidden({ timeout: 30_000 });
}

export function bboxSpansKorea(bbox: [number, number, number, number] | null): boolean {
  if (!bbox) return true; // no bias at all also preserves Map order
  return bbox[2] - bbox[0] >= 5 && bbox[3] - bbox[1] >= 4;
}

/**
 * Click a feature marker by its title. Marker DOM comes from the vendored `vworld-map-web` MakiMarker
 * (ariaLabel = title) — tried in order: aria-label on the marker, aria-label on a child, role button.
 * README "helpers needed": `clickFeatureMarker(page, title)` should move here once the integrator confirms
 * the marker DOM.
 */
export async function clickFeatureMarker(page: Page, title: string): Promise<void> {
  const candidates = [
    page.locator(`.maplibregl-marker[aria-label="${title}"]`),
    page.locator(`.maplibregl-marker [aria-label="${title}"]`),
    page.locator('.maplibregl-marker').getByRole('button', { name: title, exact: true }),
    page.locator(`.maplibregl-marker[title="${title}"]`),
  ];
  for (const loc of candidates) {
    if ((await loc.count()) > 0) {
      await loc.first().click({ force: true });
      return;
    }
  }
  throw new Error(`feature marker not found in DOM for title=${title}`);
}

export { shot };
