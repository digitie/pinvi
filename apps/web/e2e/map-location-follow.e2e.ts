import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

const CONSENTS = ['lbs_tos', 'location_collection'].map((consent_type) => ({
  consent_type,
  version: 'v1.0',
  agreed_at: '2026-06-10T00:00:00Z',
  withdrawn_at: null,
}));

test.use({
  permissions: ['geolocation'],
  geolocation: { latitude: 37.5665, longitude: 126.978 },
});

// 2026-11-17 소유자 승인 — 탐색 지도(/map)의 내 위치 버튼도 여행 지도와 같은 따라가기 모드다.
test('탐색 지도 내 위치 버튼 — 동의가 있으면 바로 따라가기 모드', async ({ page }) => {
  await page.route(/.*\/users\/me\/consents$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: CONSENTS }),
    });
  });
  await page.route(/.*\/features\/in-bounds(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          items: [],
          clusters: [],
          cluster_unit: 'individual',
          zoom: 12,
          bbox: { lng_min: 126.9, lat_min: 37.4, lng_max: 127.1, lat_max: 37.6 },
        },
      }),
    });
  });

  // canvas 모드에서는 날씨 마커 레이어도 화면 범위를 묻는다 — 빈 목록으로 답한다.
  await page.route(/.*\/weather\/markers-in-bounds(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          items: [],
          zoom: 12,
          bbox: { lng_min: 126.9, lat_min: 37.4, lng_max: 127.1, lat_max: 37.6 },
        },
      }),
    });
  });

  await page.goto('/map');
  const button = page.getByTestId('map-my-location');
  await expect(button).toHaveAttribute('data-follow-mode', 'off');
  await expect(button).toHaveAccessibleName('내 위치로 이동');
  const box = (await button.boundingBox())!;
  expect(box.width).toBeGreaterThanOrEqual(40);
  expect(box.height).toBeGreaterThanOrEqual(40);

  await button.click();
  await expect(button).toHaveAttribute('data-follow-mode', 'follow');
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  await expect(button).toHaveAccessibleName('내 위치를 따라가는 중');
  // 이미 동의한 사용자에게 동의 다이얼로그를 다시 띄우지 않는다.
  await expect(page.getByTestId('location-consent-dialog')).toHaveCount(0);

  test.skip(process.env.PINVI_E2E_EXPECT_VWORLD_CANVAS !== '1', 'VWorld canvas 검증 환경에서 실행');
  // 손으로 지도를 끌면 따라가기만 꺼진다(점은 남는다) — 다시 누르면 돌아와 따라간다.
  const canvas = page.locator('.maplibregl-canvas').first();
  await expect(canvas).toBeVisible();
  // 따라가기 카메라(flyTo)가 지도에 붙어 자리 잡은 뒤에 끈다 — 그 전 끌기는 애니메이션과 겹친다(#759 CI).
  await expect(button).toHaveAttribute('data-follow-ready', 'true', { timeout: 15_000 });
  const area = (await canvas.boundingBox())!;
  await page.mouse.move(area.x + area.width / 2, area.y + area.height / 2);
  await page.mouse.down();
  await page.mouse.move(area.x + area.width / 2 - 120, area.y + area.height / 2 - 60, {
    steps: 10,
  });
  await page.mouse.up();
  await expect(button).toHaveAttribute('data-follow-mode', 'tracking');
  await expect(button).toHaveAccessibleName('내 위치로 돌아가기');
  await button.click();
  await expect(button).toHaveAttribute('data-follow-mode', 'follow');
});

// ── 2026-11-28 소유자 보고(PR #816): 따라가기 중 "dmz 자생" 검색 → DMZ 자생식물원 선택 → 다음 위치 갱신이 지도를
// 내 위치로 되돌려 "지도가 리셋되는 듯 검색 결과가 사라짐". 실제 브라우저 회귀(적대 재리뷰 하네스 R1·R6에서 옮김).
// Playwright `setGeolocation`은 watch 중 바꾸면 Chromium이 POSITION_UNAVAILABLE을 내므로 watchPosition을 직접 몬다.

const BBOX = { lng_min: 126.9, lat_min: 37.4, lng_max: 127.1, lat_max: 37.6 };
const DMZ_GARDEN = {
  source: 'feature',
  name: 'DMZ자생식물원',
  coord: { lon: 128.1306, lat: 38.2797 },
  feature_id: 'feat-dmz-garden',
  category: 'garden',
  category_label: '수목원',
  marker_color: 'P-07',
  marker_icon: 'garden',
};

/** 가짜 GPS — `window.__pinviGps(lat, lon)`이 위치를 밀어 넣는다. `holdFirst`면 첫 위치를 그때까지 미룬다. */
async function installFakeGps(page: Page, { holdFirst = false } = {}) {
  await page.addInitScript((hold: boolean) => {
    const watchers = new Map<number, (position: GeolocationPosition) => void>();
    let last: [number, number] = [37.5665, 126.978];
    let nextId = 0;
    const fix = (lat: number, lon: number) =>
      ({
        coords: {
          latitude: lat,
          longitude: lon,
          accuracy: 10,
          altitude: null,
          altitudeAccuracy: null,
          heading: null,
          speed: null,
        },
        timestamp: Date.now(),
      }) as unknown as GeolocationPosition;
    (window as unknown as { __pinviGps: (lat: number, lon: number) => void }).__pinviGps = (
      lat,
      lon,
    ) => {
      last = [lat, lon];
      for (const callback of watchers.values()) callback(fix(lat, lon));
    };
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition(ok: (position: GeolocationPosition) => void) {
          setTimeout(() => ok(fix(last[0], last[1])), 10);
        },
        watchPosition(ok: (position: GeolocationPosition) => void) {
          nextId += 1;
          watchers.set(nextId, ok);
          if (!hold) setTimeout(() => ok(fix(last[0], last[1])), 50);
          return nextId;
        },
        clearWatch(id: number) {
          watchers.delete(id);
        },
      },
    });
  }, holdFirst);
}

const pushGps = (page: Page, lat: number, lon: number) =>
  page.evaluate(
    ([a, b]) => (window as unknown as { __pinviGps: (x: number, y: number) => void }).__pinviGps(a, b),
    [lat, lon] as const,
  );

async function mockExploreWithSearch(page: Page) {
  const json = (data: unknown) => ({ contentType: 'application/json', body: JSON.stringify({ data }) });
  await page.route(/.*\/users\/me\/consents$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill(json(CONSENTS));
  });
  await page.route(/.*\/features\/in-bounds(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill(
      json({ items: [], clusters: [], cluster_unit: 'individual', zoom: 14, bbox: BBOX }),
    );
  });
  await page.route(/.*\/weather\/markers-in-bounds(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill(json({ items: [], zoom: 14, bbox: BBOX }));
  });
  await page.route(/.*\/search(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill(json({ results: [DMZ_GARDEN], degraded_sources: [] }));
  });
  // 선택 popup의 상세·날씨 — 이 검사는 popup 자리만 보므로 일시 오류로 답한다(popup은 제목으로 degrade).
  await page.route(/.*\/features\/[^/?]+\/(detail-card|weather)(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ error: { code: 'upstream_unavailable', message: '잠시 후 다시' } }),
    });
  });
}

async function openExploreMap(page: Page, gps: { holdFirst?: boolean } = {}) {
  await installFakeGps(page, gps);
  await mockExploreWithSearch(page);
  await page.goto('/map');
  await expect(page.locator('.maplibregl-canvas').first()).toBeVisible({ timeout: 30_000 });
  return page.getByTestId('map-my-location');
}

async function pickDmzGarden(page: Page) {
  const search = page.getByTestId('map-search');
  await search.getByRole('textbox', { name: '장소·주소 검색' }).fill('dmz 자생');
  await search.getByTestId('map-search-result-feature').first().click();
}

/** 고른 장소 popup의 가운데가 지도 화면 안에 있는가. */
async function popupInsideMap(page: Page): Promise<boolean> {
  const frame = await page.getByTestId('feature-map-frame').boundingBox();
  const popup = await page.getByTestId('feature-map-popup').boundingBox();
  if (!frame || !popup) return false;
  const cx = popup.x + popup.width / 2;
  const cy = popup.y + popup.height / 2;
  return cx > frame.x && cx < frame.x + frame.width && cy > frame.y && cy < frame.y + frame.height;
}

test('탐색 지도 따라가기 중 검색 선택은 따라가기를 끄고, 위치가 갱신돼도 고른 장소가 화면에 남는다', async ({
  page,
}) => {
  test.skip(process.env.PINVI_E2E_EXPECT_VWORLD_CANVAS !== '1', 'VWorld canvas 검증 환경에서 실행');
  const button = await openExploreMap(page);
  await button.click();
  await expect(button).toHaveAttribute('data-follow-mode', 'follow');
  await expect(button).toHaveAttribute('data-follow-ready', 'true', { timeout: 20_000 });

  await pickDmzGarden(page);
  await expect(button).toHaveAttribute('data-follow-mode', 'tracking');
  // flyTo가 DMZ 자생식물원에 선다.
  await expect.poll(() => popupInsideMap(page), { timeout: 15_000 }).toBe(true);

  // 다음 위치 갱신 — 고치기 전에는 easeTo가 지도를 서울로 되돌려 popup이 화면 밖으로 사라졌다.
  await pushGps(page, 37.5675, 126.979);
  await page.waitForTimeout(1_500);
  expect(await popupInsideMap(page)).toBe(true);
  await expect(button).toHaveAttribute('data-follow-mode', 'tracking');
  await expect(button).toHaveAccessibleName('내 위치로 돌아가기');

  // 다시 누르면 내 위치로 돌아와 따라간다(고른 장소는 화면 밖).
  await button.click();
  await expect(button).toHaveAttribute('data-follow-mode', 'follow');
  await expect.poll(() => popupInsideMap(page), { timeout: 15_000 }).toBe(false);
});

test('측위 대기 중 검색 선택은 첫 위치가 카메라를 뺏지 않는다', async ({ page }) => {
  test.skip(process.env.PINVI_E2E_EXPECT_VWORLD_CANVAS !== '1', 'VWorld canvas 검증 환경에서 실행');
  const button = await openExploreMap(page, { holdFirst: true });
  await button.click();
  await expect(button).toHaveAttribute('data-follow-mode', 'locating');

  await pickDmzGarden(page);
  await expect.poll(() => popupInsideMap(page), { timeout: 15_000 }).toBe(true);

  await pushGps(page, 37.5665, 126.978);
  await expect(button).toHaveAttribute('data-follow-mode', 'tracking');
  await page.waitForTimeout(1_500);
  expect(await popupInsideMap(page)).toBe(true);
});
