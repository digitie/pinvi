import { expect, test } from '@playwright/test';

const tripId = '11111111-1111-4111-8111-111111111111';
const userId = '22222222-2222-4222-8222-222222222222';
const poiId = '44444444-4444-4444-8444-444444444444';
const companionId = '55555555-5555-4555-8555-555555555555';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

const TRIP_VIEW = {
  trip: {
    trip_id: tripId,
    owner_user_id: userId,
    title: '부산 2박 3일',
    description: null,
    region_hint: '부산',
    primary_region_code: '26',
    primary_region_source: 'manual',
    start_date: '2026-07-01',
    end_date: '2026-07-03',
    visibility: 'private',
    status: 'planned',
    version: 1,
    created_at: '2026-06-01T09:00:00+09:00',
    updated_at: '2026-06-01T09:00:00+09:00',
  },
  days: [
    {
      day_index: 1,
      date: '2026-07-01',
      title: '1일차',
      pois: [
        {
          poi_id: poiId,
          feature_id: 'feat-haeundae',
          sort_order: '0100',
          title: '해운대 해수욕장',
          feature: { coord: { lon: 129.16, lat: 35.158 } },
          marker_color: 'P-07',
          marker_icon: 'swimming',
          is_broken: false,
          user_note: null,
          planned_arrival_at: null,
          planned_departure_at: null,
          budget_amount: null,
          actual_amount: null,
          currency: 'KRW',
          user_url: null,
          rise_set: null,
          feature_link_broken_at: null,
          version: 1,
          created_at: '2026-06-01T09:00:00+09:00',
          updated_at: '2026-06-01T09:00:00+09:00',
        },
      ],
    },
  ],
  companions: [
    {
      companion_id: companionId,
      trip_id: tripId,
      user_id: null,
      invited_email: 'friend@example.com',
      invited_nickname: '동행',
      role: 'editor',
      invited_at: '2026-06-01T09:00:00+09:00',
      joined_at: null,
      created_at: '2026-06-01T09:00:00+09:00',
      updated_at: '2026-06-01T09:00:00+09:00',
    },
  ],
  share_links: [],
  broken_feature_count: 0,
};

test('trip 상세가 TripView를 받아 헤더·POI·협업 섹션을 렌더링한다', async ({ page }) => {
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
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: TRIP_VIEW }),
    });
  });

  await page.goto(`/trips/${tripId}`);

  await expect(page.getByRole('heading', { name: '부산 2박 3일' })).toBeVisible();
  await expect(page.getByRole('tab', { name: '1일차' })).toBeVisible();
  await expect(page.getByTestId('trip-poi-list')).toContainText('해운대 해수욕장');
  await expect(page.getByTestId('companion-list')).toContainText('동행');
  await expect(page.getByRole('heading', { name: '공유 링크' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '첨부' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '댓글' })).toBeVisible();
});
