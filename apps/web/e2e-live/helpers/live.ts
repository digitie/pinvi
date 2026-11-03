/**
 * Shared helpers for the live e2e catalog (`apps/web/e2e-live`).
 *
 * Every spec under `specs/<area>/` talks to the deployed PinVi web app through a real browser —
 * nothing here (or anywhere in `e2e-live/`) calls `page.route`. The base URL and all credentials
 * come from env only (`docs/runbooks/live-e2e-catalog.md` lists the names); values are never
 * printed, attached or written into error messages.
 *
 * Selectors are read from `apps/web` on origin/main 620b6046:
 *  - app/(auth)/login/page.tsx            login-email / login-password / login-submit (disabled until hydrated)
 *  - app/(admin)/admin/login/page.tsx     data-testid=admin-login + [data-slot=login-username|login-password|login-submit]
 *  - components/trips/TripDashboard.tsx   trip-create-* / '관리 열기' / '초안 여행을 저장했습니다.' / trip-list
 *  - components/trips/TripDetail.tsx      trip-detail-panel / '패널 열기' / #trip-panel-plan / day tabs (role=tab, `${n}일차`)
 *  - components/map/MapSearchBox.tsx      map-search / '장소·주소 검색' / map-search-result-{source} + badge labels
 *  - components/trips/TripPoiList.tsx     trip-poi-list (ol > li)
 *  - components/trips/TripMapView.tsx     trip-map-detail-open ('상세보기')
 *  - components/trips/TripShareLinks.tsx  '링크 만들기' / new-share-url / 권한 / 만료일(선택)
 *  - packages/api-client/src/endpoints/trips.ts  DELETE /trips/{id} {mode:'soft_delete'}, GET /trips?bucket=all&cursor=
 */
import {
  expect,
  test,
  type Browser,
  type BrowserContext,
  type Cookie,
  type Locator,
  type Page,
  type Response,
  type TestInfo,
} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

export const e2ePrefix = '[e2e]';
/** Persistent read-only seed trip (WX-011/012); never swept because it does not start with `[e2e]`. */
export const seedSunTripTitle = process.env.PINVI_E2E_SEED_SUN_TRIP ?? '[e2e-seed] weather-sun';

/**
 * Prod web origin. Must be explicit (#618: the live suite never falls back to localhost).
 * Empty only while `playwright test --list` runs without env; `globalSetup` fails fast before any test.
 */
export const baseURL: string = (process.env.PLAYWRIGHT_BASE_URL ?? '').replace(/\/$/, '');

/** Fail fast with a clear message when a required env var is missing. Never prints the value. */
export function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`환경변수 ${name} 가 필요합니다 (n150 root-only env 파일, 값은 출력하지 않는다).`);
  }
  return value;
}

/* ------------------------------------------------------------------ viewport / project */

export const MOBILE_MAX_WIDTH = 1023; // lib/useMobileWebLayout.ts `(max-width: 1023px)`

/** Mobile web layout is a pure viewport decision — true under the 390x844 `mobile` project. */
export function isMobile(testInfo: TestInfo): boolean {
  const vp = testInfo.project.use.viewport;
  return !!vp && vp.width <= MOBILE_MAX_WIDTH;
}

/** Same as `isMobile`, for code that has no `testInfo` in scope (uses `test.info()`). */
export function isMobileProject(): boolean {
  return isMobile(test.info());
}

/* ------------------------------------------------------------------ API origin */

let knownApiBase: string | null = process.env.PINVI_E2E_API_URL?.replace(/\/$/, '') ?? null;

const API_PATH_RE = /^(.*?)\/(auth|trips|users|features|search|transport|admin|storage)(?:[/?]|$)/;

/**
 * Remembers the API base (origin + path prefix) from the page's own fetch/xhr traffic.
 * The web bundle bakes `NEXT_PUBLIC_PINVI_API_URL` in at build time and the repo does not pin the
 * prod value, so the first API request the app makes is the source of truth. `PINVI_E2E_API_URL`
 * overrides. Idempotent per page.
 */
export function trackApiBase(page: Page): void {
  const marker = page as Page & { __e2eApiTracked?: boolean };
  if (marker.__e2eApiTracked) return;
  marker.__e2eApiTracked = true;
  page.on('request', (request) => {
    if (knownApiBase) return;
    const type = request.resourceType();
    if (type !== 'fetch' && type !== 'xhr') return;
    let url: URL;
    try {
      url = new URL(request.url());
    } catch {
      return;
    }
    if (baseURL && url.origin === new URL(baseURL).origin && !/\/(auth|trips)\b/.test(url.pathname)) {
      return;
    }
    const match = API_PATH_RE.exec(url.pathname);
    if (!match) return;
    knownApiBase = `${url.origin}${match[1] ?? ''}`;
  });
}

/**
 * API base as seen by the browser (`https://api.host` or `https://web.host/api`).
 * Resolved from `PINVI_E2E_API_URL`, else from traffic already observed on any tracked page, else by
 * loading `/login` (which always calls `GET /auth/oauth/providers`).
 */
export async function apiBaseURL(page: Page): Promise<string> {
  if (knownApiBase) return knownApiBase;
  trackApiBase(page);
  const pending = page
    .waitForRequest((req) => /\/auth\/(oauth\/providers|me)(\?|$)/.test(req.url()), { timeout: 30_000 })
    .catch(() => null);
  await page.goto('/login');
  const req = await pending;
  if (!knownApiBase && req) {
    const url = new URL(req.url());
    knownApiBase = `${url.origin}${url.pathname.replace(/\/auth\/.*$/, '')}`;
  }
  if (!knownApiBase) {
    throw new Error('API base 를 페이지 트래픽에서 찾지 못했습니다 — PINVI_E2E_API_URL 로 지정하세요.');
  }
  return knownApiBase;
}

/* ------------------------------------------------------------------ login */

/*
 * Session reuse. Prod limits the auth endpoints to 5 requests/min (`pinvi_rate_limit_auth_per_minute`),
 * so logging in through the form before every test 429s after a handful of cases. The suite runs with
 * `workers: 1`, so one worker process holds an in-memory cookie jar per identity: the first login goes
 * through the UI, later `loginAs*` calls seed the new context with those cookies and confirm the app
 * accepts them (the app itself refreshes an expired access cookie). If the session was revoked (logout,
 * refused admin login, rotated refresh token) the check fails and we fall back to the form.
 * Cookies live only in this process's memory — never on disk, never in a report.
 */
const sessionCache = new Map<string, Cookie[]>();

/** Drops cached sessions (all, or one identity) — call after a test logs a session out. */
export function forgetSessions(email?: string): void {
  if (email) sessionCache.delete(email);
  else sessionCache.clear();
}

async function rememberSession(page: Page, key: string): Promise<void> {
  sessionCache.set(key, await page.context().cookies());
  // Refresh tokens rotate: whenever this context refreshes its session, re-snapshot the cookies so
  // the next test never offers an already-rotated refresh token (that 401s and logs the test out).
  const ctx = page.context() as BrowserContext & { __e2eSessionKey?: string };
  if (ctx.__e2eSessionKey === key) return;
  ctx.__e2eSessionKey = key;
  ctx.on('requestfinished', (req) => {
    if (!/\/auth\/refresh(\?|$)/.test(req.url())) return;
    void req
      .response()
      .then(async (res) => {
        if (res && res.ok() && ctx.__e2eSessionKey === key) sessionCache.set(key, await ctx.cookies());
      })
      .catch(() => undefined);
  });
}

async function reuseSession(page: Page, key: string, landing: string, ready: Locator): Promise<boolean> {
  const cookies = sessionCache.get(key);
  if (!cookies) return false;
  await page.context().addCookies(cookies);
  await page.goto(landing);
  try {
    await expect(ready).toBeVisible({ timeout: 20_000 });
  } catch {
    sessionCache.delete(key);
    return false;
  }
  if (/\/login(?:[/?#]|$)/.test(new URL(page.url()).pathname)) {
    sessionCache.delete(key);
    return false;
  }
  await rememberSession(page, key);
  return true;
}

/*
 * Rate limits (apps/api/app/core/config.py): auth 5/min, authenticated 60/min, both per 60 s window.
 * A 429 is waited out (Retry-After, default 61 s, cap 70 s) and the step retried — never hidden: each
 * wait is recorded as a `rate-limit` annotation on the test.
 */
async function backOff(res: { headers(): Record<string, string> }, what: string): Promise<void> {
  const retryAfter = Number(res.headers()['retry-after'] ?? '');
  const waitMs = Math.min(Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter * 1000 + 1000 : 61_000, 70_000);
  try {
    test.info().annotations.push({ type: 'rate-limit', description: `${what} 429 — retry in ${waitMs} ms` });
  } catch {
    // outside a test (global setup/teardown)
  }
  await new Promise((resolve) => setTimeout(resolve, waitMs));
}

/** Runs an API call made with `context.request`, retrying up to 3 times on 429. */
export async function withRateLimitRetry<T extends { status(): number; headers(): Record<string, string> }>(
  what: string,
  call: () => Promise<T>,
): Promise<T> {
  for (let attempt = 1; ; attempt += 1) {
    const res = await call();
    if (res.status() !== 429 || attempt >= 3) return res;
    await backOff(res, what);
  }
}

/**
 * Clicks `submit` and resolves with the `POST /auth/login` response; on 429 waits for `Retry-After`
 * (default 61 s) and submits again — up to 3 attempts. The form keeps its values across a 429.
 */
async function submitLogin(page: Page, submit: Locator): Promise<Response | null> {
  for (let attempt = 1; ; attempt += 1) {
    const loginRes = page
      .waitForResponse((r) => r.request().method() === 'POST' && /\/auth\/login(\?|$)/.test(r.url()), {
        timeout: 30_000,
      })
      .catch(() => null);
    await expect(submit).toBeEnabled({ timeout: 20_000 });
    await submit.click();
    const res = await loginRes;
    if (!res || res.status() !== 429 || attempt >= 3) return res;
    await backOff(res, 'POST /auth/login');
  }
}

export interface LoginOptions {
  /** Skip the session cache and log in through the form (auth/session cases that rotate tokens). */
  fresh?: boolean;
}

async function loginWithUserForm(page: Page, email: string, password: string, opts: LoginOptions = {}): Promise<void> {
  trackApiBase(page);
  if (opts.fresh) sessionCache.delete(email);
  else if (await reuseSession(page, email, '/trips', page.getByRole('heading', { name: '여행', exact: true }))) return;
  await page.goto('/login');
  const submit = page.getByTestId('login-submit');
  // origin/main: the submit button is rendered disabled in server HTML and enabled after hydration.
  await expect(submit).toBeEnabled({ timeout: 20_000 });
  await page.getByTestId('login-email').fill(email);
  await page.getByTestId('login-password').fill(password);
  const res = await submitLogin(page, submit);
  if (res && !knownApiBase) {
    const url = new URL(res.url());
    knownApiBase = `${url.origin}${url.pathname.replace(/\/auth\/login$/, '')}`;
  }
  if (res && res.status() >= 400) {
    throw new Error(`로그인 실패: POST /auth/login → HTTP ${res.status()} (계정/비밀번호/이메일 인증 상태 확인)`);
  }
  await expect(page).toHaveURL(/\/trips(?:[?#].*)?$/, { timeout: 30_000 });
  await rememberSession(page, email);
}

/** Generic user login (second identity, ad-hoc contexts). Credentials are passed in, never logged. */
export async function loginAs(page: Page, email: string, password: string): Promise<void> {
  await loginWithUserForm(page, email, password);
}

/** `test@test.com` — PINVI_E2E_USER_EMAIL / PINVI_E2E_USER_PASSWORD. */
export async function loginAsUser(page: Page, opts: LoginOptions = {}): Promise<void> {
  await loginWithUserForm(page, requireEnv('PINVI_E2E_USER_EMAIL'), requireEnv('PINVI_E2E_USER_PASSWORD'), opts);
}

/** `test2@test.com` — PINVI_E2E_USER2_EMAIL / PINVI_E2E_USER2_PASSWORD (DECISIONS D2). */
export async function loginAsUser2(page: Page): Promise<void> {
  await loginWithUserForm(page, requireEnv('PINVI_E2E_USER2_EMAIL'), requireEnv('PINVI_E2E_USER2_PASSWORD'));
}

/** Second identity creds, only for specs that must type the email into a form (never logged). */
export function user2Email(): string {
  return requireEnv('PINVI_E2E_USER2_EMAIL');
}

/**
 * Admin console login — `/admin/login` renders `LoginForm` from `@kor-travel/ui`
 * (`[data-slot=login-username|login-password|login-submit]` inside `data-testid=admin-login`).
 * PINVI_E2E_ADMIN_EMAIL / PINVI_E2E_ADMIN_PASSWORD; the account must carry role `admin`.
 */
export async function loginAsAdmin(page: Page): Promise<void> {
  const email = requireEnv('PINVI_E2E_ADMIN_EMAIL');
  const password = requireEnv('PINVI_E2E_ADMIN_PASSWORD');
  trackApiBase(page);
  const key = `admin:${email}`;
  if (await reuseSession(page, key, '/admin', page.getByTestId('admin-sidebar'))) return;
  await page.goto('/admin/login');
  const root = page.getByTestId('admin-login');
  await expect(root).toBeVisible({ timeout: 20_000 });
  const submit = root.locator('[data-slot=login-submit]');
  await expect(submit).toBeEnabled({ timeout: 20_000 });
  await root.locator('[data-slot=login-username]').fill(email);
  await root.locator('[data-slot=login-password]').fill(password);
  const res = await submitLogin(page, submit);
  if (res && res.status() >= 400) {
    throw new Error(`관리자 로그인 실패: POST /auth/login → HTTP ${res.status()}`);
  }
  await page.waitForURL((url) => /\/admin(?!\/login)/.test(url.pathname), { timeout: 30_000 });
  await expect(root.locator('[data-slot=login-error]')).toHaveCount(0);
  await rememberSession(page, key);
}

/** Logged-in second-user context (companion / isolation cases). Caller closes the context. */
export async function user2Context(browser: Browser): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL });
  const page = await context.newPage();
  await loginAsUser2(page);
  return { context, page };
}

/* ------------------------------------------------------------------ trips */

export interface CreateTripOptions {
  title: string;
  /** `YYYY-MM-DD`; empty/omitted together with `end` creates an undated trip (0 days). */
  start?: string;
  end?: string;
  region?: string;
}

/** Mobile dashboard hides the create form behind '관리 열기' (TripDashboard.tsx). */
export async function revealCreateForm(page: Page): Promise<void> {
  const form = page.locator('#trip-dashboard-create');
  if (await form.isVisible()) return;
  await page.getByRole('button', { name: '관리 열기' }).click();
  await expect(form).toBeVisible();
}

/**
 * Creates a trip through the dashboard form and returns its id (from the POST /trips response, with
 * the list card href as fallback). The title must start with `[e2e]` unless it is the seed trip.
 */
export async function createTrip(page: Page, opts: CreateTripOptions): Promise<{ id: string }> {
  if (!opts.title.startsWith(e2ePrefix) && opts.title !== seedSunTripTitle) {
    throw new Error(`createTrip: 제목은 '${e2ePrefix}' 로 시작해야 합니다`);
  }
  if ((opts.start ?? '') === '' && (opts.end ?? '') !== '') {
    throw new Error('createTrip: start/end 는 둘 다 주거나 둘 다 비워야 합니다');
  }
  trackApiBase(page);
  if (!/\/trips(?:[?#].*)?$/.test(page.url())) await page.goto('/trips');
  await expect(page.getByRole('heading', { name: '여행', exact: true })).toBeVisible({ timeout: 20_000 });
  await revealCreateForm(page);
  await page.getByTestId('trip-create-title').fill(opts.title);
  await page.getByTestId('trip-create-region').fill(opts.region ?? '');
  await page.getByTestId('trip-create-start').fill(opts.start ?? '');
  await page.getByTestId('trip-create-end').fill(opts.end ?? '');
  let res: Response;
  for (let attempt = 1; ; attempt += 1) {
    const created = page.waitForResponse(
      (r) => r.request().method() === 'POST' && /\/trips$/.test(new URL(r.url()).pathname),
      { timeout: 30_000 },
    );
    await page.getByTestId('trip-create-submit').click();
    res = await created;
    // 429: the form keeps its values on a failed save (TripDashboard clears them only on success).
    if (res.status() !== 429 || attempt >= 3) break;
    await backOff(res, 'POST /trips');
  }
  if (res.status() >= 400) throw new Error(`POST /trips → HTTP ${res.status()}`);
  await expect(page.getByText('초안 여행을 저장했습니다.')).toBeVisible({ timeout: 20_000 });
  let id: string | null = null;
  try {
    const body = (await res.json()) as { data?: { trip_id?: string }; trip_id?: string };
    id = body.data?.trip_id ?? body.trip_id ?? null;
  } catch {
    id = null;
  }
  if (!id) {
    const link = page.getByTestId('trip-list').getByRole('link').filter({ hasText: opts.title }).first();
    await expect(link).toBeVisible();
    const href = (await link.getAttribute('href')) ?? '';
    id = /\/trips\/([0-9a-f-]{36})/i.exec(href)?.[1] ?? null;
  }
  if (!id) throw new Error('생성된 여행의 trip_id 를 찾지 못했습니다');
  return { id };
}

/** `DELETE /trips/{id}` (`soft_delete`) with the browser's cookies; 404 (already gone) is swallowed. */
export async function deleteTrip(page: Page, id: string): Promise<void> {
  const api = await apiBaseURL(page);
  const res = await withRateLimitRetry(`DELETE /trips/${id}`, () =>
    page.context().request.delete(`${api}/trips/${id}`, { data: { mode: 'soft_delete' } }),
  );
  if (!res.ok() && res.status() !== 404) {
    throw new Error(`DELETE /trips/${id} → HTTP ${res.status()}`);
  }
}

interface TripListItem {
  trip_id: string;
  title: string;
}

/** Lists every active trip of the logged-in user through the API (cursor pagination). */
export async function listAllTrips(page: Page): Promise<TripListItem[]> {
  const api = await apiBaseURL(page);
  const items: TripListItem[] = [];
  let cursor: string | null = null;
  for (let round = 0; round < 50; round += 1) {
    const qs = new URLSearchParams({ bucket: 'all', limit: '50' });
    if (cursor) qs.set('cursor', cursor);
    const res = await withRateLimitRetry('GET /trips', () => page.context().request.get(`${api}/trips?${qs.toString()}`));
    if (!res.ok()) throw new Error(`GET /trips → HTTP ${res.status()}`);
    const body = (await res.json()) as {
      data?: TripListItem[];
      meta?: { cursor?: string | null; next_cursor?: string | null; has_more?: boolean };
    };
    items.push(...(body.data ?? []));
    const next = body.meta?.next_cursor ?? body.meta?.cursor ?? null;
    if (!next || body.meta?.has_more === false) break;
    cursor = next;
  }
  return items;
}

/** Safety sweep: soft-deletes every trip of the current user whose title starts with `[e2e]`. */
export async function deleteAllE2eTrips(page: Page): Promise<number> {
  const trips = await listAllTrips(page);
  let n = 0;
  for (const trip of trips) {
    if (!trip.title.startsWith(e2ePrefix)) continue; // '[e2e-seed] …' does not match '[e2e]'
    await deleteTrip(page, trip.trip_id);
    n += 1;
  }
  return n;
}

/** Trip id by exact title (seed trip lookup); null when the user has no such trip. */
export async function findTripByTitle(page: Page, title: string): Promise<string | null> {
  const trips = await listAllTrips(page);
  return trips.find((t) => t.title === title)?.trip_id ?? null;
}

/** Per-day POI counts of a trip from `GET /trips/{id}` (the trip view the detail page loads). */
export async function tripDayPoiCounts(page: Page, id: string): Promise<number[]> {
  const api = await apiBaseURL(page);
  const res = await withRateLimitRetry(`GET /trips/${id}`, () => page.context().request.get(`${api}/trips/${id}`));
  if (!res.ok()) throw new Error(`GET /trips/${id} → HTTP ${res.status()}`);
  const body = (await res.json()) as { data?: { days?: Array<{ pois?: unknown[] }> } };
  return (body.data?.days ?? []).map((d) => (d.pois ?? []).length);
}

export function tripIdFromUrl(page: Page): string {
  const match = page.url().match(/\/trips\/([0-9a-f-]{36})/i);
  if (!match) throw new Error(`trip id not found in url ${page.url()}`);
  return match[1]!;
}

/* ------------------------------------------------------------------ trip detail */

export function detailPanel(page: Page): Locator {
  return page.getByTestId('trip-detail-panel');
}

/**
 * Makes the trip-detail side panel visible (prod DOM, probed 2026-11-03):
 *  - the page renders nothing until the trip view loads, so wait for `trip-detail-shell` first —
 *    an instant `isVisible()` right after `goto` is always false;
 *  - desktop (≥1024): `aside#trip-detail-panel` is open by default; its toggle reads '패널 접기'
 *    (text, no aria-label) and only says '패널 열기' after a collapse;
 *  - mobile: the panel starts hidden; the header toggle has aria-label '패널 열기'.
 * Both toggles carry `aria-controls="trip-detail-panel"` + `aria-expanded`, which is what we key on.
 */
export async function openPanel(page: Page): Promise<void> {
  if (!/\/trips\/[0-9a-f-]{36}/i.test(page.url())) {
    throw new Error(`openPanel: 여행 상세 페이지가 아니다 (${new URL(page.url()).pathname}) — createTrip 뒤에는 page.goto('/trips/<id>') 가 필요하다`);
  }
  await expect(page.getByTestId('trip-detail-shell')).toBeVisible({ timeout: 45_000 });
  const panel = detailPanel(page);
  if (await panel.isVisible()) return;
  const toggle = page.locator('button[aria-controls="trip-detail-panel"][aria-expanded="false"]:visible').first();
  await expect(toggle).toBeVisible();
  await toggle.click();
  await expect(panel).toBeVisible();
}

export type TripTab = '일정' | '파일' | '공유' | '동행' | '댓글';

/**
 * Opens a trip-detail work tab ('일정 N' / '동행 N' carry a count badge, hence the prefix regex).
 * Opens the mobile drawer first when the tab is hidden.
 */
export async function openTripTab(page: Page, label: TripTab): Promise<void> {
  await openPanel(page);
  // the work tabs render twice (desktop header + mobile drawer); only one copy is visible
  const tab = page.getByRole('tab', { name: new RegExp(`^${label}`) }).filter({ visible: true }).first();
  await tab.click();
  await expect(page.getByRole('tabpanel', { name: label })).toBeVisible();
}

/** `${n}일차` day tab (exact so '1일차' never matches '11일차'). */
export function dayTab(page: Page, label: string): Locator {
  return page.getByRole('tab', { name: label, exact: true });
}

export async function selectDay(page: Page, dayIndex: number): Promise<void> {
  await openPanel(page);
  const planTab = page.getByRole('tab', { name: /^일정/ }).first();
  if ((await planTab.count()) > 0 && (await planTab.getAttribute('aria-selected')) !== 'true') {
    await planTab.click();
  }
  const tab = dayTab(page, `${dayIndex}일차`);
  await expect(tab).toBeVisible();
  if ((await tab.getAttribute('aria-selected')) !== 'true') await tab.click();
  await expect(tab).toHaveAttribute('aria-selected', 'true');
}

/** Rows of the selected day's POI list (`<ol data-testid="trip-poi-list">`). */
export function poiRows(page: Page): Locator {
  return page.getByTestId('trip-poi-list').locator('> li');
}

const EXTERNAL_BADGES = ['카카오', '네이버 검색'];
/** Default search pick: any row that is not a Kakao/Naver result (those auto-fire a feature request). */
export const pickNotExternal = (rowText: string): boolean => !EXTERNAL_BADGES.some((b) => rowText.includes(b));
/** Map feature rows only (badge '장소'). */
export const pickFeature = (rowText: string): boolean => rowText.includes('장소') && pickNotExternal(rowText);

/**
 * Adds a place to day `dayIndex` (1-based: 1 = '1일차') through the plan-panel search box
 * (`#trip-panel-plan [data-testid=map-search]`, the copy that is visible on both layouts).
 * `pick` receives each `<li>`'s innerText — name, source badge ('장소' / '카카오' / '네이버 검색' /
 * '주소' / '내 여행') and the secondary line — and the first matching row is clicked; without `pick`
 * the first non-Kakao/Naver row wins. Resolves once the POI row count grew by one and returns the
 * picked row's name (first line).
 */
export async function searchAndAddPlace(
  page: Page,
  dayIndex: number,
  query: string,
  pick: (rowText: string) => boolean = pickNotExternal,
): Promise<string> {
  if (!Number.isInteger(dayIndex) || dayIndex < 1) {
    throw new Error(`searchAndAddPlace: dayIndex 는 1-based 입니다 (받은 값 ${dayIndex})`);
  }
  await selectDay(page, dayIndex);
  const before = await poiRows(page).count();
  const box = page.locator('#trip-panel-plan').getByTestId('map-search').first();
  const input = box.getByRole('textbox', { name: '장소·주소 검색' });
  await expect(input).toBeVisible();
  await input.fill('');
  await input.fill(query);
  const rows = box.locator('ul > li');
  await expect
    .poll(
      async () => {
        if ((await rows.count()) > 0) return 'rows';
        const alert = box.locator('p[role="alert"]');
        return (await alert.count()) > 0 ? ((await alert.first().textContent()) ?? 'alert') : 'pending';
      },
      { timeout: 45_000, message: `검색 '${query}' 결과 대기` },
    )
    .toBe('rows');
  const count = await rows.count();
  let target: Locator | null = null;
  let targetText = '';
  for (let i = 0; i < count; i += 1) {
    const row = rows.nth(i);
    const text = await row.innerText();
    if (pick(text)) {
      target = row;
      targetText = text;
      break;
    }
  }
  if (!target) {
    throw new Error(`검색 '${query}': pick 조건에 맞는 결과 행이 없습니다 (행 ${count}개)`);
  }
  const name = (await target.locator('button span.truncate').first().innerText()).trim() || targetText.split('\n')[0]!.trim();
  const posted = page.waitForResponse(
    (r) => r.request().method() === 'POST' && /\/trips\/[^/]+\/pois$/.test(new URL(r.url()).pathname),
    { timeout: 30_000 },
  );
  await target.locator('button').first().click();
  const res = await posted;
  if (res.status() >= 400) throw new Error(`POST /pois → HTTP ${res.status()} (${name})`);
  await expect(poiRows(page)).toHaveCount(before + 1, { timeout: 30_000 });
  return name;
}

/** Selects the POI row by name and opens the feature detail modal from the map popup ('상세보기'). */
export async function openPoiDetail(page: Page, name: string): Promise<void> {
  await openPanel(page);
  const row = poiRows(page).filter({ hasText: name }).first();
  await expect(row).toBeVisible();
  await row.locator('button[aria-current]').first().click();
  const open = page.getByTestId('trip-map-detail-open');
  await expect(open).toBeVisible({ timeout: 15_000 });
  await open.click();
  await expect(page.getByTestId('feature-detail-modal')).toBeVisible({ timeout: 15_000 });
}

/* ------------------------------------------------------------------ share links */

export type ShareVisibility = 'view_only' | 'comment' | 'edit';

export interface CreatedShareLink {
  url: string;
  tripId: string;
  token: string;
}

export const sharedPath = (tripId: string, token: string) => `/shared/${tripId}/${token}`;

/**
 * Creates a share link on the open trip page (opens the '공유' tab when needed) and reads the
 * one-time banner. The returned token is a secret — specs must `redact()` it from messages and the
 * share-opening specs run with trace off (playwright.live-catalog.config.ts).
 */
export async function createShareLink(
  page: Page,
  opts: { visibility?: ShareVisibility; expires?: string } = {},
): Promise<CreatedShareLink> {
  const section = page.getByRole('region', { name: '공유 링크' });
  if (!(await section.isVisible())) await openTripTab(page, '공유');
  await section.getByLabel('권한').selectOption(opts.visibility ?? 'view_only');
  if (opts.expires) await section.getByLabel('만료일(선택)').fill(opts.expires);
  const isCreate = (r: Response) => r.request().method() === 'POST' && /\/share-tokens(\?|$)/.test(new URL(r.url()).pathname);
  for (let attempt = 1; ; attempt += 1) {
    const created = page.waitForResponse(isCreate, { timeout: 30_000 });
    await section.getByRole('button', { name: '링크 만들기' }).click();
    const res = await created;
    if (res.status() === 429 && attempt < 3) {
      await backOff(res, 'POST share-tokens');
      continue;
    }
    if (!res.ok()) throw new Error(`공유 링크 생성 실패: POST share-tokens → HTTP ${res.status()}`);
    break;
  }
  const banner = page.getByTestId('new-share-url');
  await expect(banner).toBeVisible();
  await expect(banner).toContainText('링크가 생성됐습니다. 이 주소는 지금만 표시됩니다.');
  const url = (await banner.locator('code').textContent())?.trim() ?? '';
  const match = /\/shared\/([0-9a-f-]{36})\/([^/?#]+)$/i.exec(url);
  if (!match) throw new Error('공유 URL 형식을 인식하지 못했습니다.');
  return { url, tripId: match[1]!, token: match[2]! };
}

export interface RecordedRequest {
  url: string;
  referer: string | undefined;
}

export interface FreshSharedPage {
  context: BrowserContext;
  page: Page;
  requests: RecordedRequest[];
  apiStatus: number;
}

/** Opens the share page in a logged-out context; returns the share API status and request log. */
export async function openSharedInFreshContext(
  browser: Browser,
  tripId: string,
  token: string,
  opts: { viewport?: { width: number; height: number } } = {},
): Promise<FreshSharedPage> {
  const context = await browser.newContext({
    baseURL,
    ...(opts.viewport ? { viewport: opts.viewport } : {}),
  });
  const page = await context.newPage();
  const requests: RecordedRequest[] = [];
  page.on('request', (request) => {
    requests.push({ url: request.url(), referer: request.headers()['referer'] });
  });
  const apiResponse = page.waitForResponse((response) =>
    new RegExp(`/trips/${tripId}/shared/[^/?#]+`).test(response.url()),
  );
  await page.goto(sharedPath(tripId, token));
  const response = await apiResponse;
  return { context, page, requests, apiStatus: response.status() };
}

/**
 * App alerts only. Next.js mounts `<p id="__next-route-announcer__" role="alert">` on every page,
 * so a bare `getByRole('alert')` never has count 0 (first prod run, 2026-11-03).
 */
export function appAlerts(scope: Page | Locator): Locator {
  return scope.locator('[role="alert"]:not(#__next-route-announcer__)');
}

/**
 * Individually rendered feature markers on the explore/trip map. Cluster markers are the same
 * `.maplibregl-marker[role=button]` but labelled "N개 위치 묶음 펼치기" (vworld-map-web), and clicking one
 * zooms instead of opening a popup.
 */
export function featureMarkerButtons(page: Page): Locator {
  return page.locator('.maplibregl-marker[role="button"]:not([data-is-cluster="true"]):not([aria-label*="묶음"])');
}

/**
 * Explore map: zooms in (keyboard `=` on the canvas, ≤ `maxSteps`) until at least `min` individual
 * feature markers are rendered — the default Seoul viewport is often all clusters.
 */
export async function ensureFeatureMarkers(page: Page, min = 1, maxSteps = 5): Promise<Locator> {
  // Server clusters of one are labelled with the place name (not "N개 위치 묶음") but are still
  // clusters — clicking one zooms. The explore legend is the ground truth: data-kind="feature".
  const legend = page.locator('[data-testid="feature-map-marker-style"][data-kind="feature"]');
  for (let step = 0; step <= maxSteps; step += 1) {
    try {
      await expect.poll(() => legend.count(), { timeout: 8_000 }).toBeGreaterThanOrEqual(min);
      break;
    } catch {
      if (step === maxSteps) break;
      const canvas = page.locator('.maplibregl-canvas').first();
      await canvas.focus();
      await page.keyboard.press('=');
      await page.waitForTimeout(600);
    }
  }
  return featureMarkerButtons(page);
}

async function featureLegendTitles(page: Page): Promise<Set<string>> {
  const legend = page.locator('[data-testid="feature-map-marker-style"][data-kind="feature"]');
  return new Set((await legend.allTextContents()).map((t) => t.trim()).filter(Boolean));
}

/**
 * Feature markers that a user can actually click right now: rendered inside the map canvas and the
 * topmost element at their centre (markers outside the viewport stay in the DOM, and the search card /
 * transport panel overlay part of the canvas). Clicking anything else lands on the map, and the
 * popup's `closeOnClick` closes it again (first prod run: CORE-013/025 never saw a popup).
 */
export async function clickableFeatureMarkers(page: Page, max = 5): Promise<Locator[]> {
  const all = featureMarkerButtons(page);
  const titles = [...(await featureLegendTitles(page))];
  const indexes = await all.evaluateAll(
    (els, { limit, featureTitles }) => {
    const canvas = document.querySelector('.maplibregl-canvas')?.getBoundingClientRect();
    const allowed = new Set(featureTitles);
    const out: number[] = [];
    els.forEach((el, i) => {
      if (out.length >= limit || !canvas) return;
      // only real features (legend data-kind="feature"), never clusters-of-one
      if (allowed.size > 0 && !allowed.has((el.getAttribute('aria-label') ?? '').trim())) return;
      const r = el.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      if (r.width === 0 || cx < canvas.left || cx > canvas.right || cy < canvas.top || cy > canvas.bottom) return;
      const top = document.elementFromPoint(cx, cy);
      if (top && (top === el || el.contains(top))) out.push(i);
    });
    return out;
    },
    { limit: max, featureTitles: titles },
  );
  return indexes.map((i) => all.nth(i));
}

/** Masks a secret in text destined for logs/messages. */
export function redact(text: string, secret: string): string {
  return secret ? text.split(secret).join('<token>') : text;
}

/* ------------------------------------------------------------------ waits */

const TILE_RE = /vworld\.kr\/req\/wmts|xdworld\.vworld\.kr|\/req\/wmts\//i;

/**
 * Resolves once no VWorld tile request has started for 3 s (max 45 s). Counts only tile traffic so
 * transport/weather polling never keeps the map "busy".
 */
export async function waitForMapIdle(page: Page): Promise<void> {
  const quietMs = 3_000;
  const maxMs = 45_000;
  let lastTileAt = Date.now();
  const onRequest = (req: { url(): string }) => {
    if (TILE_RE.test(req.url())) lastTileAt = Date.now();
  };
  page.on('request', onRequest);
  try {
    const started = Date.now();
    for (;;) {
      const now = Date.now();
      if (now - lastTileAt >= quietMs) return;
      if (now - started >= maxMs) return;
      await page.waitForTimeout(250);
    }
  } finally {
    page.off('request', onRequest);
  }
}

function isApiResponse(res: Response): boolean {
  const type = res.request().resourceType();
  return type === 'fetch' || type === 'xhr';
}

/**
 * Next fetch/XHR response whose URL path (+ query) matches `pathPattern`. Start it before the navigation or
 * click that triggers the request; `res.request().postDataJSON()` is available on the result.
 */
export function waitForRequest(page: Page, pathPattern: RegExp, timeout = 45_000): Promise<Response> {
  return page.waitForResponse(
    (res) => {
      // API calls only: the page navigation to `/trips/{id}` has the same path as `GET /trips/{id}`.
      if (!isApiResponse(res)) return false;
      try {
        const url = new URL(res.url());
        return pathPattern.test(url.pathname + url.search);
      } catch {
        return false;
      }
    },
    { timeout },
  );
}

/** GET-only variant of `waitForRequest` (ignores preflight and mutations on the same path). */
export function waitForGet(page: Page, pathPattern: RegExp, timeout = 30_000): Promise<Response> {
  return page.waitForResponse(
    (res) => {
      if (res.request().method() !== 'GET' || !isApiResponse(res)) return false;
      const url = new URL(res.url());
      return pathPattern.test(url.pathname + url.search);
    },
    { timeout },
  );
}

/* ------------------------------------------------------------------ screenshots */

/** `shots/<id>-<step>.png` under the run output dir (never the checkout) + `test.info().attach`. */
export const shotDir: string =
  process.env.PINVI_E2E_SHOT_DIR ??
  path.join(process.env.PINVI_E2E_OUTPUT_DIR ?? path.resolve(process.cwd(), 'test-results'), 'shots');

const SHARE_URL_BANNER = '[data-testid="new-share-url"] code';

export async function shot(page: Page, id: string, step: string): Promise<void> {
  const safe = `${id}-${step}`.replace(/[^A-Za-z0-9._-]+/g, '_');
  const file = path.join(shotDir, `${safe}.png`);
  await fs.mkdir(shotDir, { recursive: true });
  // The one-time share URL banner carries the share token — always masked.
  await page.screenshot({ path: file, fullPage: false, mask: [page.locator(SHARE_URL_BANNER)] });
  try {
    await test.info().attach(`${safe}.png`, { path: file, contentType: 'image/png' });
  } catch {
    // outside a test (globalSetup / hooks without a test): file on disk is enough
  }
}

/* ------------------------------------------------------------------ misc */

/** Short unique suffix so repeated runs never collide on `[e2e]` titles. */
export function runTag(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
}

/** `[e2e] <label> <tag>` */
export function e2eTitle(label: string): string {
  return `${e2ePrefix} ${label} ${runTag()}`;
}

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

/** `YYYY-MM-DD` for today + offsetDays in the runner's local calendar (same as the UI's `today`). */
export function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setHours(12, 0, 0, 0);
  d.setDate(d.getDate() + offsetDays);
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}
