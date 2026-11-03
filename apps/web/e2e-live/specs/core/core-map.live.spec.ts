/**
 * CORE — map interaction on the explore map (/map) and the trip map (/trips/{id}).
 * Selectors verified against PinVi origin/main b1cef056:
 *   apps/web/components/map/FeatureMapView.tsx, components/trips/TripMapView.tsx, lib/mapFitPadding.ts,
 *   components/map/TransportLayerControls.tsx, vendor vworld-map-web Marker.js / VWorldMapView.web.js,
 *   vworld-map-core vworldStyle.js (attribution text).
 */
import { expect, test, type Page } from '@playwright/test';
import {
  createTrip,
  deleteTrip,
  e2ePrefix,
  ensureFeatureMarkers,
  loginAsUser,
  searchAndAddPlace,
  shot,
} from '../../helpers/live';
import {
  annotate,
  featureMarkers,
  intersects,
  isMobileViewport,
  PLACES,
  recordConsole,
  tripPins,
  waitForMapCanvas,
  type Box,
} from '../../helpers/core';

const ATTRIBUTION = '공간정보 오픈플랫폼 브이월드';

async function openExploreMap(page: Page) {
  const inBounds = page.waitForResponse(
    (r) => r.url().includes('/features/in-bounds') && r.status() === 200,
    { timeout: 45_000 },
  );
  await page.goto('/map');
  await waitForMapCanvas(page);
  await inBounds;
  // Default Seoul viewport can be all clusters — zoom in until an individual feature pin renders.
  await ensureFeatureMarkers(page, 1);
}

/** Explore-map markers appear only after in-bounds; clusters may replace single pins at low zoom. */
async function anyMarkerOrCluster(page: Page) {
  return page.locator('.maplibregl-marker[role="button"]');
}

async function seedTwoPinTrip(page: Page, tag: string) {
  const { id } = await createTrip(page, {
    title: `${e2ePrefix} ${tag} ${Date.now()}`,
    start: '2026-11-05',
    end: '2026-11-08',
    region: '경북·강원',
  });
  await page.goto(`/trips/${id}`);
  await searchAndAddPlace(page, 1, PLACES.north);
  await searchAndAddPlace(page, 1, PLACES.south);
  return id;
}

test.describe('CORE map — explore map (/map)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test('CORE-010 탐색 지도 첫 렌더 마커(#613) — 상호작용 없이 핀이 그려진다', async ({ page }, testInfo) => {
    await openExploreMap(page);
    const markers = await anyMarkerOrCluster(page);
    await expect(markers.first()).toBeVisible({ timeout: 15_000 });
    const domCount = await markers.count();
    const legendCount = await page.getByTestId('feature-map-marker-style').count();
    expect(domCount).toBeGreaterThan(0);
    expect(legendCount).toBeGreaterThan(0);
    await expect(page.getByTestId('feature-map-empty')).toHaveCount(0);
    await expect(page.getByTestId('feature-map-error')).toHaveCount(0);
    annotate(testInfo, 'metric', `markers dom=${domCount} legend=${legendCount}`);
    await shot(page, 'CORE-010', 'first-render');
  });

  test('CORE-013 마커 선택/해제 — 팝업(데스크톱) 또는 상세 시트(모바일)', async ({ page }) => {
    await openExploreMap(page);
    const pins = featureMarkers(page);
    await expect(pins.first()).toBeVisible({ timeout: 15_000 });
    const title = (await pins.first().getAttribute('aria-label')) ?? '';
    await pins.first().click();
    if (isMobileViewport(page)) {
      // ADR-056: mobile tap opens the detail sheet directly (FeatureMapView.handlePointClick)
      const modal = page.getByTestId('feature-detail-modal');
      await expect(modal).toBeVisible({ timeout: 15_000 });
      await expect(modal).toHaveAttribute('aria-modal', 'true');
      await shot(page, 'CORE-013', 'mobile-sheet');
      await page.getByTestId('feature-detail-modal-close').click();
      await expect(modal).toHaveCount(0);
    } else {
      const popup = page.locator('.maplibregl-popup');
      await expect(popup).toBeVisible({ timeout: 10_000 });
      await expect(popup).toContainText(title.slice(0, 4));
      await expect(page.locator('[data-testid="feature-map-marker-style"][data-marker-selected="true"]')).toHaveCount(1);
      await expect(pins.first()).toHaveAttribute('data-selected', 'true');
      await shot(page, 'CORE-013', 'popup');
      await popup.getByRole('button', { name: '닫기' }).click();
      await expect(popup).toHaveCount(0);
      await expect(page.locator('[data-testid="feature-map-marker-style"][data-marker-selected="true"]')).toHaveCount(0);
    }
  });

  test('CORE-014 줌 컨트롤 — in-bounds 재조회의 zoom이 ±1 움직인다', async ({ page }, testInfo) => {
    test.skip(isMobileViewport(page), '모바일 여행 지도는 navigation control을 숨긴다; 탐색 지도도 터치 줌 중심');
    await openExploreMap(page);
    const zoomOf = (url: string) => Number(new URL(url).searchParams.get('zoom'));
    const zoomInBtn = page.locator('.maplibregl-ctrl-zoom-in');
    await expect(zoomInBtn).toBeVisible();
    const before = await page.evaluate(() => Number(document.querySelector('[data-testid="map-center-state"]')?.getAttribute('data-zoom')));
    const afterIn = page.waitForRequest((r) => r.url().includes('/features/in-bounds'), { timeout: 20_000 });
    await zoomInBtn.click();
    const zIn = zoomOf((await afterIn).url());
    // Zooming back to the first viewport is a viewport-cache hit (no request) — go one level further out.
    const afterOut = page.waitForRequest((r) => r.url().includes('/features/in-bounds') && zoomOf(r.url()) < zIn - 1, { timeout: 20_000 });
    await page.locator('.maplibregl-ctrl-zoom-out').click();
    await page.waitForTimeout(600);
    await page.locator('.maplibregl-ctrl-zoom-out').click();
    const zOut = zoomOf((await afterOut).url());
    expect(zIn).toBeGreaterThan(zOut);
    annotate(testInfo, 'metric', `camera-zoom=${before} in=${zIn} out=${zOut}`);
    await expect(page.getByTestId('feature-map-error')).toHaveCount(0);
    await shot(page, 'CORE-014', 'zoomed');
  });

  test('CORE-015 내 위치 버튼 — 권한/동의 없이도 오류 없이 안내 또는 동의 다이얼로그', async ({ page }) => {
    await openExploreMap(page);
    const btn = page.getByTestId('map-my-location');
    await expect(btn).toBeVisible();
    await btn.click();
    // consent not granted → LocationConsentDialog; granted but permission denied → notice text.
    const dialog = page.getByRole('dialog');
    const notice = page.getByText(/위치 권한이 거부|위치를 가져오지 못했|이 브라우저는 위치를 지원하지/);
    await expect(dialog.or(notice).first()).toBeVisible({ timeout: 15_000 });
    await shot(page, 'CORE-015', 'after-click');
    if (await dialog.isVisible()) {
      // never mutate the account's consents from e2e — cancel.
      await page.keyboard.press('Escape');
      await expect(dialog).toHaveCount(0);
    }
    await expect(btn).toBeEnabled({ timeout: 15_000 });
  });

  test('CORE-016 타일 로드 — VWorld 타일 200, 디코드/worker 오류 없음', async ({ page }, testInfo) => {
    const rec = recordConsole(page);
    let tileOk = 0;
    let tileBad = 0;
    page.on('response', (r) => {
      if (!/api\.vworld\.kr\/req\/wmts/.test(r.url())) return;
      if (r.status() === 200) tileOk += 1;
      else tileBad += 1;
    });
    const tileErrors: string[] = [];
    await page.exposeFunction('__coreTileError', (u: string) => tileErrors.push(u));
    await page.addInitScript(() => {
      window.addEventListener('vworld-tile-error', (e) =>
        (window as unknown as { __coreTileError: (u: string) => void }).__coreTileError(String((e as CustomEvent).detail?.url)),
      );
    });
    await openExploreMap(page);
    await expect.poll(() => tileOk, { timeout: 30_000 }).toBeGreaterThan(0);
    rec.stop();
    const decode = [...rec.errors, ...rec.pageErrors].filter((m) => /decode|Worker failed|Failed to load|WebGL/i.test(m));
    expect(decode, 'tile decode / worker errors').toEqual([]);
    expect(tileBad, 'non-200 tile responses (키 만료 시 전부 4xx — 운영 이슈)').toBe(0);
    expect(tileErrors, 'vworld-tile-error events').toEqual([]);
    annotate(testInfo, 'metric', `tiles ok=${tileOk} bad=${tileBad}`);
    await shot(page, 'CORE-016', 'tiles');
  });

  test('CORE-017 maplibre worker — 정적 서빙 + module worker 실기동(#613)', async ({ page, request }) => {
    const res = await request.get('/maplibre/maplibre-gl-worker.mjs');
    expect(res.status()).toBe(200);
    expect(res.headers()['content-type'] ?? '').toMatch(/javascript/);
    expect((await res.text()).length).toBeGreaterThan(1000);
    const rec = recordConsole(page);
    await openExploreMap(page);
    const outcome = await page.evaluate(
      () =>
        new Promise<string>((resolve) => {
          const w = new Worker('/maplibre/maplibre-gl-worker.mjs', { type: 'module' });
          const t = setTimeout(() => { w.terminate(); resolve('loaded'); }, 2000);
          w.addEventListener('error', (e) => { clearTimeout(t); w.terminate(); resolve(`error: ${(e as ErrorEvent).message}`); });
        }),
    );
    rec.stop();
    expect(outcome).toBe('loaded');
    expect(rec.errors.filter((m) => /Worker failed/i.test(m))).toEqual([]);
  });

  test('CORE-018 VWorld attribution 노출', async ({ page }) => {
    await openExploreMap(page);
    const attrib = page.locator('.maplibregl-ctrl-attrib');
    await expect(attrib).toHaveCount(1);
    // compact mode keeps the text in `.maplibregl-ctrl-attrib-inner`; expand if collapsed so it is visible.
    const toggle = page.locator('.maplibregl-ctrl-attrib-button');
    if ((await toggle.count()) > 0 && !(await attrib.evaluate((el) => el.classList.contains('maplibregl-compact-show')))) {
      await toggle.click({ force: true });
    }
    await expect(page.locator('.maplibregl-ctrl-attrib-inner')).toContainText(ATTRIBUTION);
    await shot(page, 'CORE-018', 'attribution');
  });
});

test.describe('CORE map — trip map first render & fit (#613/#619)', () => {
  let tripId: string | null = null;

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test.afterEach(async ({ page }) => {
    if (tripId) {
      await deleteTrip(page, tripId).catch(() => undefined);
      tripId = null;
    }
  });

  test('CORE-011 여행 지도 첫 렌더 핀(#613) — 새로고침 직후 두 핀이 바로 보인다', async ({ page }, testInfo) => {
    tripId = await seedTwoPinTrip(page, 'CORE-011');
    await page.goto(`/trips/${tripId}`);
    await waitForMapCanvas(page);
    const t0 = Date.now();
    await expect(tripPins(page)).toHaveCount(2, { timeout: 15_000 });
    annotate(testInfo, 'metric', `pins visible after ${Date.now() - t0}ms post-canvas`);
    await expect(page.getByTestId('trip-map-stats')).toContainText('장소 2곳');
    await expect(page.locator('[data-testid="trip-map-marker-style"]')).toHaveCount(2);
    await shot(page, 'CORE-011', 'first-render');
  });

  test('CORE-012 fitBounds가 검색 카드·교통 패널 아래에 핀을 숨기지 않는다(#619, desktop+mobile)', async ({ page }, testInfo) => {
    tripId = await seedTwoPinTrip(page, 'CORE-012');
    await page.goto(`/trips/${tripId}`);
    await waitForMapCanvas(page);
    const pins = tripPins(page);
    await expect(pins).toHaveCount(2, { timeout: 15_000 });
    // let the transport status arrive and the "fit once more under the panel" effect settle
    await page.waitForTimeout(1500);
    const surface = (await page.getByTestId('trip-map-surface').boundingBox()) as Box;
    const search = (await page.getByTestId('trip-map-place-search').boundingBox()) as Box;
    const panelLoc = page.getByTestId('transport-layer-controls');
    const panel = (await panelLoc.count()) > 0 ? ((await panelLoc.boundingBox()) as Box) : null;
    const stats = (await page.getByTestId('trip-map-stats').boundingBox()) as Box;
    const n = await pins.count();
    for (let i = 0; i < n; i++) {
      const pin = (await pins.nth(i).boundingBox()) as Box;
      const label = await pins.nth(i).getAttribute('aria-label');
      expect(pin, `pin ${label} has box`).not.toBeNull();
      expect(intersects(pin, surface, 0), `pin ${label} inside map surface`).toBe(true);
      expect(pin.y, `pin ${label} not above surface`).toBeGreaterThanOrEqual(surface.y);
      expect(pin.y + pin.height, `pin ${label} not below surface`).toBeLessThanOrEqual(surface.y + surface.height + 1);
      expect(intersects(pin, search), `pin ${label} vs search card`).toBe(false);
      if (panel) expect(intersects(pin, panel), `pin ${label} vs transport panel`).toBe(false);
      if (!isMobileViewport(page)) expect(intersects(pin, stats), `pin ${label} vs stats chips`).toBe(false);
    }
    annotate(testInfo, 'verified-against', 'origin/main mapFitPadding.ts + TripMapView.fitToPoints');
    await shot(page, 'CORE-012', isMobileViewport(page) ? 'mobile-fit' : 'desktop-fit');
  });
});
