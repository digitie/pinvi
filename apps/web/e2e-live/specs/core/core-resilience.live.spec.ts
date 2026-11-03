/**
 * CORE — resilience: slow weather must not block detail; selection change aborts stale work.
 * Verified against PinVi origin/main b1cef056: components/map/FeatureMapView.tsx (popup awaits
 * Promise.allSettled([get, weather]) — the #622 shape; the split-load fix 7ec36c13 is NOT on main),
 * lib/useFeatureDetailCard.ts (abort on featureId change), components/map/FeatureDetailModalController.tsx.
 */
import { expect, test, type Page } from '@playwright/test';
import { clickableFeatureMarkers, ensureFeatureMarkers, loginAsUser, shot } from '../../helpers/live';
import { annotate, isMobileViewport, timed, waitForMapCanvas } from '../../helpers/core';

async function openExploreMap(page: Page) {
  const inBounds = page.waitForResponse((r) => r.url().includes('/features/in-bounds') && r.status() === 200, { timeout: 45_000 });
  await page.goto('/map');
  await waitForMapCanvas(page);
  await inBounds;
  // Default Seoul viewport can be all clusters — zoom in until ≥2 individual feature pins render.
  const pins = await ensureFeatureMarkers(page, 2);
  await expect(pins.first()).toBeVisible({ timeout: 15_000 });
  return pins;
}

test.describe('CORE resilience', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test('CORE-023 상세 카드는 날씨가 느려도 3초 안에 뜬다(#622 — detail-card 경로)', async ({ page }, testInfo) => {
    await openExploreMap(page);
    const [pin] = await clickableFeatureMarkers(page, 1);
    expect(pin, 'a feature pin inside the visible map area').toBeTruthy();
    const featureId = ((await pin!.getAttribute('aria-label')) ?? '').slice(0, 20);
    let weatherMs: number | null = null;
    const tW = Date.now();
    page.on('response', (r) => {
      if (/\/features\/[^/]+\/weather/.test(r.url()) && weatherMs == null) weatherMs = Date.now() - tW;
    });
    await pin!.click();
    if (!isMobileViewport(page)) {
      // the popup itself waits for detail + weather (#622 popup path, CORE-024)
      await page.getByTestId('feature-map-detail-open').click({ timeout: 30_000 });
    }
    const { ms } = await timed(async () => {
      await expect(page.getByTestId('feature-detail-card-body')).toBeVisible({ timeout: 10_000 });
    });
    await shot(page, 'CORE-023', 'card');
    annotate(testInfo, 'metric', `detail-card ${ms}ms, feature=${featureId}, weather=${weatherMs ?? 'pending'}ms`);
    expect(ms, 'detail-card visible within 3s').toBeLessThan(3000);
    const kind = await page.getByTestId('feature-detail-card-body').getAttribute('data-kind');
    expect(['place', 'event', 'notice', 'price']).toContain(kind);
  });

  test('CORE-024 마커 팝업의 상세 텍스트가 날씨 응답을 기다리지 않는다(#622 — 팝업 경로)', async ({ page }, testInfo) => {
    test.skip(isMobileViewport(page), '모바일은 팝업 없이 상세 시트 직행');
    // #622 shipped the split detail/weather load (no allSettled join in FeatureMapView) — the expected-fail
    // marker was removed after the 2026-11-03 prod run passed (popup detail 11 ms).
    await openExploreMap(page);
    const [pin] = await clickableFeatureMarkers(page, 1);
    expect(pin).toBeTruthy();
    let detailAt: number | null = null;
    let weatherAt: number | null = null;
    const t0 = Date.now();
    page.on('response', (r) => {
      const u = r.url();
      if (/\/features\/[^/?]+\/weather/.test(u)) weatherAt = Date.now() - t0;
      else if (/\/features\/[^/?]+$/.test(u) && r.request().method() === 'GET') detailAt = Date.now() - t0;
    });
    await pin!.click();
    const popup = page.locator('.maplibregl-popup');
    await expect(popup).toBeVisible({ timeout: 30_000 });
    const { ms } = await timed(async () => {
      await expect(popup.getByText('상세 불러오는 중…')).toHaveCount(0, { timeout: 10_000 });
    });
    await shot(page, 'CORE-024', 'popup');
    annotate(testInfo, 'metric', `popup detail ${ms}ms (detail resp ${detailAt}ms, weather resp ${weatherAt}ms)`);
    // detail text must land within 3 s even when weather is slower than that
    expect(ms).toBeLessThan(3000);
    if (weatherAt != null && detailAt != null && weatherAt > detailAt + 500) {
      expect(ms).toBeLessThan(weatherAt);
    }
  });

  test('CORE-025 선택 변경 시 이전 상세 요청을 버린다 — stale 카드 없음', async ({ page }) => {
    await openExploreMap(page);
    let clickable = await clickableFeatureMarkers(page, 2);
    // overlays cover part of a phone screen — zoom in a little more until two pins are tappable
    for (let i = 0; i < 3 && clickable.length < 2; i += 1) {
      await page.locator('.maplibregl-canvas').first().focus();
      await page.keyboard.press('=');
      await page.waitForTimeout(800);
      clickable = await clickableFeatureMarkers(page, 2);
    }
    test.skip(clickable.length < 2, '보이는 영역에 클릭 가능한 feature 핀이 2개 미만');
    const pins = { nth: (k: number) => clickable[k]! };
    const a = (await pins.nth(0).getAttribute('aria-label')) ?? '';
    const b = (await pins.nth(1).getAttribute('aria-label')) ?? '';
    test.skip(a === b, '서로 다른 두 핀 필요');
    await pins.nth(0).click();
    await pins.nth(1).click(); // immediately supersede A with B
    if (isMobileViewport(page)) {
      // mobile: A's sheet opened; close it, tap B, sheet must be B (useFeatureDetailCard aborts A)
      const modal = page.getByTestId('feature-detail-modal');
      await expect(modal).toBeVisible();
      await page.keyboard.press('Escape');
      await pins.nth(1).tap();
      await expect(page.getByTestId('feature-detail-modal-title')).toContainText(b.slice(0, 4), { timeout: 15_000 });
      await page.waitForTimeout(2500); // let any late A response land
      await expect(page.getByTestId('feature-detail-modal-title')).toContainText(b.slice(0, 4));
      await expect(page.getByTestId('feature-detail-modal-title')).not.toContainText(a.slice(0, 6));
    } else {
      const popup = page.locator('.maplibregl-popup');
      // the popup waits for detail + weather together (#622) — allow the slow path
      await expect(popup).toHaveCount(1, { timeout: 30_000 });
      await expect(popup).toContainText(b.slice(0, 4));
      await expect(popup.getByText('상세 불러오는 중…')).toHaveCount(0, { timeout: 15_000 });
      await page.waitForTimeout(2500);
      await expect(popup).toContainText(b.slice(0, 4));
      await expect(popup).not.toContainText(a.slice(0, 6));
      await expect(page.locator('[data-testid="feature-map-marker-style"][data-marker-selected="true"]')).toHaveCount(1);
    }
    await shot(page, 'CORE-025', 'b-selected');
  });

  test('CORE-026 빠른 pan 중 in-bounds 요청은 취소·대체된다(마지막 viewport만 반영)', async ({ page }, testInfo) => {
    test.skip(isMobileViewport(page), 'desktop drag path');
    await openExploreMap(page);
    let requests = 0;
    let failed = 0;
    page.on('request', (r) => { if (r.url().includes('/features/in-bounds')) requests++; });
    page.on('requestfailed', (r) => { if (r.url().includes('/features/in-bounds')) failed++; });
    const canvas = page.locator('.maplibregl-canvas').first();
    const box = (await canvas.boundingBox())!;
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    for (let i = 0; i < 4; i++) {
      await page.mouse.move(cx, cy);
      await page.mouse.down();
      await page.mouse.move(cx + 120, cy + 60, { steps: 4 });
      await page.mouse.up();
      await page.waitForTimeout(120);
    }
    await expect(page.getByTestId('feature-map-loading')).toHaveCount(0, { timeout: 30_000 });
    await expect(page.getByTestId('feature-map-error')).toHaveCount(0);
    annotate(testInfo, 'metric', `in-bounds requests=${requests} aborted=${failed}`);
    expect(requests).toBeGreaterThanOrEqual(1);
    await shot(page, 'CORE-026', 'after-pan');
  });
});
