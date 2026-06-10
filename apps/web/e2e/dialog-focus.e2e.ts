import { expect, test } from '@playwright/test';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

async function mockInBounds(page: import('@playwright/test').Page) {
  await page.route(/.*\/features\/in-bounds(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          features: [],
          clusters: [],
          zoom: 12,
          bbox: { lng_min: 126.9, lat_min: 37.4, lng_max: 127.1, lat_max: 37.6 },
        },
      }),
    });
  });
}

test('다이얼로그가 열리면 첫 입력(이름)에 포커스가 간다', async ({ page }) => {
  await mockInBounds(page);
  await page.goto('/map?suggest=126.978,37.566');

  const dialog = page.getByTestId('feature-request-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel('이름')).toBeFocused();
});

test('이름 없이 제안하면 필드 오류 + aria-invalid + 포커스', async ({ page }) => {
  await mockInBounds(page);
  await page.goto('/map?suggest=126.978,37.566');

  const dialog = page.getByTestId('feature-request-dialog');
  await expect(dialog).toBeVisible();

  await page.getByTestId('feature-request-submit').click();

  const titleError = page.locator('#feature-request-title-error');
  await expect(titleError).toBeVisible();
  await expect(titleError).toHaveText(/이름/);
  await expect(dialog.getByLabel('이름')).toHaveAttribute('aria-invalid', 'true');
  await expect(dialog.getByLabel('이름')).toBeFocused();
});
