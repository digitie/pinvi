/**
 * NEAR — explore map (`/map`) transport panel: chips, zoom thresholds, markers, incidents,
 * freshness/truncation consistency, soft-fail, auth gate, mobile layout, a11y.
 *
 * UI reference (PinVi main b1cef056): apps/web/components/map/FeatureMapView.tsx (panel is stacked
 * under MapSearchBox in the same `w-72 max-w-[80vw]` column), TransportLayerControls.tsx,
 * lib/useTransportLayers.ts. Prod data: all four layers available since 2026-10-26.
 */
import { expect, test } from '@playwright/test';
import { loginAsUser, shot, waitForRequest } from '../../helpers/live';
import {
  DEFAULT_EXPLORE_ZOOM,
  FEATURES_IN_BOUNDS_RE,
  FRESHNESS_RE,
  LAYERS,
  LAYER_LABEL,
  LAYER_MIN_ZOOM,
  MARKERS_RE,
  STALE_TEXT,
  STATUS_RE,
  TRUNCATED_TEXT,
  TransportRecorder,
  UNAVAILABLE_TEXT,
  ZOOM_IN_TEXT,
  boxesOverlap,
  chip,
  closeDetail,
  controls,
  detailDialog,
  expectLayerLineShape,
  incidentList,
  legendMarkers,
  markersBody,
  markersQuery,
  nextMarkersResponse,
  panBy,
  searchAndFly,
  stateLine,
  toggleExpectingRequest,
  waitForControls,
  zoomBy,
} from '../../helpers/nearby';

test.describe.configure({ mode: 'serial' });
test.setTimeout(180_000);

test.describe('NEAR explore map panel', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test('NEAR-001 panel shows four chips in order, all off, no markers request before a toggle', async ({ page }) => {
    const rec = new TransportRecorder(page);
    const status = waitForRequest(page, STATUS_RE);
    await page.goto('/map');
    const statusRes = await status;
    expect(statusRes.ok()).toBe(true);
    await waitForControls(page);
    await expect(controls(page).getByText('교통 정보', { exact: true })).toBeVisible();
    const group = controls(page).getByRole('group', { name: '교통 정보 레이어' });
    await expect(group.getByRole('button')).toHaveText(LAYERS.map((l) => LAYER_LABEL[l]));
    for (const layer of LAYERS) {
      await expect(chip(page, layer)).toHaveAttribute('aria-pressed', 'false');
      await expect(stateLine(page, layer)).toHaveCount(0);
    }
    expect(rec.markers(), 'no markers-in-bounds before any chip is on').toHaveLength(0);
    await expect(legendMarkers(page)).toHaveCount(0);
    await shot(page, 'NEAR-001', 'panel-idle');
  });

  test('NEAR-002 휴게소 toggle at zoom 9 around Seoul → request, N곳 line, freshness, legend markers', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    await zoomBy(page, -(DEFAULT_EXPLORE_ZOOM - 9)); // 12 → 9
    const res = await toggleExpectingRequest(page, 'rest_area', (q) => q.layers.includes('rest_area') && q.zoom <= 10);
    const q = markersQuery(res);
    expect(q.layers).toEqual(['rest_area']);
    expect(q.limit).toBe(200);
    expect(q.zoom).toBeGreaterThanOrEqual(LAYER_MIN_ZOOM.rest_area);
    const body = await markersBody(res);
    const rest = body.layers.find((l) => l.layer === 'rest_area');
    expect(rest).toBeDefined();
    const line = stateLine(page, 'rest_area');
    await expect(line).toBeVisible();
    if (rest!.status === 'ok') {
      await expect(line).toHaveAttribute('data-status', 'ok');
      await expect(line).toContainText(`${rest!.items.length}곳`);
      await expect(line).toContainText(FRESHNESS_RE);
      // Gyeonggi highways (경부·서해안·영동·중부·외곽) are inside a zoom-9 Seoul viewport.
      expect(rest!.items.length, 'rest areas around Seoul at zoom 9').toBeGreaterThan(0);
      await expect(legendMarkers(page, 'rest_area')).toHaveCount(rest!.items.filter((i) => i.coord).length);
    } else {
      await expect(line).toContainText(UNAVAILABLE_TEXT);
      await expect(line).toHaveAttribute('data-reason', /.+/);
    }
    await shot(page, 'NEAR-002', 'rest-area-on');
  });

  test('NEAR-003 주유소 below zoom 11 says 확대하면 보여요 and is not requested; at zoom ≥11 it is', async ({ page }) => {
    const rec = new TransportRecorder(page);
    await page.goto('/map');
    await waitForControls(page);
    await zoomBy(page, -(DEFAULT_EXPLORE_ZOOM - 10)); // 12 → 10
    const mark = Date.now();
    await chip(page, 'fuel_station').click();
    await expect(chip(page, 'fuel_station')).toHaveAttribute('aria-pressed', 'true');
    await expect(stateLine(page, 'fuel_station')).toContainText(ZOOM_IN_TEXT);
    // requestableTransportLayers() drops fuel_station below 11 → with only that layer on, no request at all.
    await page.waitForTimeout(1_000);
    expect(rec.layersRequested(mark).has('fuel_station')).toBe(false);
    await shot(page, 'NEAR-003', 'fuel-below-min-zoom');

    const pending = nextMarkersResponse(page, (q) => q.layers.includes('fuel_station') && q.zoom >= 11);
    await zoomBy(page, 2); // 10 → 12
    const res = await pending;
    const fuel = (await markersBody(res)).layers.find((l) => l.layer === 'fuel_station')!;
    const line = stateLine(page, 'fuel_station');
    await expect(line).not.toContainText(ZOOM_IN_TEXT);
    if (fuel.status === 'ok') {
      await expect(line).toContainText(`${fuel.items.length}곳`);
      expect(fuel.items.length, 'central Seoul has fuel stations at zoom 12').toBeGreaterThan(0);
    } else {
      await expect(line).toContainText(UNAVAILABLE_TEXT);
    }
    await shot(page, 'NEAR-003', 'fuel-at-zoom-12');
  });

  test('NEAR-007 교통 돌발 at zoom 7 (country scale) → list header count equals legend count, ≤5 rows', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    await zoomBy(page, -(DEFAULT_EXPLORE_ZOOM - 7));
    const res = await toggleExpectingRequest(page, 'highway_incident', (q) => q.layers.includes('highway_incident') && q.zoom <= 8);
    const inc = (await markersBody(res)).layers.find((l) => l.layer === 'highway_incident')!;
    await expectLayerLineShape(page, 'highway_incident');
    if (inc.status !== 'ok') {
      await expect(incidentList(page)).toHaveCount(0);
      return;
    }
    const withCoord = inc.items.filter((i) => i.coord).length;
    await expect(legendMarkers(page, 'highway_incident')).toHaveCount(withCoord);
    if (inc.items.length === 0) {
      await expect(incidentList(page)).toHaveCount(0);
      await expect(stateLine(page, 'highway_incident')).toContainText('0곳');
    } else {
      await expect(incidentList(page)).toBeVisible();
      await expect(incidentList(page)).toContainText(`이 지역 교통 돌발 ${inc.items.length}건`);
      const rows = incidentList(page).getByRole('button');
      expect(await rows.count()).toBe(Math.min(5, inc.items.length));
      for (const row of await rows.all()) {
        const box = await row.boundingBox();
        expect(box?.height ?? 0, 'incident rows are 44px touch targets').toBeGreaterThanOrEqual(44);
      }
    }
    await shot(page, 'NEAR-007', 'incidents-zoom-7');
  });

  test('NEAR-010 toggling a layer off removes its markers and state line without a new request', async ({ page }) => {
    const rec = new TransportRecorder(page);
    await page.goto('/map');
    await waitForControls(page);
    await zoomBy(page, -(DEFAULT_EXPLORE_ZOOM - 6));
    await toggleExpectingRequest(page, 'airport');
    await expect(stateLine(page, 'airport')).toBeVisible();
    const before = await legendMarkers(page, 'airport').count();
    expect(before).toBeGreaterThan(0);
    const mark = Date.now();
    await chip(page, 'airport').click();
    await expect(chip(page, 'airport')).toHaveAttribute('aria-pressed', 'false');
    await expect(legendMarkers(page, 'airport')).toHaveCount(0);
    await expect(stateLine(page, 'airport')).toHaveCount(0);
    await page.waitForTimeout(800);
    expect(rec.markers(mark), 'no request when the last layer is switched off').toHaveLength(0);
  });

  test('NEAR-011 two layers on → one request with layers in display order and two state lines', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    await zoomBy(page, -(DEFAULT_EXPLORE_ZOOM - 8));
    await toggleExpectingRequest(page, 'airport');
    const res = await toggleExpectingRequest(page, 'rest_area', (q) => q.layers.includes('rest_area') && q.layers.includes('airport'));
    expect(markersQuery(res).layers).toEqual(['rest_area', 'airport']);
    const body = await markersBody(res);
    expect(body.layers.map((l) => l.layer).sort()).toEqual(['airport', 'rest_area']);
    await expectLayerLineShape(page, 'rest_area');
    await expectLayerLineShape(page, 'airport');
    await shot(page, 'NEAR-011', 'two-layers');
  });

  test('NEAR-012 panning the map re-queries with a different bbox at the same zoom', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    await zoomBy(page, -(DEFAULT_EXPLORE_ZOOM - 9));
    const first = markersQuery(await toggleExpectingRequest(page, 'rest_area'));
    const pending = nextMarkersResponse(page, (q) => q.layers.includes('rest_area') && q.bbox.join(',') !== first.bbox.join(','));
    await panBy(page, 'ArrowRight', 4);
    const second = markersQuery(await pending);
    expect(second.zoom).toBe(first.zoom);
    expect(second.bbox[0]).toBeGreaterThan(first.bbox[0]); // moved east
    await expectLayerLineShape(page, 'rest_area');
  });

  test('NEAR-013 truncated flag ↔ "일부만 표시" line (dense fuel layer at zoom 11)', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    await zoomBy(page, -1); // 12 → 11, widest viewport that still requests fuel_station
    const res = await toggleExpectingRequest(page, 'fuel_station', (q) => q.layers.includes('fuel_station') && q.zoom === 11);
    const fuel = (await markersBody(res)).layers.find((l) => l.layer === 'fuel_station')!;
    const line = stateLine(page, 'fuel_station');
    if (fuel.status !== 'ok') {
      await expect(line).toContainText(UNAVAILABLE_TEXT);
      return;
    }
    if (fuel.truncated) {
      await expect(line).toContainText(TRUNCATED_TEXT);
      expect(fuel.items.length).toBeLessThanOrEqual(200);
    } else {
      await expect(line).not.toContainText(TRUNCATED_TEXT);
    }
    await shot(page, 'NEAR-013', 'fuel-zoom-11');
  });

  test('NEAR-014 freshness label and stale badge mirror the response freshness for every ok layer', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    await zoomBy(page, -(DEFAULT_EXPLORE_ZOOM - 7));
    // Each toggle requests only the layers it needs (others come from the per-layer cache), so
    // collect the result of every toggle instead of waiting for one 3-layer request.
    const results = new Map<string, Awaited<ReturnType<typeof markersBody>>['layers'][number]>();
    for (const layer of ['airport', 'highway_incident', 'rest_area'] as const) {
      const res = await toggleExpectingRequest(page, layer);
      for (const l of (await markersBody(res)).layers) results.set(l.layer, l);
    }
    for (const layer of ['airport', 'highway_incident', 'rest_area'] as const) {
      const line = stateLine(page, layer);
      await expect(line).toBeVisible();
      const result = results.get(layer);
      if (!result || result.status !== 'ok') continue;
      await expect(line).toContainText(FRESHNESS_RE);
      if (result.freshness?.stale) await expect(line).toContainText(STALE_TEXT);
      else await expect(line).not.toContainText(STALE_TEXT);
    }
    await shot(page, 'NEAR-014', 'freshness-lines');
  });

  test('NEAR-015 layers reported unavailable by /transport/status still have a chip and degrade with a reason', async ({ page }) => {
    const status = waitForRequest(page, STATUS_RE);
    await page.goto('/map');
    const data = ((await (await status).json()) as { data: { enabled: boolean; layers: Array<{ layer: string; available: boolean; reason: string | null }> } }).data;
    expect(data.enabled, 'transport is enabled on prod').toBe(true);
    await waitForControls(page);
    await zoomBy(page, -(DEFAULT_EXPLORE_ZOOM - 7));
    for (const layer of LAYERS) await expect(chip(page, layer)).toBeVisible();
    const down = data.layers.filter((l) => !l.available);
    test.info().annotations.push({ type: 'status', description: JSON.stringify(data.layers) });
    for (const l of down) {
      await chip(page, l.layer as (typeof LAYERS)[number]).click();
      const line = stateLine(page, l.layer as (typeof LAYERS)[number]);
      await expect(line).toContainText(UNAVAILABLE_TEXT);
    }
    // No error banner and no crash either way.
    await expect(page.getByTestId('feature-map-error')).toHaveCount(0);
    await expect(page.getByTestId('feature-map')).toBeVisible();
  });

  test('NEAR-016 transport never breaks the base map: feature markers and search keep working', async ({ page }) => {
    const inBounds = waitForRequest(page, FEATURES_IN_BOUNDS_RE);
    await page.goto('/map');
    expect((await inBounds).ok()).toBe(true);
    await waitForControls(page);
    await zoomBy(page, -(DEFAULT_EXPLORE_ZOOM - 8));
    for (const layer of LAYERS) await chip(page, layer).click();
    await nextMarkersResponse(page).catch(() => null);
    for (const layer of LAYERS) await expectLayerLineShape(page, layer);
    await expect(page.getByTestId('feature-map-error')).toHaveCount(0);
    await expect(page.locator('[data-testid="feature-map-marker-style"]').first()).toBeAttached({ timeout: 20_000 });
    await searchAndFly(page, '서울역');
    await expect(page.getByTestId('map-search').getByRole('textbox')).toHaveValue('');
    await shot(page, 'NEAR-016', 'all-layers-plus-search');
  });

  test('NEAR-038 chips are keyboard operable and grouped with an accessible name', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    const group = controls(page).getByRole('group', { name: '교통 정보 레이어' });
    await expect(group).toBeVisible();
    const airport = chip(page, 'airport');
    await airport.focus();
    await expect(airport).toBeFocused();
    const pending = nextMarkersResponse(page, (q) => q.layers.includes('airport'));
    await page.keyboard.press('Space');
    await expect(airport).toHaveAttribute('aria-pressed', 'true');
    await pending;
    await page.keyboard.press('Enter');
    await expect(airport).toHaveAttribute('aria-pressed', 'false');
    for (const layer of LAYERS) {
      const box = await chip(page, layer).boundingBox();
      expect(box?.height ?? 0, `${layer} chip is ≥44px`).toBeGreaterThanOrEqual(44);
    }
  });

  test('NEAR-039 "여기서 주변 보기" context action flies to zoom 15 and re-queries enabled layers', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    await toggleExpectingRequest(page, 'fuel_station');
    const canvas = page.locator('.maplibregl-canvas').first();
    const box = (await canvas.boundingBox())!;
    const pending = nextMarkersResponse(page, (q) => q.zoom === 15 && q.layers.includes('fuel_station'));
    await canvas.click({ button: 'right', position: { x: box.width / 2, y: box.height / 2 } });
    await page.getByRole('button', { name: '여기서 주변 보기' }).click();
    const q = markersQuery(await pending);
    expect(q.zoom).toBe(15);
    await expectLayerLineShape(page, 'fuel_station');
  });

  test('NEAR-040 legend marker count per layer equals items with coordinates in the response', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    await zoomBy(page, -(DEFAULT_EXPLORE_ZOOM - 8));
    await toggleExpectingRequest(page, 'rest_area');
    await toggleExpectingRequest(page, 'airport');
    const res = await toggleExpectingRequest(page, 'highway_incident', (q) => q.layers.length === 3);
    const body = await markersBody(res);
    for (const result of body.layers) {
      const expected = result.status === 'ok' ? result.items.filter((i) => i.coord).length : 0;
      await expect(legendMarkers(page, result.layer)).toHaveCount(expected);
      for (const marker of await legendMarkers(page, result.layer).all()) {
        await expect(marker).toHaveAttribute('data-feature-id', /^[A-Za-z0-9_-]{1,128}$/);
        await expect(marker).toHaveAttribute('data-marker-icon', /.+/);
        await expect(marker).toHaveAttribute('data-marker-color', /.+/);
      }
    }
  });
});

test.describe('NEAR explore map — auth gate', () => {
  test('NEAR-019 unauthenticated visit to /map ends on /login and never shows the panel', async ({ page }) => {
    const rec = new TransportRecorder(page);
    await page.context().clearCookies();
    await page.goto('/map');
    await page.waitForURL(/\/login/, { timeout: 30_000 });
    await expect(controls(page)).toHaveCount(0);
    // Any /transport call made before the redirect must have been rejected, never served.
    for (const { url } of rec.urls) {
      expect(MARKERS_RE.test(url), `no markers fetch while logged out: ${url}`).toBe(false);
    }
  });
});

test.describe('NEAR explore map — mobile layout', () => {
  test.skip(({ isMobile }) => !isMobile, 'mobile project only (390x844)');
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test('NEAR-020 on 390px the panel sits under the search box, does not cover it, chips are tappable', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    const search = page.getByTestId('map-search').first();
    const searchBox = (await search.boundingBox())!;
    const panelBox = (await controls(page).boundingBox())!;
    expect(boxesOverlap(searchBox, panelBox)).toBe(false);
    expect(panelBox.y).toBeGreaterThanOrEqual(searchBox.y + searchBox.height);
    expect(panelBox.width).toBeLessThanOrEqual(390 * 0.8 + 1); // max-w-[80vw]
    const input = search.getByRole('textbox', { name: '장소·주소 검색' });
    await input.click({ position: { x: 12, y: 12 } });
    await expect(input).toBeFocused();
    await toggleExpectingRequest(page, 'airport');
    await expectLayerLineShape(page, 'airport');
    await shot(page, 'NEAR-020', 'mobile-panel');
  });

  test('NEAR-021 mobile incident row opens the full-screen detail sheet and Escape/닫기 closes it', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    await zoomBy(page, -(DEFAULT_EXPLORE_ZOOM - 7));
    const res = await toggleExpectingRequest(page, 'highway_incident');
    const inc = (await markersBody(res)).layers.find((l) => l.layer === 'highway_incident')!;
    test.skip(inc.status !== 'ok' || inc.items.length === 0, 'no active highway incidents right now');
    await incidentList(page).getByRole('button').first().click();
    await expect(detailDialog(page)).toBeVisible();
    const dialogBox = (await detailDialog(page).boundingBox())!;
    expect(dialogBox.width).toBeGreaterThanOrEqual(390 * 0.9);
    await expect(detailDialog(page)).toContainText('교통 돌발');
    await shot(page, 'NEAR-021', 'mobile-incident-sheet');
    await closeDetail(page);
  });
});
