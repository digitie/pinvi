import { expect, test, type Page } from '@playwright/test';

const tripId = '11111111-1111-4111-8111-111111111111';
const token = 'share-token-abc';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

async function routeSharedView(page: Page): Promise<void> {
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
              effective_date: '2026-07-01',
              title: '1일차',
              weather_cards: {
                'card:shared-busan': {
                  asof: '2026-07-01T00:00:00+09:00',
                  latest_at: '2026-07-01T09:00:00+09:00',
                  is_stale: false,
                  source_styles: ['observed'],
                  metrics: [
                    {
                      metric_key: 'T1H',
                      metric_name: '기온',
                      forecast_style: 'observed',
                      effective_at: '2026-07-01T09:00:00+09:00',
                      value_number: 24,
                      unit: '℃',
                    },
                  ],
                },
              },
              weather_by_feature_id: {
                'feat-1': { state: 'found', card_key: 'card:shared-busan' },
              },
              pois: [
                {
                  poi_id: '44444444-4444-4444-8444-444444444444',
                  feature_id: 'feat-1',
                  sort_order: '0100',
                  title: '해운대 해수욕장',
                  feature: { coord: { lon: 129.16, lat: 35.158 } },
                  marker_color: 'P-07',
                  marker_icon: 'swimming',
                  feature_resolution_state: 'found',
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
}

test('공유 링크로 읽기전용 여행 뷰가 로그인 없이 렌더링된다', async ({ page }) => {
  await routeSharedView(page);

  // ADR-076 — 공유 화면은 비로그인이라 /transport/*(로그인 필요)를 부르면 안 된다(401 → 로그인 이동).
  const transportRequests: string[] = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.includes('/transport/')) {
      transportRequests.push(request.url());
    }
  });

  await page.goto(`/shared/${tripId}/${token}`);

  await expect(page.getByText('공유된 여행')).toBeVisible();
  await expect(page.getByRole('heading', { name: '공유된 부산 여행' })).toBeVisible();
  await expect(page.getByTestId('trip-poi-list')).toContainText('해운대 해수욕장');
  await expect(page.getByLabel('장소 날씨')).toContainText('기온 24℃');

  // 읽기 전용 — 편집/삭제 버튼이 없다.
  await expect(page.getByRole('button', { name: '마커 편집' })).toHaveCount(0);
  expect(transportRequests).toEqual([]);
});

// #671 — 공유 토큰은 페이지 URL과 공유 API 호출 밖으로 나가면 안 된다(로그인 링크·prefetch·OAuth return_to).
test('공유 화면 로그인 링크는 토큰을 싣지 않고, 로그인 뒤 같은 탭이 공유 화면으로 돌아온다', async ({ page }) => {
  await routeSharedView(page);
  const authUser = {
    user_id: '88888888-8888-4888-8888-888888888888',
    email: 'viewer@example.com',
    nickname: '보는 사람',
    avatar_url: null,
    status: 'active',
    roles: ['user'],
    email_verified_at: '2026-06-01T09:00:00+09:00',
    has_password: true,
    oauth_identities: [],
  };
  await page.route(/.*\/auth\/oauth\/providers$/, (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: { providers: [] } }) }),
  );
  await page.route(/.*\/auth\/login$/, (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: authUser }) }),
  );

  const leaks: string[] = [];
  page.on('request', (request) => {
    const url = request.url();
    if (!url.includes(token)) return;
    const { pathname } = new URL(url);
    // 허용: 공유 화면 문서 자체와 공유 API(`/trips/{id}/shared/{token}…`).
    if (pathname === `/shared/${tripId}/${token}` || pathname.includes(`/trips/${tripId}/shared/${token}`)) return;
    leaks.push(url);
  });

  await page.goto(`/shared/${tripId}/${token}`);
  await expect(page.getByRole('heading', { name: '공유된 부산 여행' })).toBeVisible();

  const loginLinks = page.locator('a[href^="/login"]');
  expect(await loginLinks.count()).toBeGreaterThan(0);
  for (const href of await loginLinks.evaluateAll((els) => els.map((el) => el.getAttribute('href') ?? ''))) {
    expect(href).not.toContain(token);
    expect(href).toBe(`/login?next=${encodeURIComponent(`/shared/${tripId}`)}`);
  }

  await page.getByRole('banner').getByRole('link', { name: '로그인' }).click();
  await expect(page).toHaveURL(new RegExp(`/login\\?next=${encodeURIComponent(`/shared/${tripId}`)}$`));
  await page.getByTestId('login-email').fill('viewer@example.com');
  await page.getByTestId('login-password').fill('password-1234');
  await page.getByTestId('login-submit').click();

  await expect(page).toHaveURL(new RegExp(`/shared/${tripId}/${token}$`));
  await expect(page.getByRole('heading', { name: '공유된 부산 여행' })).toBeVisible();
  expect(leaks).toEqual([]);
});

test('토큰을 모르는 탭(새 탭 로그인)의 /shared/{tripId} 는 원래 탭으로 돌아가라고 안내한다', async ({ page }) => {
  await page.goto(`/shared/${tripId}`);
  await expect(page.getByTestId('shared-resume-missing')).toContainText('원래 탭으로 돌아가');
});
