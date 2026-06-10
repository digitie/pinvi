import { expect, test } from '@playwright/test';

const tripId = '11111111-1111-4111-8111-111111111111';
const userId = '22222222-2222-4222-8222-222222222222';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

function tripResponse(title: string) {
  return {
    trip_id: tripId,
    owner_user_id: userId,
    title,
    description: null,
    region_hint: '서울',
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

test('여행 메타 편집: 제목을 바꾸면 헤더에 반영된다', async ({ page }) => {
  let edited = false;

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
    if (request.method() === 'PATCH') {
      edited = true;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: tripResponse('수정된 제목') }),
      });
      return;
    }
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          trip: tripResponse(edited ? '수정된 제목' : '원래 제목'),
          days: [],
          companions: [],
          share_links: [],
          broken_feature_count: 0,
        },
      }),
    });
  });

  await page.goto(`/trips/${tripId}`);
  await expect(page.getByRole('heading', { name: '원래 제목' })).toBeVisible();

  await page.getByRole('button', { name: '편집' }).click();
  const dialog = page.getByTestId('trip-edit-dialog');
  await expect(dialog).toBeVisible();

  await dialog.getByLabel('제목').fill('수정된 제목');
  await page.getByTestId('trip-edit-save').click();

  await expect(dialog).toBeHidden();
  await expect(page.getByRole('heading', { name: '수정된 제목' })).toBeVisible();
});
