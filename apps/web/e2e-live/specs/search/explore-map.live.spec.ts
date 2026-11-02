/**
 * SRCH-042..048 — explore map (/map): in-bounds loading, clusters, marker → card, mobile sheet, height (#619).
 * UI source: apps/web/components/map/FeatureMapView.tsx (feature-map, feature-map-loading/-empty/-error,
 * sr-only legend feature-map-marker-style with data-kind/data-marker-source/data-feature-id, popup
 * feature-map-detail-open), apps/web/app/(app)/map/page.tsx (heading '탐색 지도').
 */
import { expect, test } from '@playwright/test';
import { loginAsUser, shot } from '../../helpers/live';
import {
  clickFeatureMarker,
  desktopOnly,
  dragMap,
  explore,
  gotoExplore,
  isMobileProject,
  mobileOnly,
  modal,
  openDetailFromPopup,
  readInBounds,
  wheelZoom,
} from '../../helpers/search';

test.describe('SRCH explore map (/map)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test('SRCH-042 진입 in-bounds + 드래그 재조회', async ({ page }) => {
    const first = await gotoExplore(page);
    expect(first.status()).toBe(200);
    const a = await readInBounds(first);
    const legendCount = await explore.legend(page).count();
    expect.soft(legendCount, 'markers rendered for the initial viewport').toBeGreaterThan(0);
    const second = await dragMap(page, -320, -160);
    expect(second, 'a new in-bounds request after drag').not.toBeNull();
    const b = await readInBounds(second!);
    expect(second!.status()).toBe(200);
    expect(b.bbox).not.toBe(a.bbox);
    await expect(explore.loading(page)).toBeHidden({ timeout: 30_000 });
    await expect(explore.error(page)).toHaveCount(0);
    await shot(page, 'SRCH-042', 'after-drag');
  });

  test('SRCH-043 줌 아웃 → 클러스터, 줌 인 → feature 마커', async ({ page }) => {
    desktopOnly();
    await gotoExplore(page);
    await wheelZoom(page, 5);
    await expect(explore.loading(page)).toBeHidden({ timeout: 30_000 });
    const clusters = page.locator('[data-testid="feature-map-marker-style"][data-marker-source="cluster"]');
    expect.soft(await clusters.count(), 'clusters at regional zoom').toBeGreaterThan(0);
    await shot(page, 'SRCH-043', 'zoomed-out');
    await wheelZoom(page, -9);
    await expect(explore.loading(page)).toBeHidden({ timeout: 30_000 });
    const features = page.locator('[data-testid="feature-map-marker-style"][data-kind="feature"]');
    expect.soft(await features.count(), 'individual features at street zoom').toBeGreaterThan(0);
    await shot(page, 'SRCH-043', 'zoomed-in');
  });

  test('SRCH-044 마커 클릭 → 팝업 카드', async ({ page }) => {
    desktopOnly();
    await gotoExplore(page);
    await wheelZoom(page, -4);
    await expect(explore.loading(page)).toBeHidden({ timeout: 30_000 });
    const features = page.locator('[data-testid="feature-map-marker-style"][data-kind="feature"]');
    const count = await features.count();
    test.skip(count === 0, 'no individual feature markers in this viewport');
    const title = (await features.first().innerText()).trim();
    await clickFeatureMarker(page, title);
    await expect(page.getByTestId('feature-map-detail-open')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(title, { exact: true }).first()).toBeVisible();
    await expect(page.getByText('상세 불러오는 중…')).toBeHidden({ timeout: 15_000 });
    await shot(page, 'SRCH-044', 'popup');
    const { elapsedMs } = await openDetailFromPopup(page);
    expect.soft(elapsedMs).toBeLessThan(3_000);
    await expect(modal.title(page)).toContainText(title.slice(0, 6));
  });

  test('SRCH-045 모바일 마커 탭 → 상세 시트 바로', async ({ page }) => {
    mobileOnly();
    await gotoExplore(page);
    await wheelZoom(page, -4);
    await expect(explore.loading(page)).toBeHidden({ timeout: 30_000 });
    const features = page.locator('[data-testid="feature-map-marker-style"][data-kind="feature"]');
    test.skip((await features.count()) === 0, 'no individual feature markers in this viewport');
    const title = (await features.first().innerText()).trim();
    await clickFeatureMarker(page, title);
    await expect(modal.root(page)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('feature-map-detail-open')).toHaveCount(0);
    await shot(page, 'SRCH-045', 'mobile-sheet');
  });

  test('SRCH-046 지도 높이가 컨테이너를 채운다(#619)', async ({ page }, ti) => {
    await gotoExplore(page);
    const viewport = page.viewportSize()!;
    const mapBox = await explore.map(page).boundingBox();
    const canvasBox = await explore.canvas(page).boundingBox();
    expect(mapBox).not.toBeNull();
    expect(canvasBox).not.toBeNull();
    ti.annotations.push({ type: 'layout', description: `${isMobileProject(ti) ? 'mobile' : 'desktop'} map=${Math.round(mapBox!.height)} canvas=${Math.round(canvasBox!.height)} vh=${viewport.height}` });
    expect(canvasBox!.height).toBeGreaterThanOrEqual(360);
    expect(canvasBox!.height, 'canvas fills the map box (not stuck at 360px min-h)').toBeGreaterThanOrEqual(mapBox!.height * 0.85);
    expect(mapBox!.height).toBeGreaterThanOrEqual(viewport.height * 0.5);
    const docHeight = await page.evaluate(() => document.documentElement.scrollHeight);
    expect(mapBox!.y + mapBox!.height, 'map bottom inside the document').toBeLessThanOrEqual(docHeight + 1);
    await shot(page, 'SRCH-046', 'layout');
  });

  test('SRCH-048 범위 안 이벤트/공지 → kind별 상세', async ({ page }, ti) => {
    desktopOnly();
    const first = await gotoExplore(page);
    let { items } = await readInBounds(first);
    let target = items.find((i) => (i.kind === 'event' || i.kind === 'notice') && i.coord);
    if (!target) {
      const after = await wheelZoom(page, 3);
      if (after) ({ items } = await readInBounds(after));
      target = items.find((i) => (i.kind === 'event' || i.kind === 'notice') && i.coord);
    }
    if (!target) {
      ti.annotations.push({ type: 'data', description: 'no event/notice in sampled viewports — skipped' });
      test.skip(true, 'no event/notice feature in viewport');
      return;
    }
    await clickFeatureMarker(page, target.name);
    const { card } = await openDetailFromPopup(page);
    await expect(modal.body(page)).toHaveAttribute('data-kind', card.kind);
    if (card.kind === 'event') {
      expect.soft((await modal.field(page, 'period').count()) + (await modal.field(page, 'venue').count())).toBeGreaterThan(0);
    } else if (card.kind === 'notice') {
      expect.soft((await modal.field(page, 'period').count()) + (await modal.field(page, 'notice-body').count())).toBeGreaterThan(0);
    }
    await shot(page, 'SRCH-048', card.kind);
  });
});
