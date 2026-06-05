import { expect, test } from '@playwright/test';

const tripId = '11111111-1111-4111-8111-111111111111';
const userId = '22222222-2222-4222-8222-222222222222';
const noticePlanId = '33333333-3333-4333-8333-333333333333';

test('Trip 사용자 shell이 Trip API만 조회한다', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', (request) => requests.push(request.url()));

  await page.route(/.*\/trips(\?.*)?$/, async (route, request) => {
    if (!['fetch', 'xhr'].includes(request.resourceType())) {
      await route.continue();
      return;
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: [
          {
            trip_id: tripId,
            owner_user_id: userId,
            title: '서울 주말 산책',
            description: null,
            region_hint: '서울',
            start_date: '2026-06-20',
            end_date: '2026-06-21',
            visibility: 'private',
            status: 'planned',
            version: 1,
            created_at: '2026-06-01T09:00:00+09:00',
            updated_at: '2026-06-01T09:00:00+09:00',
          },
        ],
      }),
    });
  });

  await page.goto('/trips');

  await expect(page.getByRole('heading', { name: '여행' })).toBeVisible();
  await expect(page.getByTestId('trip-list')).toContainText('서울 주말 산책');
  await expect(page.getByTestId('app-nav--trips')).toBeVisible();

  expect(requests.some((url) => url.includes('/features/'))).toBe(false);
  expect(requests.some((url) => url.includes('9011'))).toBe(false);
});

test('notice plan 사용자 shell이 추천 plan API만 조회한다', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', (request) => requests.push(request.url()));

  await page.route(/.*\/notice-plans(\?.*)?$/, async (route, request) => {
    if (!['fetch', 'xhr'].includes(request.resourceType())) {
      await route.continue();
      return;
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: [
          {
            notice_plan_id: noticePlanId,
            slug: 'seoul-weekend',
            title: '서울 추천 주말 코스',
            category: 'recommended',
            summary: '가볍게 걷고 쉬는 서울 주말 코스',
            source_name: 'TripMate',
            destination: '서울',
            starts_on: '2026-06-20',
            ends_on: '2026-06-21',
            is_published: true,
            version: 1,
            created_at: '2026-06-01T09:00:00+09:00',
            updated_at: '2026-06-01T09:00:00+09:00',
            pois: [],
          },
        ],
      }),
    });
  });

  await page.goto('/notice-plans');

  await expect(page.getByRole('heading', { name: '추천 여행' })).toBeVisible();
  await expect(page.getByTestId('notice-plan-list')).toContainText('서울 추천 주말 코스');
  await expect(page.getByTestId('app-nav--notice-plans')).toBeVisible();

  expect(requests.some((url) => url.includes('/features/'))).toBe(false);
  expect(requests.some((url) => url.includes('9011'))).toBe(false);
});
