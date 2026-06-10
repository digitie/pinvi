import { expect, test } from '@playwright/test';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

test.use({
  permissions: ['geolocation'],
  geolocation: { latitude: 37.5665, longitude: 126.978 },
});

test('내 위치는 위치 동의 후에만 동작한다', async ({ page }) => {
  let consented = false;

  await page.route(/.*\/users\/consents$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    if (request.method() === 'PUT') {
      consented = true;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: [
            { consent_type: 'lbs_tos', version: 'v1.0', agreed_at: '2026-06-10T00:00:00Z', withdrawn_at: null },
            {
              consent_type: 'location_collection',
              version: 'v1.0',
              agreed_at: '2026-06-10T00:00:00Z',
              withdrawn_at: null,
            },
          ],
        }),
      });
      return;
    }
    // GET — 최초엔 미동의(빈 목록).
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: consented ? [{ consent_type: 'lbs_tos', version: 'v1.0', agreed_at: '2026-06-10T00:00:00Z', withdrawn_at: null }] : [] }),
    });
  });

  await page.goto('/map');
  await expect(page.getByTestId('map-my-location')).toBeVisible();

  // 미동의 → 클릭 시 동의 다이얼로그.
  await page.getByTestId('map-my-location').click();
  const dialog = page.getByTestId('location-consent-dialog');
  await expect(dialog).toBeVisible();

  // 동의 → putConsents 후 다이얼로그 닫힘.
  await page.getByTestId('location-consent-agree').click();
  await expect(dialog).toBeHidden();
});
