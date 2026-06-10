import { expect, test } from '@playwright/test';

const tripId = '11111111-1111-4111-8111-111111111111';
const token = 'share-token-abc';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

test('공유 링크로 읽기전용 여행 뷰가 로그인 없이 렌더링된다', async ({ page }) => {
  await page.route(/.*\/trips\/[0-9a-f-]{36}\/shared\/[^/]+$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          visibility: 'view_only',
          trip: {
            trip_id: tripId,
            owner_user_id: '22222222-2222-4222-8222-222222222222',
            title: '공유된 부산 여행',
            description: null,
            region_hint: '부산',
            primary_region_code: null,
            primary_region_source: null,
            start_date: '2026-07-01',
            end_date: '2026-07-03',
            visibility: 'unlisted',
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
                  poi_id: '44444444-4444-4444-8444-444444444444',
                  feature_id: 'feat-1',
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
          broken_feature_count: 0,
        },
      }),
    });
  });

  await page.goto(`/shared/${tripId}/${token}`);

  await expect(page.getByText('공유된 여행')).toBeVisible();
  await expect(page.getByRole('heading', { name: '공유된 부산 여행' })).toBeVisible();
  await expect(page.getByTestId('trip-poi-list')).toContainText('해운대 해수욕장');

  // 읽기 전용 — 편집/삭제 버튼이 없다.
  await expect(page.getByRole('button', { name: '마커 편집' })).toHaveCount(0);
});
