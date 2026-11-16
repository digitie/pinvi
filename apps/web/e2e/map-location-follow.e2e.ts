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
