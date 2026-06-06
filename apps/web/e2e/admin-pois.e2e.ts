import { expect, test } from '@playwright/test';
import type { AdminPoiDetail, AdminPoiSummary } from '@tripmate/schemas';

const adminUser = {
  user_id: '77777777-7777-4777-8777-777777777777',
  email: 'admin@example.com',
  nickname: '관리자',
  avatar_url: null,
  status: 'active',
  roles: ['user', 'admin'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

const poiId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const tripId = '88888888-8888-4888-8888-888888888888';
const ownerUserId = '99999999-9999-4999-8999-999999999999';
const addedByUserId = '66666666-6666-4666-8666-666666666666';

const poiSummary: AdminPoiSummary = {
  attachment_id: poiId,
  trip_id: tripId,
  trip_title: '부산 가족 여행',
  owner_user_id: ownerUserId,
  owner_email_masked: 'o***@example.com',
  day_index: 1,
  sort_order: 'a0',
  feature_id: 'place-haeundae',
  feature_label: '해운대 해수욕장',
  feature_link_broken_at: null,
  version: 1,
  created_at: '2026-06-06T10:00:00+09:00',
  updated_at: '2026-06-06T11:00:00+09:00',
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

test('Admin POI 목록이 검색어와 연결 필터를 API에 전달한다', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', (request) => requests.push(request.url()));

  await page.route(
    (url) => url.port === '9021' && url.pathname === '/admin/pois',
    async (route) => {
      requests.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [poiSummary],
            total: 1,
            page: 1,
            limit: 50,
          },
        }),
      });
    },
  );

  await page.goto('/admin/pois');
  await expect(page.getByRole('heading', { name: 'POI' })).toBeVisible();
  await expect(page.getByText('해운대 해수욕장')).toBeVisible();

  await page.getByTestId('admin-pois-search').fill('haeundae');
  await page.getByTestId('admin-pois-search-submit').click();
  await expect.poll(() => requests.some((url) => url.includes('q=haeundae'))).toBe(true);

  await page.getByTestId('admin-pois-broken-filter').selectOption('false');
  await expect
    .poll(() =>
      requests.some(
        (url) => url.includes('q=haeundae') && url.includes('has_broken_link=false'),
      ),
    )
    .toBe(true);

  await page.getByTestId('admin-pois-broken-filter').selectOption('true');
  await expect
    .poll(() =>
      requests.some(
        (url) => url.includes('q=haeundae') && url.includes('has_broken_link=true'),
      ),
    )
    .toBe(true);

  expect(requests.some((url) => url.includes('/features/'))).toBe(false);
  expect(requests.some((url) => url.includes('9011'))).toBe(false);
});

test('Admin POI 상세가 연결 상태 변경 audit을 표시한다', async ({ page }) => {
  const requests: string[] = [];
  let patchReason: string | null = null;
  let currentPoi: AdminPoiDetail = {
    ...poiSummary,
    added_by_user_id: addedByUserId,
    added_by_email_masked: 'p***@example.com',
    feature_snapshot: {
      name: '해운대 해수욕장',
      category: 'beach',
    },
    custom_marker_color: '#3366ff',
    custom_marker_icon: 'beach',
    planned_arrival_at: '2026-07-01T11:00:00+09:00',
    planned_departure_at: '2026-07-01T13:00:00+09:00',
    user_note: '점심 전에 도착',
    budget_amount: '12000.00',
    actual_amount: '10000.00',
    currency: 'KRW',
    user_url: 'https://example.com/haeundae',
    recent_audit: [],
  };

  page.on('request', (request) => requests.push(request.url()));

  await page.route(
    (url) => url.port === '9021' && url.pathname === `/admin/pois/${poiId}`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: currentPoi }),
      });
    },
  );

  await page.route(
    (url) => url.port === '9021' && url.pathname === `/admin/pois/${poiId}/link-status`,
    async (route) => {
      const body = route.request().postDataJSON() as {
        broken: boolean;
        access_reason: string;
      };
      patchReason = body.access_reason;
      currentPoi = {
        ...currentPoi,
        feature_link_broken_at: body.broken ? '2026-06-06T12:00:00+09:00' : null,
        version: 2,
        recent_audit: [
          {
            log_id: 30,
            actor_user_id: adminUser.user_id,
            action: 'poi.update_link_status',
            resource_type: 'poi',
            resource_id: poiId,
            access_reason: body.access_reason,
            target_pii_fields: null,
            prev_hash: '0'.repeat(64),
            content_hash: '1'.repeat(64),
            occurred_at: '2026-06-06T12:00:00+09:00',
          },
        ],
      };
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: currentPoi }),
      });
    },
  );

  await page.goto(`/admin/pois/${poiId}`);

  await expect(page.getByRole('heading', { name: '해운대 해수욕장' })).toBeVisible();
  await expect(page.getByTestId('admin-poi-info')).toContainText('p***@example.com');
  await expect(page.getByTestId('admin-poi-snapshot')).toContainText('beach');

  await page.getByTestId('admin-poi-link-status').selectOption('broken');
  await page.getByTestId('admin-poi-link-status-save').click();
  await page.getByTestId('admin-poi-action-reason').fill('feature_id 점검 결과 끊김');
  await page.getByTestId('admin-poi-action-confirm').click();

  await expect(page.getByTestId('admin-poi-audit-list')).toContainText(
    'poi.update_link_status',
  );
  expect(patchReason).toBe('feature_id 점검 결과 끊김');
  expect(requests.some((url) => url.includes('/features/'))).toBe(false);
  expect(requests.some((url) => url.includes('9011'))).toBe(false);
});
