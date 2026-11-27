import { expect, test, type Page } from './fixtures';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

const FRESHNESS = {
  source_collected_at: '2026-10-23T09:00:00+09:00',
  loaded_at: '2026-10-23T09:05:00+09:00',
  age_seconds: 600,
  max_age_seconds: 172800,
  stale: false,
};

async function mockMapReads(page: Page) {
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
}

async function mockTransportStatus(page: Page, enabled: boolean) {
  await page.route(/.*\/transport\/status$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: enabled
          ? {
              enabled: true,
              layers: [
                { layer: 'fuel_station', available: false, reason: 'NOT_LOADED', freshness: null },
                { layer: 'rest_area', available: true, reason: null, freshness: FRESHNESS },
                { layer: 'highway_incident', available: true, reason: null, freshness: FRESHNESS },
                { layer: 'airport', available: true, reason: null, freshness: FRESHNESS },
              ],
            }
          : { enabled: false, layers: [] },
      }),
    });
  });
}

// ADR-076 — 교통 정보 레이어 컨트롤은 기능이 켜져 있을 때만 보인다.
test('교통 정보가 켜져 있으면 레이어 토글이 보이고 적재 전 레이어를 알린다', async ({ page }) => {
  await mockMapReads(page);
  await mockTransportStatus(page, true);

  await page.goto('/map');

  // 2026-11-16: 교통 레이어는 지도 레이어 패널의 체크박스다. 공항·휴게소는 없다(경로·영역도 2026-11-27 제거).
  const controls = page.getByTestId('map-layer-controls');
  await expect(controls).toBeVisible();
  const labels = controls.getByRole('group', { name: '지도 레이어 표시' }).locator('label');
  await expect(labels).toHaveText(['주유소', '교통 돌발']);
  await expect(page.getByTestId('transport-layer-toggle-airport')).toHaveCount(0);
  await expect(page.getByTestId('transport-layer-toggle-rest_area')).toHaveCount(0);
  const fuel = page.getByTestId('transport-layer-toggle-fuel_station');
  await expect(fuel).not.toBeChecked();
  await fuel.check();
  await expect(fuel).toBeChecked();
  // 상태 응답에서 주유소는 NOT_LOADED — 켜면 "일시적으로 불러올 수 없음"이다.
  await expect(page.getByTestId('transport-layer-state-fuel_station')).toContainText(
    '일시적으로 불러올 수 없음',
  );
});

test('교통 정보가 꺼져 있으면 지도 화면은 지금과 같다', async ({ page }) => {
  await mockMapReads(page);
  await mockTransportStatus(page, false);

  await page.goto('/map');

  await expect(page.getByTestId('feature-map')).toBeVisible();
  // 지도 레이어 패널은 교통 레이어만 담으므로 패널 자체가 없다.
  await expect(page.getByTestId('map-layer-controls')).toHaveCount(0);
  await expect(page.getByTestId('transport-layer-toggle-fuel_station')).toHaveCount(0);
  await expect(page.getByTestId('transport-layer-toggle-highway_incident')).toHaveCount(0);
});
