/**
 * CORE — mobile UX (runs under the 390x844 project; desktop project skips where noted).
 * Selectors verified against PinVi origin/main b1cef056: components/ui/Dialog.tsx (variant="sheet"),
 * lib/useModalDialog.ts (scroll lock = overflow:clip, focus trap), components/trips/TripDetail.tsx
 * (mobile header '패널 열기/닫기', aside#trip-detail-panel, day tabs), components/app/AppShell.tsx.
 */
import { expect, test } from '@playwright/test';
import { clickableFeatureMarkers, createTrip, dismissFeaturePopup, deleteTrip, e2ePrefix, ensureFeatureMarkers, loginAsUser, searchAndAddPlace, shot } from '../../helpers/live';
import {
  annotate,
  intersects,
  isMobileViewport,
  PLACES,
  tripPins,
  waitForMapCanvas,
  type Box,
} from '../../helpers/core';

test.describe('CORE mobile', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isMobileViewport(page), 'mobile project only (390x844)');
    await loginAsUser(page);
  });

  test('CORE-019 상세 바텀시트 — 본문 스크롤, 배경 스크롤 잠금, 닫기 경로 3종', async ({ page }) => {
    const inBounds = page.waitForResponse((r) => r.url().includes('/features/in-bounds') && r.status() === 200, { timeout: 45_000 });
    await page.goto('/map');
    await waitForMapCanvas(page);
    await inBounds;
    // tap a real feature pin that is on screen and not under an overlay (not a cluster-of-one)
    await ensureFeatureMarkers(page, 1);
    const [pin] = await clickableFeatureMarkers(page, 1);
    expect(pin, 'a tappable feature pin').toBeTruthy();
    await pin!.tap();
    const modal = page.getByTestId('feature-detail-modal');
    await expect(modal).toBeVisible({ timeout: 15_000 });
    await expect(modal).toHaveAttribute('role', 'dialog');
    // body scroll lock (useModalDialog): overflow clip on html/body while open
    await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('clip');
    // sheet body is the scroll container; it must not overflow the viewport
    const sheet = (await modal.boundingBox()) as Box;
    const vp = page.viewportSize()!;
    expect(sheet.y + sheet.height).toBeLessThanOrEqual(vp.height + 1);
    expect(sheet.width).toBeLessThanOrEqual(vp.width + 1);
    const body = modal.locator('.overflow-auto').first();
    const scrollable = await body.evaluate((el) => el.scrollHeight > el.clientHeight);
    if (scrollable) {
      await body.evaluate((el) => el.scrollBy(0, 200));
      expect(await body.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
    }
    await shot(page, 'CORE-019', 'sheet');
    // 1) Escape
    await page.keyboard.press('Escape');
    await expect(modal).toHaveCount(0);
    await expect.poll(() => page.evaluate(() => document.body.style.overflow)).not.toBe('clip');
    // 2) close button — the camera flies to the selected pin; wait for it to settle and re-pick a tappable pin
    const retap = async () => {
      await dismissFeaturePopup(page); // selection popup stays after the sheet closes and covers pins
      await page.waitForTimeout(1500);
      const [p] = await clickableFeatureMarkers(page, 1);
      expect(p, 'a tappable feature pin').toBeTruthy();
      await p!.tap();
    };
    await retap();
    await expect(modal).toBeVisible();
    await page.getByTestId('feature-detail-modal-close').tap();
    await expect(modal).toHaveCount(0);
    // 3) backdrop
    await retap();
    await expect(modal).toBeVisible();
    await page.getByTestId('feature-detail-modal-backdrop').click({ position: { x: 10, y: 10 } });
    await expect(modal).toHaveCount(0);
  });

  test.describe('with a seeded [e2e] trip', () => {
    let tripId: string | null = null;

    test.beforeEach(async ({ page }) => {
      const { id } = await createTrip(page, {
        title: `${e2ePrefix} CORE-mobile ${Date.now()}`,
        start: '2026-11-05',
        end: '2026-11-06',
      });
      tripId = id;
      await page.goto(`/trips/${id}`);
      await searchAndAddPlace(page, 1, PLACES.north);
      await searchAndAddPlace(page, 1, PLACES.south);
    });

    test.afterEach(async ({ page }) => {
      if (tripId) await deleteTrip(page, tripId).catch(() => undefined);
      tripId = null;
    });

    test('CORE-020 일자 패널 열기/일자 전환/닫기 (스와이프 미구현 → 버튼 경로)', async ({ page }, testInfo) => {
      await page.goto(`/trips/${tripId}`);
      await waitForMapCanvas(page);
      const toggle = page.getByRole('button', { name: '패널 열기' });
      await expect(toggle).toBeVisible();
      await expect(toggle).toHaveAttribute('aria-expanded', 'false');
      await toggle.tap();
      const panel = page.getByTestId('trip-detail-panel');
      await expect(panel).toBeVisible();
      await expect(page.getByRole('button', { name: '패널 닫기' }).first()).toHaveAttribute('aria-expanded', 'true');
      // the dated 2-day trip already has 2일차; add it through the drawer only when the slot is free
      const addInDrawer = page.getByTestId('trip-add-day-drawer');
      if (await addInDrawer.isEnabled()) await addInDrawer.tap();
      const day2 = page.getByRole('tab', { name: '2일차', exact: true });
      await expect(day2).toBeVisible({ timeout: 15_000 });
      await day2.tap();
      await expect(day2).toHaveAttribute('aria-selected', 'true');
      await expect(page.getByRole('tab', { name: '1일차', exact: true })).toHaveAttribute('aria-selected', 'false');
      // swipe gesture on the drawer should NOT break anything (no handler exists — documented gap)
      await page.touchscreen.tap(10, 400);
      await shot(page, 'CORE-020', 'day2');
      await page.locator('button[aria-controls="trip-detail-panel"][aria-expanded="true"]:visible').first().tap();
      await expect(panel).toBeHidden();
      annotate(testInfo, 'gap', 'TripDetail.tsx에 스와이프 제스처 핸들러 없음 — 버튼 경로만 검증');
    });

    test('CORE-021 통계 칩이 남쪽 핀을 가리지 않는다(#623)', async ({ page }) => {
      // #623의 조건부 하단 여백 회귀. 실제 SVG 핀을 통계 칩이 가리지 않아야 한다.
      await page.goto(`/trips/${tripId}`);
      await waitForMapCanvas(page);
      const pins = tripPins(page);
      await expect(pins).toHaveCount(2, { timeout: 15_000 });
      await page.waitForTimeout(1500);
      const stats = (await page.getByTestId('trip-map-stats').boundingBox()) as Box;
      const n = await pins.count();
      let southern: Box | null = null;
      for (let i = 0; i < n; i++) {
        const b = (await pins.nth(i).boundingBox()) as Box;
        if (!southern || b.y > southern.y) southern = b;
      }
      await shot(page, 'CORE-021', 'stats-vs-pin');
      expect(intersects(southern!, stats, 4), 'southern pin overlaps stats chips (#623)').toBe(false);
    });

    test('CORE-022 오버레이 키보드 Tab 순서 — 검색창이 캔버스·마커보다 먼저', async ({ page }) => {
      await page.goto(`/trips/${tripId}`);
      await waitForMapCanvas(page);
      await expect(tripPins(page)).toHaveCount(2, { timeout: 15_000 });
      // start from the top panel's first control and walk Tab until the search input or canvas gets focus
      await page.getByRole('link', { name: '여행 목록' }).focus();
      const order: string[] = [];
      for (let i = 0; i < 12; i++) {
        await page.keyboard.press('Tab');
        const desc = await page.evaluate(() => {
          const el = document.activeElement as HTMLElement | null;
          if (!el) return 'none';
          return `${el.tagName.toLowerCase()}|${el.getAttribute('aria-label') ?? ''}|${el.className.split(' ')[0] ?? ''}`;
        });
        order.push(desc);
        if (desc.includes('장소·주소 검색') || desc.includes('maplibregl-canvas')) break;
      }
      const searchIdx = order.findIndex((d) => d.includes('장소·주소 검색'));
      const canvasIdx = order.findIndex((d) => d.includes('maplibregl-canvas') || d.includes('maplibregl-marker'));
      expect(searchIdx, `tab order: ${order.join(' > ')}`).toBeGreaterThanOrEqual(0);
      if (canvasIdx >= 0) expect(searchIdx).toBeLessThan(canvasIdx);
    });
  });
});
