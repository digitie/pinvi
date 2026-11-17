/**
 * NEAR — transport panel on the trip detail map (`/trips/{id}`): stacking under the place search
 * (#613), fit padding so pins are never under the search line or the panel (#619), nearby data is
 * the trip places' radius (2026-11-16: 주유소 10 km · 교통 돌발 20 km, `/transport/markers-near`) rather
 * than the viewport — so camera moves never re-query, an empty trip has nothing nearby — and the
 * mobile overlay stack (공항·휴게소 layers removed).
 *
 * UI reference (PinVi main b1cef056): apps/web/components/trips/TripDetail.tsx (overlayTopLeft →
 * `trip-map-place-search`, `transportLayers` on), apps/web/components/trips/TripMapView.tsx
 * (`trip-map-overlay-stack`, `.trip-map-marker`, fitToPoints + fitPanelRect), apps/web/lib/mapFitPadding.ts.
 *
 * Mutating: creates one `[e2e]` trip per project in beforeAll and deletes it in afterAll (+ sweep).
 */
import { expect, test, type Page } from '@playwright/test';
import { runSearch, searchRows } from '../../helpers/search';
import { renderedMap, waitForCamera } from '../../helpers/geometry';
import { normalizeFixtureName } from '../../helpers/searchFixture';
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
  LAYERS,
  LOADING_TEXT,
  NEAR_RADIUS_M,
  NEAR_RE,
  PANEL_LABELS,
  REMOVED_LAYERS,
  TransportRecorder,
  UNAVAILABLE_TEXT,
  ZOOM_IN_TEXT,
  boxesOverlap,
  chip,
  controls,
  expectLayerLineShape,
  haversineM,
  incidentList,
  incidentToggle,
  layerGroup,
  legendMarkers,
  nearBody,
  nearQuery,
  stateLine,
  toggleExpectingNear,
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
    await expect(stack.getByTestId('map-layer-controls')).toBeVisible();
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

  test('NEAR-024 trip map transport is the trip places radius (markers-near with the place points), not the viewport', async ({ page }) => {
    const rec = new TransportRecorder(page);
    await openTrip(page, tripId);
    await expect(tripMarkers(page)).toHaveCount(PLACES.length, { timeout: 30_000 });
    await waitForMapIdle(page);
    expect(expectedCoords).toHaveLength(4);
    // 2026-11-16: 여행 지도의 주유소·교통 돌발은 여행 장소 반경이다(주유소 10 km·교통 돌발 20 km).
    const res = await toggleExpectingNear(page, 'highway_incident');
    const q = nearQuery(res);
    expect(q.layers).toEqual(['highway_incident']);
    // 요청 기준점 = 여행 장소 네 곳(지도 화면 bbox가 아니다).
    expect(q.points).toHaveLength(PLACES.length);
    for (const coord of expectedCoords) {
      expect(
        q.points.some((p) => Math.abs(p.lon - coord.lon) < 1e-4 && Math.abs(p.lat - coord.lat) < 1e-4),
        `trip place ${coord.lon},${coord.lat} is a query point`,
      ).toBe(true);
    }
    expect(new URL(res.url()).searchParams.get('bbox')).toBeNull();
    const body = await nearBody(res);
    expect(body.radius_m.highway_incident).toBe(NEAR_RADIUS_M.highway_incident);
    const line = stateLine(page, 'highway_incident');
    await expect(line).not.toContainText(LOADING_TEXT, { timeout: 30_000 });
    const inc = body.layers.find((l) => l.layer === 'highway_incident')!;
    if (inc.status === 'ok') {
      await expect(line).toContainText(`${inc.items.length}곳 · 여행 장소 20km 이내`);
      // 반경 모드에는 줌 안내가 없다.
      await expect(line).not.toContainText(ZOOM_IN_TEXT);
    } else {
      await expect(line).toContainText(UNAVAILABLE_TEXT);
    }
    // 뷰포트 조회는 하지 않는다.
    expect(rec.markers(), 'no markers-in-bounds on the trip map').toHaveLength(0);
    // 맞춤이 피하는 것은 패널의 상시 부분이다(#619) — 결과가 와도 핀이 패널 밑에 들지 않는다.
    await waitForMapIdle(page);
    const panelFull = (await controls(page).boundingBox())!;
    const transient = controls(page).locator('[data-map-fit-transient]');
    const transientTop = (await transient.count()) > 0 ? (await transient.first().boundingBox())?.y : undefined;
    const panel = transientTop == null ? panelFull
      : { ...panelFull, height: Math.max(0, Math.min(panelFull.height, transientTop - panelFull.y)) };
    for (const marker of await tripMarkers(page).all()) {
      expect(boxesOverlap((await marker.boundingBox())!, panel)).toBe(false);
    }
    await shot(page, 'NEAR-024', 'trip-radius-layers');
  });

  test('NEAR-041 every item is within the radius of a trip place (주유소 10 km · 교통 돌발 20 km) and lines say so', async ({ page }) => {
    await openTrip(page, tripId);
    for (const layer of LAYERS) {
      const res = await toggleExpectingNear(page, layer);
      const body = await nearBody(res);
      const radius = NEAR_RADIUS_M[layer];
      expect(body.radius_m[layer]).toBe(radius);
      const result = body.layers.find((l) => l.layer === layer)!;
      const line = stateLine(page, layer);
      await expect(line).not.toContainText(LOADING_TEXT, { timeout: 30_000 });
      if (result.status !== 'ok') {
        await expect(line).toContainText(UNAVAILABLE_TEXT);
        continue;
      }
      await expect(line).toContainText(`여행 장소 ${radius / 1000}km 이내`);
      let previous = -1;
      for (const item of result.items) {
        expect(item.coord, `${layer} ${item.feature_id} has a coordinate`).not.toBeNull();
        const nearest = Math.min(...expectedCoords.map((c) => haversineM(item.coord!, c)));
        // 서버가 거른 반경 + 좌표 반올림 여유(5자리 ≈ 1 m).
        expect(nearest, `${layer} ${item.feature_id} within ${radius} m of a trip place`).toBeLessThanOrEqual(radius + 5);
        const distance = Number(item.distance_m);
        expect(Math.abs(distance - nearest), 'distance_m = distance to the nearest trip place').toBeLessThanOrEqual(5);
        expect(distance, 'items are nearest first').toBeGreaterThanOrEqual(previous);
        previous = distance;
      }
      // 마커 legend = 응답 중 좌표 있는 항목.
      await expect(legendMarkers(page, layer)).toHaveCount(result.items.filter((i) => i.coord).length);
    }
    await shot(page, 'NEAR-041', 'trip-radius-distances');
  });

  test('NEAR-044 both radius layers over four far-apart places are ok — a single request fan-out is not rejected by its own cap (T-READ-PIN-01)', async ({ page }) => {
    // 전제: 네 장소가 서로 2 km(서버 묶음 거리) 넘게 떨어져 있어 레이어마다 Map 근처 조회가 4번 동시에 나간다.
    // 예전 상한(transport 2)에서는 이 팬아웃이 자기 자리에 막혀(BULKHEAD_FULL) 레이어 전체가 unavailable이었다.
    expect(expectedCoords).toHaveLength(PLACES.length);
    for (let i = 0; i < expectedCoords.length; i += 1) {
      for (let j = i + 1; j < expectedCoords.length; j += 1) {
        expect(haversineM(expectedCoords[i]!, expectedCoords[j]!), 'trip places are separate query centers').toBeGreaterThan(2_000);
      }
    }
    await openTrip(page, tripId);
    const seen = new Map<string, { status: string; reason?: string | null }>();
    for (const layer of LAYERS) {
      const res = await toggleExpectingNear(page, layer);
      expect(nearQuery(res).points).toHaveLength(PLACES.length);
      for (const result of (await nearBody(res)).layers) seen.set(result.layer, result);
    }
    // 레이어가 운영에서 꺼져 있으면(disabled) 이 사례의 전제가 없다 — 실패가 아니라 건너뛴다.
    const disabled = LAYERS.filter((layer) => seen.get(layer)?.status === 'disabled');
    test.skip(disabled.length > 0, `transport layer disabled in this environment: ${disabled.join(',')}`);
    for (const layer of LAYERS) {
      const result = seen.get(layer);
      expect(result, `${layer} answered`).toBeDefined();
      expect(result!.status, `${layer} is ok (reason=${result!.reason ?? '-'})`).toBe('ok');
      await expect(stateLine(page, layer)).toContainText(`여행 장소 ${NEAR_RADIUS_M[layer] / 1000}km 이내`, { timeout: 30_000 });
      await expect(stateLine(page, layer)).not.toContainText(UNAVAILABLE_TEXT);
    }
    await shot(page, 'NEAR-044', 'trip-radius-both-layers-ok');
  });

  test('NEAR-025 selecting a POI pin flies the map but does not re-query (radius follows the places, not the camera)', async ({ page }) => {
    const rec = new TransportRecorder(page);
    await openTrip(page, tripId);
    await toggleExpectingNear(page, 'highway_incident');
    await expectLayerLineShape(page, 'highway_incident');
    const lineBefore = await stateLine(page, 'highway_incident').textContent();
    const poiId = await page.getByTestId('trip-map-marker-style').filter({ hasText: /고씨굴/ }).getAttribute('data-poi-id');
    expect(poiId).toBeTruthy();
    const pin = tripMarkers(page).and(page.locator('[data-interaction-id=' + JSON.stringify('poi:' + poiId) + ']'));
    await expect(pin).toBeVisible();
    const map = await renderedMap(page);
    const nearBefore = rec.urls.filter((u) => NEAR_RE.test(u.url)).length;
    try {
      const zoomBefore = await map.evaluate((m) => m.getZoom());
      await pin.click();
      await expect(pin).toHaveAttribute('data-selected', 'true');
      await waitForCamera(map);
      const zoomAfter = await map.evaluate((m) => m.getZoom());
      test.info().annotations.push({ type: 'flyto-zoom', description: zoomBefore + ' → ' + zoomAfter });
      await page.waitForTimeout(1_500); // 디바운스(250ms)보다 넉넉히
    } finally {
      await map.dispose();
    }
    expect(rec.urls.filter((u) => NEAR_RE.test(u.url)).length, 'no new markers-near after the camera moved').toBe(nearBefore);
    expect(rec.markers(), 'no markers-in-bounds either').toHaveLength(0);
    await expect(stateLine(page, 'highway_incident')).toHaveText(lineBefore ?? '');
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
      // 원형 마커는 원의 중심이 좌표다 — 오른쪽 이름 라벨까지 넣은 마커 상자의 가운데가 아니라 원을 잰다.
      const box = (await marker.getByTestId('circle-place-marker-dot').boundingBox())!;
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
      const res = await toggleExpectingNear(page, 'highway_incident');
      const inc = (await nearBody(res)).layers.find((l) => l.layer === 'highway_incident')!;
      if (inc.status === 'ok' && inc.items.length > 0) {
        // 여행 지도는 돌발 목록을 접어 둔다(#731) — 실제 상태 줄 토글로 편 뒤 스택이 지도 안에 머무는지 본다.
        const toggle = incidentToggle(page);
        await expect(toggle).toHaveAttribute('aria-expanded', 'false');
        await expect(incidentList(page)).toHaveCount(0);
        await toggle.click();
        await expect(toggle).toHaveAttribute('aria-expanded', 'true');
        await expect(incidentList(page)).toBeVisible();
      }
      const after = (await stack.boundingBox())!;
      expect(after.y + after.height).toBeLessThanOrEqual(surface.y + surface.height + 1);
      const overflowing = await stack.evaluate((el) => el.scrollHeight > el.clientHeight);
      test.info().annotations.push({ type: 'overflow', description: String(overflowing) });
      await shot(page, 'NEAR-028', 'mobile-stack');
    });

    test('NEAR-029 no navigation control on the mobile trip map, airport layer is gone, remaining checkboxes toggle', async ({ page }) => {
      const rec = new TransportRecorder(page);
      await openTrip(page, tripId);
      await expect(page.locator('.maplibregl-ctrl-zoom-in')).toHaveCount(0);
      // 2026-11-16: 공항·휴게소 레이어를 지도에서 뺐다 — 체크박스도 마커도 요청도 없다.
      await expect(layerGroup(page).locator('label')).toHaveText(PANEL_LABELS);
      for (const layer of REMOVED_LAYERS) {
        await expect(chip(page, layer)).toHaveCount(0);
        await expect(legendMarkers(page, layer)).toHaveCount(0);
      }
      for (const layer of LAYERS) {
        await toggleExpectingNear(page, layer);
        await expectLayerLineShape(page, layer);
      }
      for (const layer of LAYERS) {
        await chip(page, layer).uncheck();
        await expect(chip(page, layer)).not.toBeChecked();
        await expect(stateLine(page, layer)).toHaveCount(0);
        await expect(legendMarkers(page, layer)).toHaveCount(0);
      }
      const requested = new Set(
        rec.urls
          .filter((u) => NEAR_RE.test(u.url))
          .flatMap((u) => (new URL(u.url).searchParams.get('layers') ?? '').split(',')),
      );
      for (const layer of REMOVED_LAYERS) expect(requested.has(layer), `${layer} never requested`).toBe(false);
      await shot(page, 'NEAR-029', 'mobile-checkboxes');
    });
  });
});

test.describe('NEAR trip map — empty trip', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test('NEAR-026 a trip with no places has nothing nearby: markers-near without points answers 0곳, no zoom hint', async ({ page }) => {
    const rec = new TransportRecorder(page);
    const trip = await createTrip(page, {
      title: `${e2ePrefix} NEAR empty ${Date.now()}`,
      start: '2026-11-05',
      end: '2026-11-06',
    });
    try {
      await openTrip(page, trip.id);
      await expect(page.getByTestId('trip-map-stats')).toContainText('장소 0곳');
      const res = await toggleExpectingNear(page, 'fuel_station');
      expect(nearQuery(res).points).toHaveLength(0);
      const fuel = (await nearBody(res)).layers.find((l) => l.layer === 'fuel_station')!;
      expect(fuel.status).toBe('ok');
      expect(fuel.items).toHaveLength(0);
      await expect(stateLine(page, 'fuel_station')).toContainText('0곳 · 여행 장소 10km 이내');
      await expect(stateLine(page, 'fuel_station')).not.toContainText(ZOOM_IN_TEXT);
      expect(rec.markers(), 'no markers-in-bounds on the trip map').toHaveLength(0);
      await shot(page, 'NEAR-026', 'empty-trip-radius');
    } finally {
      await deleteTrip(page, trip.id).catch(() => undefined);
    }
  });
});
