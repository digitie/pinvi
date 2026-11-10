/**
 * CORE — accessibility smoke + perf smoke.
 * Verified against origin/main b1cef056: app/layout.tsx (lang=ko), app/(auth)/layout.tsx (main#main,
 * PublicChrome header/footer), components/app/AppShell.tsx (nav aria-labels), app/globals.css (.focus-ring).
 * axe: @axe-core/playwright is an apps/web devDependency (installed by the runner's npm ci).
 */
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { createTrip, deleteTrip, e2ePrefix, loginAsUser, searchAndAddPlace, shot } from '../../helpers/live';
import { annotate, isMobileViewport, PLACES, timed, tripPins, waitForMapCanvas } from '../../helpers/core';

async function focusVisibleOutline(page: Page, selector: string) {
  return page.evaluate((sel) => {
    const el = document.querySelector<HTMLElement>(sel);
    if (!el) return null;
    const cs = getComputedStyle(el);
    return { style: cs.outlineStyle, width: parseFloat(cs.outlineWidth), matches: el.matches(':focus-visible') };
  }, selector);
}

test.describe('CORE a11y', () => {
  test('CORE-027 랜드마크 — lang=ko, main 1개, h1 1개, 셸 nav 라벨', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('html')).toHaveAttribute('lang', 'ko');
    await expect(page.locator('main#main')).toHaveCount(1);
    await expect(page.getByRole('banner')).toHaveCount(1);
    await expect(page.getByRole('contentinfo')).toHaveCount(1);
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
    await loginAsUser(page);
    for (const path of ['/trips', '/map']) {
      await page.goto(path);
      await expect(page.locator('main'), path).toHaveCount(1);
      await expect(page.getByRole('heading', { level: 1 }), path).toHaveCount(1);
      if (isMobileViewport(page)) {
        await expect(page.locator('nav[aria-label="주요 메뉴"]'), path).toBeVisible();
      } else {
        await expect(page.locator('nav[aria-label="사용자 메뉴"]'), path).toBeVisible();
        await expect(page.locator('nav[aria-label="사용자 메뉴"] [aria-current="page"]')).toHaveCount(1);
      }
    }
    await shot(page, 'CORE-027', 'map');
  });

  test('CORE-028 주요 컨트롤 포커스 가시성(.focus-ring = focus-visible outline 2px)', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByTestId('login-submit')).toBeEnabled();
    await page.getByTestId('login-password').focus();
    await page.keyboard.press('Tab'); // → submit
    await expect(page.getByTestId('login-submit')).toBeFocused();
    const submit = await focusVisibleOutline(page, '[data-testid="login-submit"]');
    expect(submit?.matches, 'submit :focus-visible').toBe(true);
    expect(submit!.style).not.toBe('none');
    expect(submit!.width).toBeGreaterThan(0);
    await loginAsUser(page);
    await page.goto('/map');
    await page.getByTestId('map-my-location').focus();
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Tab');
    const loc = await focusVisibleOutline(page, '[data-testid="map-my-location"]');
    expect(loc?.matches).toBe(true);
    expect(loc!.style).not.toBe('none');
    if (!isMobileViewport(page)) {
      const nav = page.getByTestId('app-nav--trips');
      await nav.focus();
      await page.keyboard.press('Shift+Tab');
      await page.keyboard.press('Tab');
      const navStyle = await focusVisibleOutline(page, '[data-testid="app-nav--trips"]');
      expect(navStyle?.style).not.toBe('none');
    }
    await shot(page, 'CORE-028', 'focus');
  });

  test('CORE-029 axe-core critical=0 on /login, /trips, /map', async ({ page }, testInfo) => {
    const pages: Array<[string, () => Promise<void>]> = [
      ['/login', async () => { await page.goto('/login'); await expect(page.getByTestId('login-submit')).toBeEnabled(); }],
      ['/trips', async () => { await loginAsUser(page); await expect(page.getByRole('heading', { name: '여행', exact: true })).toBeVisible(); }],
      ['/map', async () => { await page.goto('/map'); await waitForMapCanvas(page); }],
    ];
    for (const [path, open] of pages) {
      await open();
      const result = await new AxeBuilder({ page }).analyze();
      const critical = result.violations.filter((v) => v.impact === 'critical');
      const serious = result.violations.filter((v) => v.impact === 'serious');
      annotate(testInfo, 'axe', `${path}: critical=${critical.length} serious=${serious.length} (${serious.map((v) => v.id).join(',')})`);
      for (const v of critical) {
        annotate(testInfo, 'axe-critical', `${path} ${v.id}: ${v.nodes.slice(0, 5).map((n) => n.target.join(' ')).join(' | ')}`);
      }
      // soft: scan every page so one run reports all three; any critical still fails the test.
      expect.soft(critical.map((v) => `${v.id}×${v.nodes.length}`), `${path} critical violations`).toEqual([]);
    }
  });
});

test.describe('CORE perf smoke', () => {
  let tripId: string | null = null;
  test.afterEach(async ({ page }) => {
    if (tripId) await deleteTrip(page, tripId).catch(() => undefined);
    tripId = null;
  });

  test('CORE-030 TTI 기록 — 여행 목록 / 여행 상세 / 탐색 지도 (soft thresholds)', async ({ page }, testInfo) => {
    await loginAsUser(page);
    const { id } = await createTrip(page, { title: `${e2ePrefix} CORE-030 ${Date.now()}`, start: '2026-11-05', end: '2026-11-06' });
    tripId = id;
    await page.goto(`/trips/${id}`);
    await searchAndAddPlace(page, 1, PLACES.south);

    const list = await timed(async () => {
      await page.goto('/trips');
      await expect(page.getByTestId('trip-list')).toBeVisible({ timeout: 30_000 });
    });
    const detail = await timed(async () => {
      await page.goto(`/trips/${id}`);
      await expect(page.getByTestId('trip-detail-shell')).toBeVisible({ timeout: 30_000 });
      await waitForMapCanvas(page);
      await expect(tripPins(page)).toHaveCount(1, { timeout: 30_000 });
    });
    const explore = await timed(async () => {
      const inBounds = page.waitForResponse((r) => r.url().includes('/features/in-bounds') && r.status() === 200, { timeout: 45_000 });
      await page.goto('/map');
      await waitForMapCanvas(page);
      await inBounds;
      await expect(page.locator('.maplibregl-marker[role="button"]').first()).toBeVisible({ timeout: 30_000 });
    });
    const metrics = { tripsListMs: list.ms, tripViewMs: detail.ms, exploreMapMs: explore.ms };
    annotate(testInfo, 'perf', JSON.stringify(metrics));
    await testInfo.attach('CORE-030-perf.json', { body: JSON.stringify(metrics, null, 2), contentType: 'application/json' });
    // soft thresholds: annotate when slow, hard-fail only on pathological values
    for (const [k, v] of Object.entries(metrics)) {
      if (v > 5000) annotate(testInfo, 'slow', `${k}=${v}ms > 5s soft threshold`);
      expect(v, `${k} hard ceiling`).toBeLessThan(30_000);
    }
    await shot(page, 'CORE-030', 'explore');
  });
});
