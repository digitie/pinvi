import { expect, test } from '@playwright/test';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

// 탐색 지도(`/map`) — VWorld 키 유무와 무관하게 셸 + 컨트롤이 렌더된다.
test('탐색 지도가 검색·내 위치 컨트롤과 함께 렌더링된다', async ({ page }) => {
  // 키가 있으면 onLoad 에서 in-bounds 를 부르므로 mock(없으면 호출 안 됨 — 둘 다 허용).
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

  await page.goto('/map');

  await expect(page.getByRole('heading', { name: '탐색 지도' })).toBeVisible();
  await expect(page.getByTestId('map-search')).toBeVisible();
  await expect(page.getByTestId('map-my-location')).toBeVisible();
  await expect(page.getByTestId('feature-map')).toBeVisible();

  // VWorld 키 미설정 시 fallback, 설정 시 canvas — 둘 중 하나는 보여야 한다.
  const fallback = page.getByTestId('vworld-map-fallback');
  const canvas = page.locator('.maplibregl-canvas').first();
  await expect(fallback.or(canvas)).toBeVisible();
});

// 2026-11-02 prod e2e — 데스크톱 탐색 지도가 테두리 상자를 다 채우지 못하고 360px(min-h)에서 멈춰
// 아래 절반 이상이 비었다. 지도(또는 키가 없을 때의 fallback)는 지도 상자 높이를 채워야 한다.
test('탐색 지도는 데스크톱에서 지도 상자 높이를 채운다', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
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

  await page.goto('/map');

  // 테두리 지도 상자 = `feature-map`의 첫 자식(검색·지도 영역).
  const frame = page.getByTestId('feature-map').locator(':scope > div').first();
  const surface = page
    .getByTestId('vworld-map-fallback')
    .or(page.getByTestId('vworld-map-container'))
    .first();
  await expect(surface).toBeVisible();
  const frameBox = await frame.boundingBox();
  const surfaceBox = await surface.boundingBox();
  expect(frameBox).not.toBeNull();
  expect(surfaceBox).not.toBeNull();
  expect(frameBox!.height).toBeGreaterThan(450);
  expect(Math.abs(surfaceBox!.height - frameBox!.height)).toBeLessThanOrEqual(4);
});
