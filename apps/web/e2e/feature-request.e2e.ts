import { expect, test } from '@playwright/test';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

// `/map?suggest=lon,lat` 딥링크로 장소 제안 다이얼로그가 좌표와 함께 열리고 제출된다.
test('장소 제안 딥링크로 다이얼로그를 열고 제출하면 접수된다', async ({ page }) => {
  // viewport feature 로딩(키 없으면 호출 안 됨 — 안전하게 mock).
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

  let requested = false;
  await page.route(/.*\/features\/requests$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    requested = true;
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          request_id: '88888888-8888-4888-8888-888888888888',
          status: 'pending',
          type: 'new_place',
          kind: 'place',
          title: '새 카페',
          coord: { lon: 126.978, lat: 37.566 },
          categories: [],
          note: null,
          target_feature_id: null,
          created_at: '2026-06-10T00:00:00Z',
          resolved_at: null,
        },
      }),
    });
  });

  await page.goto('/map?suggest=126.978,37.566');

  const dialog = page.getByTestId('feature-request-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('37.56600, 126.97800');

  await dialog.getByLabel('이름').fill('새 카페');
  await page.getByTestId('feature-request-submit').click();

  await expect(dialog).toContainText('제안이 접수됐습니다');
  expect(requested).toBe(true);
});
