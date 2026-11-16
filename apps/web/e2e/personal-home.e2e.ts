import { expect, test, type Page } from './fixtures';

/**
 * 개인 홈(/home) — 로고·'홈'이 로그인 사용자를 마케팅 랜딩(로그인 CTA)이 아니라 개인 홈으로 보낸다.
 */

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);
const apiPath = (path: string) => (url: URL) => url.port === '12801' && url.pathname === path;

const home = {
  today: '2026-11-16',
  stats: {
    trip_count: 4,
    upcoming_trip_count: 1,
    ongoing_trip_count: 0,
    completed_trip_count: 2,
    undated_trip_count: 1,
    travel_day_count: 5,
    visited_place_count: 7,
    region_count: 2,
  },
  next_trip: {
    trip_id: '11111111-1111-4111-8111-111111111111',
    title: '다음 제주',
    region_hint: '제주',
    region_name: '제주',
    start_date: '2026-11-21',
    end_date: '2026-11-22',
    phase: 'upcoming',
    days_until: 5,
    place_count: 3,
  },
  upcoming_trips: [],
  recent_trips: [
    {
      trip_id: '33333333-3333-4333-8333-333333333333',
      title: '지난 강릉',
      region_hint: '강릉',
      region_name: '강원',
      start_date: '2026-11-01',
      end_date: '2026-11-02',
      phase: 'completed',
      days_until: null,
      place_count: 4,
    },
  ],
  recent_places: [
    {
      poi_id: '22222222-2222-4222-8222-222222222222',
      trip_id: '33333333-3333-4333-8333-333333333333',
      trip_title: '지난 강릉',
      name: '경포해변',
      category: null,
      visited_on: '2026-11-01',
      region_name: '강원',
    },
  ],
  regions: [
    { code: '51', name: '강원', place_count: 4, trip_count: 1 },
    { code: '47', name: '경북', place_count: 3, trip_count: 1 },
  ],
};

async function signedIn(page: Page) {
  await page.route(apiPath('/auth/me'), (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: {} }) }),
  );
  await page.route(apiPath('/users/me/home'), (route, request) =>
    isFetch(request.resourceType())
      ? route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: home }) })
      : route.fallback(),
  );
}

test('로그인 사용자가 랜딩(/)에 오면 개인 홈으로 가고 통계가 보인다', async ({ page }) => {
  await signedIn(page);
  await page.goto('/');
  await expect(page).toHaveURL(/\/home$/);
  const root = page.getByTestId('personal-home');
  await expect(root.getByRole('heading', { name: '내 여행', level: 1 })).toBeVisible();
  await expect(page.getByTestId('home-next-trip')).toContainText('다음 제주');
  await expect(page.getByTestId('home-next-trip-badge')).toHaveText('D-5');
  await expect(page.getByTestId('home-stat-trips')).toContainText('2');
  await expect(page.getByTestId('home-stat-days')).toContainText('5');
  await expect(page.getByTestId('home-stat-places')).toContainText('7');
  await expect(page.getByTestId('home-stat-regions')).toContainText('2/17');
  await expect(page.getByTestId('home-regions')).toContainText('강원');
  await expect(page.getByTestId('home-recent')).toContainText('지난 강릉');
  await expect(page.getByTestId('home-places')).toContainText('경포해변');
});

test('앱 셸의 로고는 개인 홈으로 간다', async ({ page }) => {
  await signedIn(page);
  await page.goto('/home');
  await expect(page.getByTestId('home-stats')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Pinvi 홈' })).toHaveAttribute('href', '/home');
});

test('익명 방문자는 랜딩에 머문다', async ({ page }) => {
  await page.route(apiPath('/auth/me'), (route) =>
    route.fulfill({ status: 401, contentType: 'application/json', body: '{}' }),
  );
  const checked = page.waitForResponse((response) => apiPath('/auth/me')(new URL(response.url())));
  await page.goto('/');
  await checked;
  await expect(page.getByTestId('home-hero')).toBeVisible();
  await expect(page).toHaveURL(/\/$/);
});
