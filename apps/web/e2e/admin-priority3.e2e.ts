import { expect, test } from '@playwright/test';
import type { AdminApiCallEntry, AdminLocationAuditEntry } from '@tripmate/schemas';

const adminUser = {
  user_id: '77777777-7777-4777-8777-777777777777',
  email: 'admin@example.com',
  nickname: '관리자',
  avatar_url: null,
  status: 'active',
  roles: ['user', 'admin', 'cpo'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

const apiCall: AdminApiCallEntry = {
  log_id: 10,
  provider: 'kma',
  endpoint: '/weather/current',
  status_code: 200,
  latency_ms: 42,
  error_class: null,
  error_message: null,
  request_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  occurred_at: '2026-06-09T10:00:00+09:00',
};

const locationAudit: AdminLocationAuditEntry = {
  log_id: 20,
  user_id: '99999999-9999-4999-8999-999999999999',
  occurred_at: '2026-06-09T11:00:00+09:00',
  endpoint: '/features/in-bounds',
  purpose: 'viewport_query',
  lat_masked: '37.5666',
  lng_masked: '126.9781',
  request_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  ip_hash: 'a'.repeat(64),
  prev_hash: '0'.repeat(64),
  content_hash: '1'.repeat(64),
};

test.beforeEach(async ({ page }) => {
  await page.route(
    (url) => url.port === '9021' && url.pathname === '/auth/me',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: adminUser }),
      });
    },
  );
});

test('Admin 대시보드가 앱 소유 통계를 표시한다', async ({ page }) => {
  await page.route(
    (url) => url.port === '9021' && url.pathname === '/admin/stats/overview',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            users_total: 12,
            users_24h: 3,
            users_pending_verification: 2,
            trips_total: 7,
            trips_active: 4,
            pois_total: 31,
            email_queue_pending: 5,
            api_calls_24h: 21,
            api_calls_failed_24h: 1,
            features_by_kind: {},
            etl_last_24h: { success: 0, failed: 0 },
          },
        }),
      });
    },
  );

  await page.goto('/admin');

  await expect(page.getByRole('heading', { name: '대시보드' })).toBeVisible();
  await expect(page.getByTestId('admin-stat-사용자 총 수')).toContainText('12');
  await expect(page.getByTestId('admin-stat-API 실패 24h')).toContainText('1');
  await expect(page.getByText('Feature / ETL / seed-reset')).toBeVisible();
});

test('Admin API 호출 로그가 필터를 API에 전달한다', async ({ page }) => {
  const requests: string[] = [];

  await page.route(
    (url) => url.port === '9021' && url.pathname === '/admin/api-calls',
    async (route) => {
      requests.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: [apiCall] }),
      });
    },
  );

  await page.goto('/admin/api-calls');

  await expect(page.getByRole('heading', { name: 'API 호출 로그' })).toBeVisible();
  await expect(page.getByText('/weather/current')).toBeVisible();

  await page.getByTestId('admin-api-calls-provider').fill('kma');
  await page.getByTestId('admin-api-calls-status').fill('200');
  await page.getByTestId('admin-api-calls-submit').click();

  await expect
    .poll(() =>
      requests.some((url) => url.includes('provider=kma') && url.includes('status_code=200')),
    )
    .toBe(true);
  expect(requests.some((url) => url.includes('9011'))).toBe(false);
});

test('CPO 위치 감사 로그가 마스킹 좌표와 날짜 필터를 표시한다', async ({ page }) => {
  const requests: string[] = [];

  await page.route(
    (url) => url.port === '9021' && url.pathname === '/admin/audit/location',
    async (route) => {
      requests.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: [locationAudit] }),
      });
    },
  );

  await page.goto('/admin/audit/location');

  await expect(page.getByRole('heading', { name: '위치 감사 로그' })).toBeVisible();
  await expect(page.getByText('126.9781, 37.5666')).toBeVisible();
  await expect(page.getByText('37.566567')).toHaveCount(0);

  await page.getByTestId('admin-location-user').fill(locationAudit.user_id);
  await page.getByTestId('admin-location-from').fill('2026-06-09T00:00');
  await page.getByTestId('admin-location-to').fill('2026-06-10T00:00');
  await page.getByTestId('admin-location-submit').click();

  await expect
    .poll(() =>
      requests.some(
        (url) =>
          url.includes(`user_id=${locationAudit.user_id}`) &&
          url.includes('from=') &&
          url.includes('to='),
      ),
    )
    .toBe(true);
  expect(requests.some((url) => url.includes('9011'))).toBe(false);
});
