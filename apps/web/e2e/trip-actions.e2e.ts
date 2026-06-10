import { expect, test } from '@playwright/test';

const tripId = '11111111-1111-4111-8111-111111111111';
const newTripId = '99999999-9999-4999-8999-999999999999';
const userId = '22222222-2222-4222-8222-222222222222';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

function tripResponse(id: string, title: string) {
  return {
    trip_id: id,
    owner_user_id: userId,
    title,
    description: null,
    region_hint: null,
    primary_region_code: null,
    primary_region_source: null,
    start_date: null,
    end_date: null,
    visibility: 'private',
    status: 'draft',
    version: 1,
    created_at: '2026-06-01T09:00:00+09:00',
    updated_at: '2026-06-01T09:00:00+09:00',
  };
}

async function commonRoutes(page: import('@playwright/test').Page) {
  await page.route(/.*\/auth\/me$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: { user_id: userId } }),
    });
  });
  await page.route(/.*\/trips\/[0-9a-f-]{36}\/comments(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
  });
  await page.route(/.*\/trips\/[0-9a-f-]{36}\/attachments$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
  });
  await page.route(/.*\/trips\/[0-9a-f-]{36}$/, async (route, request) => {
    if (request.method() === 'DELETE') {
      await route.fulfill({ status: 204, body: '' });
      return;
    }
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          trip: tripResponse(tripId, '액션 테스트 여행'),
          days: [],
          companions: [],
          share_links: [],
          broken_feature_count: 0,
        },
      }),
    });
  });
}

test('여행 복사 → 새 여행으로 이동', async ({ page }) => {
  await commonRoutes(page);

  await page.route(/.*\/trips\/[0-9a-f-]{36}\/copy$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          trip: tripResponse(newTripId, '액션 테스트 여행 (사본)'),
          created_trip: true,
          copied_day_count: 0,
          copied_poi_count: 0,
          copied_attachment_count: 0,
        },
      }),
    });
  });

  await page.goto(`/trips/${tripId}`);
  await expect(page.getByRole('heading', { name: '액션 테스트 여행' })).toBeVisible();

  await page.getByTestId('trip-actions').getByRole('button', { name: '복사' }).click();
  await expect(page).toHaveURL(new RegExp(`/trips/${newTripId}$`));
});

test('여행 삭제(확인) → 목록으로 이동', async ({ page }) => {
  await commonRoutes(page);
  await page.route(/.*\/trips(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
  });

  await page.goto(`/trips/${tripId}`);
  await page.getByTestId('trip-actions').getByRole('button', { name: '삭제' }).click();
  await page.getByTestId('trip-delete-confirm').click();

  await expect(page).toHaveURL(/\/trips$/);
  await expect(page.getByRole('heading', { name: '여행' })).toBeVisible();
});
