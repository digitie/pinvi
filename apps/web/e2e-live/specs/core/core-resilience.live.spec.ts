/**
 * CORE — resilience: slow weather must not block detail; selection change aborts stale work.
 * Verified against PinVi origin/main b1cef056: components/map/FeatureMapView.tsx (popup awaits
 * Promise.allSettled([get, weather]) — the #622 shape; the split-load fix 7ec36c13 is NOT on main),
 * lib/useFeatureDetailCard.ts (abort on featureId change), components/map/FeatureDetailModalController.tsx.
 */
import { expect, test, type Page } from '@playwright/test';
import {
  clickableFeatureMarkers,
  dismissFeaturePopup,
  ensureFeatureMarkers,
  loginAsUser,
  shot,
} from '../../helpers/live';
import { annotate, isMobileViewport, timed, waitForMapCanvas } from '../../helpers/core';

async function openExploreMap(page: Page) {
  const inBounds = page.waitForResponse(
    (r) => r.url().includes('/features/in-bounds') && r.status() === 200,
    { timeout: 45_000 },
  );
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

  test('CORE-023 상세 본문 또는 정본 서비스 저하를 3초 안에 표시', async ({ page }, testInfo) => {
    await openExploreMap(page);
    const [pin] = await clickableFeatureMarkers(page, 1);
    expect(pin).toBeTruthy();
    let code = 0;
    const { ms } = await timed(async () => {
      const isCardRequest = (req: import('@playwright/test').Request) => {
        const url = new URL(req.url());
        return (
          req.method() === 'GET' &&
          url.pathname.endsWith('/detail-card') &&
          !url.searchParams.has('providers')
        );
      };
      if (!isMobileViewport(page)) {
        const popupRequest = page.waitForRequest(isCardRequest);
        await pin!.click();
        await popupRequest;
      }
      const request = page.waitForRequest(isCardRequest);
      if (isMobileViewport(page)) await pin!.click();
      else await page.getByTestId('feature-map-detail-open').click();
      const res = await (await request).response();
      expect(res).not.toBeNull();
      code = res!.status();
      const payload = await res!.json();
      if (code === 200) {
        const body = page.getByTestId('feature-detail-card-body');
        await expect(body).toBeVisible();
        await expect(body).toHaveAttribute('data-feature-id', payload.data.feature_id);
        await expect(body).toHaveAttribute('data-kind', payload.data.kind);
      } else {
        expect(code).toBe(503);
        expect(payload.error.code).toBe('FEATURE_SERVICE_UNAVAILABLE');
        await expect(page.getByTestId('feature-detail-modal').getByRole('alert')).toBeVisible();
      }
    });
    annotate(testInfo, 'metric', 'detail-card ' + ms + 'ms, HTTP ' + code);
    expect(ms).toBeLessThan(3000);
    await shot(page, 'CORE-023', 'card');
  });

  test('CORE-024 팝업의 제한된 상세가 느린 날씨를 기다리지 않는다', async ({ page }, testInfo) => {
    test.skip(isMobileViewport(page), '모바일은 상세 시트 직행');
    await openExploreMap(page);
    const [pin] = await clickableFeatureMarkers(page, 1);
    expect(pin).toBeTruthy();
    const response = page.waitForResponse((res) => {
      const url = new URL(res.url());
      return (
        res.request().method() === 'GET' &&
        url.pathname.endsWith('/detail-card') &&
        !url.searchParams.has('providers')
      );
    });
    let code = 0;
    const { ms } = await timed(async () => {
      await pin!.click();
      const popup = page.getByTestId('feature-map-popup');
      await expect(popup).toBeVisible();
      const res = await response;
      code = res.status();
      const payload = await res.json();
      if (code === 200) {
        await expect(popup).toHaveAttribute('data-feature-id', payload.data.feature_id);
        await expect(popup).toHaveAttribute('data-detail-feature-id', payload.data.feature_id);
      } else {
        expect(code).toBe(503);
        expect(payload.error.code).toBe('FEATURE_SERVICE_UNAVAILABLE');
        await expect(popup.getByRole('alert')).toBeVisible();
      }
      await expect(popup.getByText('상세 불러오는 중…')).toHaveCount(0);
    });
    annotate(testInfo, 'metric', 'popup detail ' + ms + 'ms, HTTP ' + code);
    expect(ms).toBeLessThan(3000);
    await shot(page, 'CORE-024', 'popup');
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
    // desktop: immediately supersede A with B. Mobile: A's sheet now covers the map — the mobile branch
    // below closes it and taps B.
    if (!isMobileViewport(page)) {
      const uncovered = await pins.nth(1).evaluate((el) => {
        const r = el.getBoundingClientRect(),
          top = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
        return top === el || el.contains(top);
      });
      if (!uncovered)
        await page
          .getByTestId('feature-map-popup')
          .getByRole('button', { name: '닫기', exact: true })
          .click();
      await pins.nth(1).click();
    }
    if (isMobileViewport(page)) {
      // mobile: A's sheet opened; close it, tap B, sheet must be B (useFeatureDetailCard aborts A)
      const modal = page.getByTestId('feature-detail-modal');
      await expect(modal).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(modal).toHaveCount(0);
      await dismissFeaturePopup(page); // the selection popup stays over the map after the sheet closes
      await pins.nth(1).tap();
      const popup = page.getByTestId('feature-map-popup');
      const idB = await popup.getAttribute('data-feature-id');
      expect(idB).toBeTruthy();
      await expect(page.getByTestId('feature-detail-card-body')).toHaveAttribute(
        'data-feature-id',
        idB!,
      );
      await expect(page.getByTestId('feature-detail-modal-title')).toContainText(b.slice(0, 4), {
        timeout: 15_000,
      });
      await page.waitForTimeout(2500); // 기존 정본 예산 이후에도 B 본문 ID 유지
      await expect(page.getByTestId('feature-detail-card-body')).toHaveAttribute(
        'data-feature-id',
        idB!,
      );
      await expect(page.getByTestId('feature-detail-modal-title')).toContainText(b.slice(0, 4));
      await expect(page.getByTestId('feature-detail-modal-title')).not.toContainText(a.slice(0, 6));
    } else {
      const popup = page.getByTestId('feature-map-popup');
      const idB = await popup.getAttribute('data-feature-id');
      expect(idB).toBeTruthy();
      await expect(popup).toHaveAttribute('data-detail-feature-id', idB!);
      // the popup waits for detail + weather together (#622) — allow the slow path
      await expect(popup).toHaveCount(1, { timeout: 30_000 });
      await expect(popup).toContainText(b.slice(0, 4));
      await expect(popup.getByText('상세 불러오는 중…')).toHaveCount(0, { timeout: 15_000 });
      await page.waitForTimeout(2500);
      await expect(popup).toContainText(b.slice(0, 4));
      await expect(popup).not.toContainText(a.slice(0, 6));
      await expect(
        page.locator('[data-testid="feature-map-marker-style"][data-marker-selected="true"]'),
      ).toHaveCount(1);
    }
    await shot(page, 'CORE-025', 'b-selected');
  });

  test('CORE-026 빠른 pan 중 in-bounds 요청은 취소·대체된다(마지막 viewport만 반영)', async ({
    page,
  }, testInfo) => {
    test.skip(isMobileViewport(page), 'desktop drag path');
    await openExploreMap(page);
    let requests = 0;
    let failed = 0;
    page.on('request', (r) => {
      if (r.url().includes('/features/in-bounds')) requests++;
    });
    page.on('requestfailed', (r) => {
      if (r.url().includes('/features/in-bounds')) failed++;
    });
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
