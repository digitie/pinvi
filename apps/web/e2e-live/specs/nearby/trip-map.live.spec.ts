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
import { expect, test, type Page, type Response } from '@playwright/test';
import { runSearch, searchRows } from '../../helpers/search';
import { renderedMap, waitForCamera } from '../../helpers/geometry';
import { normalizeFixtureName } from '../../helpers/searchFixture';
import { viewportBboxMatches } from '../../helpers/viewportBbox';
import {
  createTrip,
  deleteAllE2eTrips,
  deleteTrip,
  e2ePrefix,
  loginAsUser,
  poiRows,
  selectDay,
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
  stateLine,
  toggleExpectingRequest,
  waitForControls,
} from '../../helpers/nearby';

test.describe.configure({ mode: 'serial' });
test.setTimeout(180_000);

/** 2026-11-02 prod e2e itinerary — heritage/cave families spread over 영월·영주·안동 (north pin = 고씨굴). */
const PLACES = ['영월 고씨굴', '소수서원', '도산서원', '안동하회마을'] as const;

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
  const expectedCoords:{lon:number;lat:number}[]=[];

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
      await selectDay(page,1);
      // runSearch·searchRows가 scope 안에서 map-search를 찾는다 — 상자 자체가 아니라 패널을 넘긴다.
      const scope=page.locator('#trip-panel-plan');
      const outcome=await runSearch(page,place,{scope});
      expect(outcome.status).toBe(200);
      const key=normalizeFixtureName(place.replace(/^\S+\s/,''));
      const index=outcome.rows.findIndex(row=>row.source==='feature'&&row.coord!=null
        &&normalizeFixtureName(row.name).endsWith(key));
      expect(index,'여행 범위 fixture에는 해당 Map 장소의 실제 point 좌표가 필요하다').toBeGreaterThanOrEqual(0);
      const picked=outcome.rows[index]!;
      expectedCoords.push(picked.coord!);
      const before=await poiRows(page).count();
      await searchRows(page,undefined,scope).nth(index).click();
      await expect(poiRows(page)).toHaveCount(before+1);
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
    // #686: 맞춤은 지도 load 뒤에 적용된다. 그 전에 칩을 누르면 TripMapView 기본 시점(127.5,36.5 z7)의
    // 요청을 잡는다(운영 22:41:30 bbox=124.80,33.00,130.20,40.05 z7). NEAR-023처럼 네 핀이 그려지고
    // 지도가 멈춘 뒤 — 사용자가 여행 지도를 본 상태에서 — 켠다.
    await expect(tripMarkers(page)).toHaveCount(PLACES.length, { timeout: 30_000 });
    await waitForMapIdle(page);
    const map=await renderedMap(page);
    await waitForCamera(map);
    expect(expectedCoords).toHaveLength(4);
    const res = await toggleExpectingRequest(page, 'highway_incident');
    const q = markersQuery(res);
    for(const coord of expectedCoords){
      expect(q.bbox[0]).toBeLessThanOrEqual(coord.lon);
      expect(q.bbox[2]).toBeGreaterThanOrEqual(coord.lon);
      expect(q.bbox[1]).toBeLessThanOrEqual(coord.lat);
      expect(q.bbox[3]).toBeGreaterThanOrEqual(coord.lat);
    }
    expect(await map.evaluate((m,coords)=>coords.every(c=>m.getBounds().contains([c.lon,c.lat])),expectedCoords)).toBe(true);
    const viewport = await map.evaluate((m, coords) => {
      const bounds = m.getBounds(), canvas = m.getCanvas();
      const points = coords.map(c => m.project([c.lon, c.lat]));
      return {
        bbox: [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()],
        spanX: Math.max(...points.map(p => p.x)) - Math.min(...points.map(p => p.x)),
        spanY: Math.max(...points.map(p => p.y)) - Math.min(...points.map(p => p.y)),
        width: canvas.clientWidth, height: canvas.clientHeight,
      };
    }, expectedCoords);
    // API가 실제 맞춘 native viewport를 조회해야 한다. 한국 경계 clamp와 저줌 양자화만 허용한다.
    expect(viewportBboxMatches(q.bbox, viewport.bbox, q.zoom)).toBe(true);
    // 네 좌표가 포함돼도 지나치게 축소한 전국 보기는 실패한다. 고정 카탈로그 화면에서
    // 여행의 투영 범위가 한 축에서 지도 1/4 이상을 사용해야 한다.
    expect(Math.max(viewport.spanX / viewport.width, viewport.spanY / viewport.height)).toBeGreaterThan(0.25);
    const panel = (await controls(page).boundingBox())!;
    const stats = (await page.getByTestId('trip-map-stats').boundingBox())!;
    for (const marker of await tripMarkers(page).all()) {
      const box = (await marker.boundingBox())!;
      expect(boxesOverlap(box, panel)).toBe(false);
      expect(boxesOverlap(box, stats)).toBe(false);
    }
    await map.dispose();
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
    const poiId = await page.getByTestId('trip-map-marker-style').filter({ hasText: /고씨굴/ }).getAttribute('data-poi-id');
    expect(poiId).toBeTruthy();
    const pin = tripMarkers(page).and(page.locator('[data-interaction-id=' + JSON.stringify('poi:' + poiId) + ']'));
    await expect(pin).toBeVisible();
    const map = await renderedMap(page);
    const responses: Response[] = [];
    const issuedAfter = Date.now();
    const observe = (response: Response) => {
      const url = new URL(response.url());
      if (url.pathname.endsWith('/transport/markers-in-bounds') &&
          response.request().timing().startTime >= issuedAfter) responses.push(response);
    };
    page.on('response', observe);
    try {
      await pin.click();
      await expect(pin).toHaveAttribute('data-selected', 'true');
      await waitForCamera(map);
      const bbox = await map.evaluate(m => {
        const b = m.getBounds();
        return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
      });
      let matched: Response | undefined;
      await expect.poll(() => {
        matched = responses.find(response => {
          const q = markersQuery(response);
          return q.layers.includes('highway_incident') && q.bbox.join(',') !== first.bbox.join(',') &&
            viewportBboxMatches(q.bbox, bbox, q.zoom);
        });
        return Boolean(matched);
      }, { timeout: 30_000 }).toBe(true);
      const next = markersQuery(matched!);
      const selectedCoord = expectedCoords[0]!;
      expect(next.bbox[0]).toBeLessThanOrEqual(selectedCoord.lon);
      expect(next.bbox[2]).toBeGreaterThanOrEqual(selectedCoord.lon);
      expect(next.bbox[1]).toBeLessThanOrEqual(selectedCoord.lat);
      expect(next.bbox[3]).toBeGreaterThanOrEqual(selectedCoord.lat);
      test.info().annotations.push({ type: 'flyto-zoom', description: first.zoom + ' → ' + next.zoom });
    } finally {
      page.off('response', observe);
      await map.dispose();
    }
    await expectLayerLineShape(page, 'highway_incident');
  });

  /** #704: 지도·패널이 창 안, 문서 스크롤 없음, 맞춤 뒤 모든 핀이 지도·창 안. */
  async function expectDesktopMapInWindow(page: Page, minMapShare: number) {
    await openTrip(page, tripId);
    await expect(tripMarkers(page)).toHaveCount(PLACES.length, { timeout: 30_000 });
    await waitForMapIdle(page);
    const viewport = page.viewportSize()!;
    const map = (await page.getByTestId('trip-detail-map').boundingBox())!;
    // 900 px 창에서 지도가 ~1590 px로 자라 핀이 fold 아래에 그려졌다 — 지도는 창 안, 문서는 스크롤하지 않는다.
    expect(map.y).toBeGreaterThanOrEqual(0);
    expect(map.y + map.height, 'map bottom is inside the window').toBeLessThanOrEqual(viewport.height + 1);
    expect(map.height).toBeGreaterThan(viewport.height * minMapShare);
    const documentOverflow = await page.evaluate(() => document.scrollingElement!.scrollHeight - window.innerHeight);
    expect(documentOverflow, 'the page itself does not scroll').toBeLessThanOrEqual(1);
    const panel = (await page.getByTestId('trip-detail-panel').boundingBox())!;
    expect(panel.y + panel.height, 'left panel is inside the window').toBeLessThanOrEqual(viewport.height + 1);
    for (const marker of await tripMarkers(page).all()) {
      const box = (await marker.boundingBox())!;
      const label = await marker.getAttribute('aria-label');
      const tipX = box.x + box.width / 2;
      const tipY = box.y + box.height;
      expect(tipX, `${label} pin is inside the map horizontally`).toBeGreaterThanOrEqual(map.x);
      expect(tipX, `${label} pin is inside the map horizontally`).toBeLessThanOrEqual(map.x + map.width);
      expect(box.y, `${label} pin head is inside the map`).toBeGreaterThanOrEqual(map.y);
      expect(tipY, `${label} pin is above the fold`).toBeLessThanOrEqual(Math.min(map.y + map.height, viewport.height));
    }
  }

  test.describe('desktop', () => {
    test.skip(({ isMobile }) => isMobile, 'desktop project only (1440x900)');

    test('NEAR-042 the desktop trip map stays inside the window and every fitted pin is on screen (#704)', async ({ page }) => {
      await expectDesktopMapInWindow(page, 0.55);
      await shot(page, 'NEAR-042', 'desktop-map-in-window');
    });

    test('NEAR-043 on a short 1280x600 desktop window the pins stay above the fold and the page does not scroll (#704)', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 600 });
      await expectDesktopMapInWindow(page, 0.45);
      await shot(page, 'NEAR-043', 'short-desktop-map-in-window');
    });
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
