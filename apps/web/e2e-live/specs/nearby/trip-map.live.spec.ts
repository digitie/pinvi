/**
 * NEAR — transport panel on the trip detail map (`/trips/{id}`): stacking under the place search
 * (#613), fit padding so pins are never under the search line or the panel (#619), nearby data is
 * relative to the trip's places (fitted viewport) rather than Seoul, re-query on POI selection,
 * empty-trip default view, mobile overlay stack.
 *
 * UI reference (PinVi main b1cef056): apps/web/components/trips/TripDetail.tsx (overlayTopLeft →
 * `trip-map-place-search`, `transportLayers` on), apps/web/components/trips/TripMapView.tsx
 * (`trip-map-overlay-stack`, `.trip-map-marker`, fitToPoints + fitPanelRect), apps/web/lib/mapFitPadding.ts.
 *
 * Mutating: creates one `[e2e]` trip per project in beforeAll and deletes it in afterAll (+ sweep).
 */
import { expect, test, type Page } from '@playwright/test';
import {
  createTrip,
  deleteAllE2eTrips,
  deleteTrip,
  e2ePrefix,
  loginAsUser,
  searchAndAddPlace,
  shot,
  waitForMapIdle,
} from '../../helpers/live';
import {
  LAYER_LABEL,
  TransportRecorder,
  ZOOM_IN_TEXT,
  boxesOverlap,
  chip,
  clickTransportMarker,
  closeDetail,
  controls,
  detailDialog,
  expectLayerLineShape,
  incidentList,
  legendMarkers,
  markersBody,
  markersQuery,
  nextMarkersResponse,
  stateLine,
  toggleExpectingRequest,
  waitForControls,
} from '../../helpers/nearby';

test.describe.configure({ mode: 'serial' });
test.setTimeout(180_000);

/** 2026-11-02 prod e2e itinerary — heritage/cave families spread over 영월·영주·안동 (north pin = 고씨굴). */
const PLACES = ['영월 고씨굴', '소수서원', '도산서원', '안동하회마을'] as const;
const REGION = { lonMin: 128.4, lonMax: 128.95, latMin: 36.5, latMax: 37.25 };
const pickMapFeature = (rowText: string) => rowText.includes('장소');

const tripMarkers = (page: Page) => page.locator('.maplibregl-marker.trip-map-marker');
const searchCard = (page: Page) => page.getByTestId('trip-map-place-search');
const overlayStack = (page: Page) => page.getByTestId('trip-map-overlay-stack');
const searchAnchor = (page: Page) => searchCard(page).locator('[data-map-fit-anchor]');

async function openTrip(page: Page, id: string) {
  await page.goto(`/trips/${id}`);
  await expect(page.getByTestId('trip-detail-map')).toBeVisible({ timeout: 30_000 });
  await waitForControls(page);
}

test.describe('NEAR trip map — four-place trip', () => {
  let tripId = '';

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    await loginAsUser(page);
    const trip = await createTrip(page, {
      title: `${e2ePrefix} NEAR trip ${Date.now()}`,
      start: '2026-11-05',
      end: '2026-11-08',
    });
    tripId = trip.id;
    await page.goto(`/trips/${tripId}`);
    for (const place of PLACES) {
      await searchAndAddPlace(page, 1, place, pickMapFeature);
    }
    await page.close();
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    await loginAsUser(page);
    if (tripId) await deleteTrip(page, tripId).catch(() => undefined);
    await deleteAllE2eTrips(page);
    await page.close();
  });

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test('NEAR-022 transport panel is stacked under the place search and never covers it (#613)', async ({ page }) => {
    await openTrip(page, tripId);
    const stack = overlayStack(page);
    await expect(stack).toBeVisible();
    await expect(stack.getByTestId('trip-map-place-search')).toBeVisible();
    await expect(stack.getByTestId('transport-layer-controls')).toBeVisible();
    const searchBox = (await searchCard(page).boundingBox())!;
    const panelBox = (await controls(page).boundingBox())!;
    expect(boxesOverlap(searchBox, panelBox)).toBe(false);
    expect(panelBox.y).toBeGreaterThanOrEqual(searchBox.y + searchBox.height);
    const input = searchCard(page).getByRole('textbox', { name: '장소·주소 검색' });
    await input.click({ position: { x: 12, y: 12 }, timeout: 5_000 });
    await expect(input).toBeFocused();
    // Expanded results push the panel down instead of overlapping it.
    await input.fill('안동');
    await expect(searchCard(page).locator('li').first()).toBeVisible({ timeout: 20_000 });
    const panelAfter = (await controls(page).boundingBox())!;
    expect(panelAfter.y).toBeGreaterThan(panelBox.y);
    expect(boxesOverlap((await searchCard(page).boundingBox())!, panelAfter)).toBe(false);
    await shot(page, 'NEAR-022', 'stacked-overlay');
  });

  test('NEAR-023 first render shows all pins below the search line and outside the panel (#619)', async ({ page }) => {
    await openTrip(page, tripId);
    await expect(page.getByTestId('trip-map-stats')).toContainText(`장소 ${PLACES.length}곳`);
    await expect(page.locator('[data-testid="trip-map-marker-style"]')).toHaveCount(PLACES.length);
    // #613 (vworld-map-web #29): pins are drawn on the first render, before any user interaction.
    await expect(tripMarkers(page)).toHaveCount(PLACES.length, { timeout: 30_000 });
    await waitForMapIdle(page);
    const anchor = (await searchAnchor(page).boundingBox())!;
    const panel = (await controls(page).boundingBox())!;
    for (const marker of await tripMarkers(page).all()) {
      const box = (await marker.boundingBox())!;
      const label = await marker.getAttribute('aria-label');
      expect(box.y, `${label} pin head is below the search input line`).toBeGreaterThanOrEqual(anchor.y + anchor.height - 2);
      expect(boxesOverlap(box, panel), `${label} pin is not under the transport panel`).toBe(false);
    }
    await shot(page, 'NEAR-023', 'fit-padding');
  });

  test('NEAR-024 nearby data is requested for the trip viewport, not the Seoul default', async ({ page }) => {
    await openTrip(page, tripId);
    const res = await toggleExpectingRequest(page, 'highway_incident');
    const q = markersQuery(res);
    expect(q.bbox[0]).toBeLessThanOrEqual(REGION.lonMin);
    expect(q.bbox[2]).toBeGreaterThanOrEqual(REGION.lonMax);
    expect(q.bbox[1]).toBeLessThanOrEqual(REGION.latMin);
    expect(q.bbox[3]).toBeGreaterThanOrEqual(REGION.latMax);
    // The fitted viewport is centred on the trip (영월~안동), not on the Seoul default camera — at the
    // fit zoom a wide desktop viewport may still *contain* Seoul, so compare centres, not containment.
    const cx = (q.bbox[0] + q.bbox[2]) / 2;
    const cy = (q.bbox[1] + q.bbox[3]) / 2;
    // fit padding (search card + panel on the left) shifts the centre west by ~1°
    expect(Math.abs(cx - (REGION.lonMin + REGION.lonMax) / 2)).toBeLessThan(2);
    expect(Math.abs(cy - (REGION.latMin + REGION.latMax) / 2)).toBeLessThan(2);
    expect(Math.hypot(cx - 126.978, cy - 37.5665)).toBeGreaterThan(1);
    await expectLayerLineShape(page, 'highway_incident');
    const rest = await toggleExpectingRequest(page, 'rest_area', (x) => x.layers.includes('rest_area'));
    const restBody = (await markersBody(rest)).layers.find((l) => l.layer === 'rest_area')!;
    if (restBody.status === 'ok') {
      await expect(stateLine(page, 'rest_area')).toContainText(`${restBody.items.length}곳`);
      // 중앙고속도로(안동·영주) runs through the fitted viewport.
      expect(restBody.items.length).toBeGreaterThan(0);
    }
    await shot(page, 'NEAR-024', 'trip-viewport-layers');
  });

  test('NEAR-025 selecting a POI pin flies the map and re-queries the enabled layers', async ({ page }) => {
    await openTrip(page, tripId);
    const first = markersQuery(await toggleExpectingRequest(page, 'highway_incident'));
    const pin = tripMarkers(page).and(page.getByLabel(/고씨굴/)).first();
    await expect(pin).toBeVisible();
    const pending = nextMarkersResponse(page, (q) => q.layers.includes('highway_incident') && q.bbox.join(',') !== first.bbox.join(','));
    await pin.click({ force: true });
    const next = markersQuery(await pending);
    // flyTo moves (and may zoom) to the pin: the re-query must cover 고씨굴 (영월 ≈ 128.47E 37.17N) and
    // is centred north of the first (4-place) viewport.
    expect(next.bbox[0]).toBeLessThanOrEqual(128.47);
    expect(next.bbox[2]).toBeGreaterThanOrEqual(128.47);
    expect(next.bbox[1]).toBeLessThanOrEqual(37.17);
    expect(next.bbox[3]).toBeGreaterThanOrEqual(37.17);
    expect((next.bbox[1] + next.bbox[3]) / 2).toBeGreaterThan((first.bbox[1] + first.bbox[3]) / 2);
    test.info().annotations.push({ type: 'flyto-zoom', description: `${first.zoom} → ${next.zoom}` });
    await expectLayerLineShape(page, 'highway_incident');
  });

  test.describe('mobile', () => {
    test.skip(({ isMobile }) => !isMobile, 'mobile project only (390x844)');

    test('NEAR-028 overlay stack stays inside the map surface and scrolls when the incident list grows', async ({ page }) => {
      await openTrip(page, tripId);
      const stack = overlayStack(page);
      const surface = (await page.getByTestId('trip-map-surface').boundingBox())!;
      const stackBox = (await stack.boundingBox())!;
      expect(stackBox.y + stackBox.height).toBeLessThanOrEqual(surface.y + surface.height + 1);
      await expect(stack).toHaveCSS('overflow-y', 'auto');
      const panelBox = (await controls(page).boundingBox())!;
      expect(panelBox.width).toBeLessThanOrEqual(stackBox.width * 0.7 + 1); // w-64 max-w-[70%]
      const res = await toggleExpectingRequest(page, 'highway_incident');
      const inc = (await markersBody(res)).layers.find((l) => l.layer === 'highway_incident')!;
      if (inc.status === 'ok' && inc.items.length > 0) await expect(incidentList(page)).toBeVisible();
      const after = (await stack.boundingBox())!;
      expect(after.y + after.height).toBeLessThanOrEqual(surface.y + surface.height + 1);
      const overflowing = await stack.evaluate((el) => el.scrollHeight > el.clientHeight);
      test.info().annotations.push({ type: 'overflow', description: String(overflowing) });
      await shot(page, 'NEAR-028', 'mobile-stack');
    });

    test('NEAR-029 no navigation control on the mobile trip map, chips still toggle, marker tap opens the sheet', async ({ page }) => {
      await openTrip(page, tripId);
      await expect(page.locator('.maplibregl-ctrl-zoom-in')).toHaveCount(0);
      const res = await toggleExpectingRequest(page, 'airport');
      const airports = (await markersBody(res)).layers.find((l) => l.layer === 'airport')!;
      await expectLayerLineShape(page, 'airport');
      test.skip(airports.status !== 'ok' || airports.items.filter((i) => i.coord).length === 0, 'no airport inside the trip viewport');
      await expect(legendMarkers(page, 'airport').first()).toBeAttached();
      await clickTransportMarker(page, 'airport');
      await expect(detailDialog(page)).toContainText(LAYER_LABEL.airport);
      await closeDetail(page);
    });
  });
});

test.describe('NEAR trip map — empty trip', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test('NEAR-026 a trip with no places shows the country view: 공항 lists ≥5, 주유소 asks to zoom in', async ({ page }) => {
    const rec = new TransportRecorder(page);
    const trip = await createTrip(page, {
      title: `${e2ePrefix} NEAR empty ${Date.now()}`,
      start: '2026-11-05',
      end: '2026-11-06',
    });
    try {
      await openTrip(page, trip.id);
      await expect(page.getByTestId('trip-map-stats')).toContainText('장소 0곳');
      const res = await toggleExpectingRequest(page, 'airport', (q) => q.layers.includes('airport'));
      const q = markersQuery(res);
      expect(q.zoom).toBeLessThanOrEqual(7); // TripMapView DEFAULT_ZOOM = 7
      const airports = (await markersBody(res)).layers.find((l) => l.layer === 'airport')!;
      if (airports.status === 'ok') expect(airports.items.length).toBeGreaterThanOrEqual(5);
      const mark = Date.now();
      await chip(page, 'fuel_station').click();
      await expect(stateLine(page, 'fuel_station')).toContainText(ZOOM_IN_TEXT);
      await page.waitForTimeout(1_000);
      expect(rec.layersRequested(mark).has('fuel_station')).toBe(false);
      await shot(page, 'NEAR-026', 'empty-trip-country-view');
    } finally {
      await deleteTrip(page, trip.id).catch(() => undefined);
    }
  });
});
