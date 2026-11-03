/**
 * CORE area-local helpers — thin additions on top of the shared `../helpers/live` contract.
 * Everything here is read-only against prod except `logoutViaApi` (session-only) and the
 * cookie clearing used to simulate access-token expiry (no server state is touched).
 *
 * Credentials come ONLY from env: PINVI_E2E_USER_EMAIL / PINVI_E2E_USER_PASSWORD
 * (second identity: PINVI_E2E_USER2_EMAIL / PINVI_E2E_USER2_PASSWORD). Nothing is logged.
 */
import { expect, type BrowserContext, type ConsoleMessage, type Page, type TestInfo } from '@playwright/test';
import { apiBaseURL, forgetSessions, loginAsUser2, requireEnv } from './live';

export { loginAsUser2, requireEnv };

export const MOBILE_MAX_WIDTH = 600;

/** True under the 390x844 project (or any narrow project). Mirrors `useMobileWebLayout` (<=1023px) loosely. */
export function isMobileViewport(page: Page): boolean {
  return (page.viewportSize()?.width ?? 1440) < MOBILE_MAX_WIDTH;
}

/**
 * Runs `run` (normally the login helper) and returns the API base the app talks to — the shared
 * `apiBaseURL` learns it from the page's own traffic; `PINVI_E2E_API_URL` overrides.
 */
export async function discoverApiBase(page: Page, run: () => Promise<void>): Promise<string> {
  await run();
  return apiBaseURL(page);
}

/** POST /auth/logout with the session cookies (there is no logout control in the user UI — see README). */
export async function logoutViaApi(page: Page, apiBase: string): Promise<number> {
  forgetSessions(); // the shared session cache must not hand this revoked session to the next test
  return page.evaluate(async (api) => {
    const res = await fetch(`${api}/auth/logout`, { method: 'POST', credentials: 'include' });
    return res.status;
  }, apiBase);
}

/** Simulate access-token expiry (10 min TTL, `pinvi_access` httpOnly cookie) without waiting 11 minutes. */
export async function expireAccessCookie(context: BrowserContext): Promise<void> {
  await context.clearCookies({ name: 'pinvi_access' });
}

export async function hasCookie(context: BrowserContext, name: string): Promise<boolean> {
  return (await context.cookies()).some((c) => c.name === name);
}

export interface ConsoleRecorder {
  errors: string[];
  pageErrors: string[];
  stop: () => void;
}

/** Records console errors + uncaught page errors (for tile-decode / worker / hydration checks). */
export function recordConsole(page: Page): ConsoleRecorder {
  const errors: string[] = [];
  const pageErrors: string[] = [];
  const onConsole = (msg: ConsoleMessage) => {
    if (msg.type() === 'error' || msg.type() === 'warning') errors.push(`${msg.type()}: ${msg.text()}`);
  };
  const onPageError = (err: Error) => pageErrors.push(err.message);
  page.on('console', onConsole);
  page.on('pageerror', onPageError);
  return {
    errors,
    pageErrors,
    stop: () => {
      page.off('console', onConsole);
      page.off('pageerror', onPageError);
    },
  };
}

/** Explore-map feature markers (not clusters). Marker roots carry role=button + aria-label=title (vworld-map-web Marker.js). */
export function featureMarkers(page: Page) {
  return page.locator('.maplibregl-marker[role="button"]:not([data-is-cluster="true"])');
}

/** Trip-map POI pins (`PinMarker className="trip-map-marker"`). */
export function tripPins(page: Page) {
  return page.locator('.maplibregl-marker.trip-map-marker');
}

export async function waitForMapCanvas(page: Page): Promise<void> {
  await expect(page.locator('.maplibregl-canvas').first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('vworld-map-fallback')).toHaveCount(0);
}

export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

export function intersects(a: Box, b: Box, gap = 0): boolean {
  return (
    a.x < b.x + b.width + gap &&
    a.x + a.width + gap > b.x &&
    a.y < b.y + b.height + gap &&
    a.y + a.height + gap > b.y
  );
}

export function annotate(testInfo: TestInfo, type: string, description: string): void {
  testInfo.annotations.push({ type, description });
}

/** Timing helper: milliseconds until `fn` resolves. */
export async function timed<T>(fn: () => Promise<T>): Promise<{ ms: number; value: T }> {
  const t0 = Date.now();
  const value = await fn();
  return { ms: Date.now() - t0, value };
}

export const PLACES = {
  north: '영월 고씨굴', // 강원 영월 — 북쪽 핀 (#619 재현 데이터), family: heritage/cave(관광지)
  south: '안동하회마을', // 경북 안동 — 남쪽 핀, family: heritage(국가유산/마을)
  sosu: '소수서원', // 영주, family: heritage
  dosan: '도산서원', // 안동, family: heritage
} as const;
