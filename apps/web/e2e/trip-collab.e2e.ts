import { expect, test } from '@playwright/test';

const tripId = '11111111-1111-4111-8111-111111111111';
const userId = '22222222-2222-4222-8222-222222222222';
const shareId = '77777777-7777-4777-8777-777777777777';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

function trip() {
  return {
    trip_id: tripId,
    owner_user_id: userId,
    title: '협업 테스트 여행',
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

function poi(id: string, sort: string, title: string, lon: number) {
  return {
    poi_id: id,
    feature_id: `feat-${id}`,
    sort_order: sort,
    title,
    feature: { coord: { lon, lat: 37.5 } },
    marker_color: 'P-01',
    marker_icon: 'marker',
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
  };
}

async function commonRoutes(
  page: import('@playwright/test').Page,
  shareLinks: unknown[] = []
) {
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
      body: JSON.stringify({
        data: {
          trip: trip(),
          days: [
            {
              day_index: 1,
              date: null,
              title: '1일차',
              pois: [
                poi('44444444-4444-4444-8444-444444444444', '0100', '장소 A', 126.9),
                poi('44444444-4444-4444-8444-444444444445', '0200', '장소 B', 127.1),
              ],
            },
          ],
          companions: [],
          share_links: shareLinks,
          broken_feature_count: 0,
        },
      }),
    });
  });
}

test('공유 링크를 만들면 생성된 URL이 1회 표시된다', async ({ page }) => {
  await commonRoutes(page);

  await page.route(/.*\/trips\/[0-9a-f-]{36}\/share-tokens$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          share_id: shareId,
          trip_id: tripId,
          visibility: 'view_only',
          token: 'tok-abc',
          url: 'http://127.0.0.1:12805/s/tok-abc',
          expires_at: null,
          revoked_at: null,
          last_used_at: null,
          created_at: '2026-06-01T09:00:00+09:00',
        },
      }),
    });
  });

  await page.goto(`/trips/${tripId}`);
  await expect(page.getByRole('heading', { name: '공유 링크' })).toBeVisible();

  await page.getByRole('button', { name: '링크 만들기' }).click();

  const banner = page.getByTestId('new-share-url');
  await expect(banner).toBeVisible();
  // 서버 url 대신 실제 공유 뷰 라우트(/shared/{tripId}/{token})로 구성된다.
  await expect(banner).toContainText(`/shared/${tripId}/tok-abc`);
  await expect(banner.getByRole('link', { name: '열기' })).toHaveAttribute(
    'href',
    `/shared/${tripId}/tok-abc`
  );
});

test('동선 최적화 미리보기 후 적용하면 패널이 닫힌다', async ({ page }) => {
  await commonRoutes(page);

  await page.route(/.*\/trips\/[0-9a-f-]{36}\/days\/\d+\/optimize$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          trip_id: tripId,
          day_index: 1,
          ordered_poi_ids: [
            '44444444-4444-4444-8444-444444444445',
            '44444444-4444-4444-8444-444444444444',
          ],
          moves: [
            {
              poi_id: '44444444-4444-4444-8444-444444444445',
              old_sort_order: '0200',
              new_sort_order: '0050',
            },
          ],
          distance_meters: 1800,
          warnings: [],
        },
      }),
    });
  });

  await page.goto(`/trips/${tripId}`);
  await page.getByRole('button', { name: '동선 최적화' }).click();

  await expect(page.getByText('최단 경로 추정 거리')).toBeVisible();
  await expect(page.getByText('1.8km')).toBeVisible();

  await page.getByRole('button', { name: '적용' }).click();
  await expect(page.getByText('최단 경로 추정 거리')).toBeHidden();
});
