/**
 * CORE — auth / session (live prod, no mocks).
 * Selectors verified against PinVi origin/main b1cef056 (apps/web/app/(auth)/login/page.tsx,
 * apps/web/lib/api.ts, packages/api-client/src/client.ts, apps/api/app/api/v1/auth.py).
 */
import { expect, test } from '@playwright/test';
import {
  baseURL,
  createTrip,
  deleteTrip,
  e2ePrefix,
  loginAsUser,
  shot,
} from '../../helpers/live';
import {
  annotate,
  discoverApiBase,
  expireAccessCookie,
  hasCookie,
  loginAsUser2,
  logoutViaApi,
  recordConsole,
  requireEnv,
} from '../../helpers/core';

const WRONG_CREDS_MSG = '이메일 또는 비밀번호가 올바르지 않습니다.';

test.describe('CORE auth/session', () => {
  test('CORE-001 로그인 — 하이드레이션 안전 제출(#619)', async ({ page }, testInfo) => {
    const email = requireEnv('PINVI_E2E_USER_EMAIL');
    const password = requireEnv('PINVI_E2E_USER_PASSWORD');
    const rec = recordConsole(page);
    await page.goto('/login');
    const submit = page.getByTestId('login-submit');
    // origin/main: submit is rendered disabled in server HTML and enabled only after hydration
    // (useHydrated). A click before hydration must never native-submit the form and wipe inputs.
    await expect(submit).toBeEnabled({ timeout: 15_000 });
    await page.getByTestId('login-email').fill(email);
    await page.getByTestId('login-password').fill(password);
    await shot(page, 'CORE-001', 'filled');
    await submit.click();
    await expect(page).toHaveURL(/\/trips(?:[?#].*)?$/, { timeout: 20_000 });
    await expect(page.getByRole('heading', { name: '여행', exact: true })).toBeVisible();
    await expect(page).not.toHaveURL(/\/login/);
    const hydrationNoise = rec.errors.filter((e) => /hydrat/i.test(e));
    rec.stop();
    expect(hydrationNoise, 'hydration mismatch console errors').toEqual([]);
    await shot(page, 'CORE-001', 'trips');
    annotate(testInfo, 'verified-against', 'origin/main b1cef056 login/page.tsx useHydrated');
  });

  test('CORE-002 잘못된 비밀번호 — 메시지·URL 유지·쿠키 없음', async ({ page, context }) => {
    const email = requireEnv('PINVI_E2E_USER_EMAIL');
    await page.goto('/login');
    await expect(page.getByTestId('login-submit')).toBeEnabled();
    await page.getByTestId('login-email').fill(email);
    await page.getByTestId('login-password').fill(`wrong-${Date.now()}`);
    await page.getByTestId('login-submit').click();
    const err = page.getByTestId('login-error');
    await expect(err).toBeVisible({ timeout: 15_000 });
    await expect(err).toHaveAttribute('role', 'alert');
    await expect(err).toHaveText(WRONG_CREDS_MSG);
    await expect(page).toHaveURL(/\/login/);
    // the email stays filled (no native form reload), no session cookie was issued
    await expect(page.getByTestId('login-email')).toHaveValue(email);
    expect(await hasCookie(context, 'pinvi_refresh')).toBe(false);
    await shot(page, 'CORE-002', 'error');
  });

  test('CORE-003 로그아웃(API) 뒤 보호 페이지는 /login으로 보낸다', async ({ page, context }, testInfo) => {
    const apiBase = await discoverApiBase(page, () => loginAsUser(page));
    expect(await hasCookie(context, 'pinvi_refresh')).toBe(true);
    const status = await logoutViaApi(page, apiBase);
    expect(status).toBe(204);
    expect(await hasCookie(context, 'pinvi_refresh')).toBe(false);
    await page.goto('/trips');
    // apiClient.onUnauthorized → window.location.href='/login' (lib/api.ts)
    await expect(page).toHaveURL(/\/login/, { timeout: 20_000 });
    await shot(page, 'CORE-003', 'after-logout');
    annotate(testInfo, 'gap', '사용자 UI에 로그아웃 버튼이 없다(admin 전용) — API로 로그아웃');
  });

  test('CORE-004 access 만료(10분) 뒤 자동 갱신 — 쿠키 삭제로 시뮬레이션(#612)', async ({ page, context }, testInfo) => {
    await loginAsUser(page);
    await expireAccessCookie(context);
    expect(await hasCookie(context, 'pinvi_access')).toBe(false);
    const refreshDone = page.waitForResponse(
      (r) => r.url().includes('/auth/refresh') && r.request().method() === 'POST',
      { timeout: 30_000 },
    );
    await page.goto('/trips');
    const refresh = await refreshDone;
    expect(refresh.status(), 'POST /auth/refresh').toBe(200);
    // stayed logged in: list or empty state rendered, never bounced to /login
    await expect(page.getByTestId('trip-list').or(page.getByText('아직 여행이 없습니다.'))).toBeVisible({
      timeout: 20_000,
    });
    await expect(page).not.toHaveURL(/\/login/);
    expect(await hasCookie(context, 'pinvi_access')).toBe(true);
    await shot(page, 'CORE-004', 'refreshed');
    annotate(testInfo, 'note', '실제 11분 대기 변형은 CORE-005(manual)');
  });

  test('CORE-006 두 탭 동시 갱신 조정(Web Locks) — 어느 탭도 로그아웃되지 않는다', async ({ page, context }) => {
    await loginAsUser(page);
    const page2 = await context.newPage();
    await page2.goto('/trips');
    await expect(page2).not.toHaveURL(/\/login/);
    await expireAccessCookie(context);
    const refreshStatuses: number[] = [];
    const collect = (r: import('@playwright/test').Response) => {
      if (r.url().includes('/auth/refresh')) refreshStatuses.push(r.status());
    };
    page.on('response', collect);
    page2.on('response', collect);
    // both tabs hit a 401 at the same instant; refresh tokens rotate, so an unserialised race
    // would make the loser's 401 clear both cookies (client.ts single-flight + navigator.locks).
    await Promise.all([page.goto('/trips'), page2.goto('/map')]);
    await expect(page.getByTestId('trip-list').or(page.getByText('아직 여행이 없습니다.'))).toBeVisible({
      timeout: 20_000,
    });
    await expect(page2.getByTestId('feature-map')).toBeVisible({ timeout: 20_000 });
    await expect(page).not.toHaveURL(/\/login/);
    await expect(page2).not.toHaveURL(/\/login/);
    expect(await hasCookie(context, 'pinvi_refresh')).toBe(true);
    expect(refreshStatuses.length).toBeGreaterThanOrEqual(1);
    expect(refreshStatuses.filter((s) => s === 401)).toEqual([]);
    page.off('response', collect);
    page2.off('response', collect);
    await shot(page2, 'CORE-006', 'tab2-map');
    await page2.close();
  });

  test('CORE-007 비로그인 딥링크 → 로그인 → 원래 여행으로 복귀', async ({ browser, page }, testInfo) => {
    test.fail(true, 'login/page.tsx는 항상 router.push("/trips") — return_to/next 파라미터가 없다 (origin/main b1cef056)');
    await loginAsUser(page);
    const { id } = await createTrip(page, {
      title: `${e2ePrefix} CORE-007 ${Date.now()}`,
      start: '2026-11-05',
      end: '2026-11-08',
    });
    try {
      const fresh = await browser.newContext({ baseURL: baseURL });
      const p = await fresh.newPage();
      await p.goto(`/trips/${id}`);
      await expect(p).toHaveURL(/\/login/, { timeout: 20_000 });
      await expect(p.getByTestId('login-submit')).toBeEnabled();
      await p.getByTestId('login-email').fill(requireEnv('PINVI_E2E_USER_EMAIL'));
      await p.getByTestId('login-password').fill(requireEnv('PINVI_E2E_USER_PASSWORD'));
      await p.getByTestId('login-submit').click();
      await shot(p, 'CORE-007', 'after-login');
      await expect(p).toHaveURL(new RegExp(`/trips/${id}`), { timeout: 20_000 });
      await fresh.close();
    } finally {
      await deleteTrip(page, id);
    }
    annotate(testInfo, 'expected-fail', '현재 동작: /trips로 착지. 복귀 기능 구현 여부는 open question');
  });

  test('CORE-008 비로그인 보호 페이지 접근은 /login으로', async ({ page }) => {
    for (const path of ['/trips', '/map', '/files', '/settings/mcp-tokens']) {
      await page.goto(path);
      await expect(page, path).toHaveURL(/\/login/, { timeout: 20_000 });
    }
    await shot(page, 'CORE-008', 'login');
  });

  test('CORE-009 두 계정 세션 격리 — test2는 test의 [e2e] 여행을 볼 수 없다', async ({ browser, page }) => {
    test.skip(!process.env.PINVI_E2E_USER2_EMAIL, 'PINVI_E2E_USER2_* 미제공');
    await loginAsUser(page);
    const title = `${e2ePrefix} CORE-009 ${Date.now()}`;
    const { id } = await createTrip(page, { title, start: '2026-11-05', end: '2026-11-06' });
    const ctx2 = await browser.newContext({ baseURL: baseURL });
    const p2 = await ctx2.newPage();
    try {
      await loginAsUser2(p2);
      await expect(p2.getByTestId('trip-list').or(p2.getByText('아직 여행이 없습니다.'))).toBeVisible({
        timeout: 20_000,
      });
      await expect(p2.getByTestId('trip-list').getByText(title)).toHaveCount(0);
      await p2.goto(`/trips/${id}`);
      // owner-only trip: TripDetail renders the error panel (403/404), never the owner's data
      await expect(p2.getByTestId('trip-detail-error')).toBeVisible({ timeout: 20_000 });
      await expect(p2.getByRole('heading', { name: title })).toHaveCount(0);
      await shot(p2, 'CORE-009', 'user2-denied');
    } finally {
      await ctx2.close();
      await deleteTrip(page, id);
    }
  });
});
