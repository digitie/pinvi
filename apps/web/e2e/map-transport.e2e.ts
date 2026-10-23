import { expect, test, type Page } from '@playwright/test';

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
    if (!isFetch(request.resourceType())) return route.continue();
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
    if (!isFetch(request.resourceType())) return route.continue();
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

  const controls = page.getByTestId('transport-layer-controls');
  await expect(controls).toBeVisible();
  const fuel = page.getByTestId('transport-layer-toggle-fuel_station');
  await expect(fuel).toHaveAttribute('aria-pressed', 'false');
  await fuel.click();
  await expect(fuel).toHaveAttribute('aria-pressed', 'true');
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
  await expect(page.getByTestId('transport-layer-controls')).toHaveCount(0);
});
