import { expect, test } from '@playwright/test';
import type { AdminTripDetail, AdminTripSummary } from '@tripmate/schemas';

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

const tripId = '88888888-8888-4888-8888-888888888888';
const ownerUserId = '99999999-9999-4999-8999-999999999999';

const tripSummary: AdminTripSummary = {
  trip_id: tripId,
  owner_user_id: ownerUserId,
  owner_email_masked: 'o***@example.com',
  title: '부산 가족 여행',
  region_hint: '부산',
  start_date: '2026-07-01',
  end_date: '2026-07-03',
  visibility: 'private',
  status: 'planned',
  version: 1,
  day_count: 2,
  poi_count: 3,
  companion_count: 1,
  share_link_count: 1,
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

test('Admin 여행 목록이 검색어와 필터를 API에 전달한다', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', (request) => requests.push(request.url()));

  await page.route(
    (url) => url.port === '9021' && url.pathname === '/admin/trips',
    async (route) => {
      requests.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [tripSummary],
            total: 1,
            page: 1,
            limit: 50,
          },
        }),
      });
    },
  );

  await page.goto('/admin/trips');
  await expect(page.getByRole('heading', { name: '여행' })).toBeVisible();
  await expect(page.getByText('부산 가족 여행')).toBeVisible();

  await page.getByTestId('admin-trips-search').fill('busan');
  await page.getByTestId('admin-trips-search-submit').click();
  await expect.poll(() => requests.some((url) => url.includes('q=busan'))).toBe(true);

  await page.getByTestId('admin-trips-status-filter').selectOption('planned');
  await page.getByTestId('admin-trips-visibility-filter').selectOption('private');
  await expect
    .poll(() =>
      requests.some(
        (url) =>
          url.includes('q=busan') &&
          url.includes('status_filter=planned') &&
          url.includes('visibility_filter=private'),
      ),
    )
    .toBe(true);

  expect(requests.some((url) => url.includes('/features/'))).toBe(false);
  expect(requests.some((url) => url.includes('9011'))).toBe(false);
});

test('Admin 여행 상세가 상태 변경 audit을 표시한다', async ({ page }) => {
  const requests: string[] = [];
  let patchReason: string | null = null;
  let currentTrip: AdminTripDetail = {
    ...tripSummary,
    description: '운영자가 확인할 여행 상세',
    companions: [
      {
        companion_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        user_id: null,
        invited_email_masked: 'f***@example.com',
        invited_nickname: '친구',
        role: 'editor',
        invited_at: '2026-06-06T10:00:00+09:00',
        joined_at: null,
      },
    ],
    share_links: [
      {
        share_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        visibility: 'view_only',
        expires_at: '2026-07-01T10:00:00+09:00',
        revoked_at: null,
        last_used_at: null,
        created_at: '2026-06-06T10:00:00+09:00',
      },
    ],
    recent_audit: [],
  };

  page.on('request', (request) => requests.push(request.url()));

  await page.route(
    (url) => url.port === '9021' && url.pathname === `/admin/trips/${tripId}`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: currentTrip }),
      });
    },
  );

  await page.route(
    (url) => url.port === '9021' && url.pathname === `/admin/trips/${tripId}/status`,
    async (route) => {
      const body = route.request().postDataJSON() as {
        status: 'archived';
        access_reason: string;
      };
      patchReason = body.access_reason;
      currentTrip = {
        ...currentTrip,
        status: body.status,
        version: 2,
        recent_audit: [
          {
            log_id: 20,
            actor_user_id: adminUser.user_id,
            action: 'trip.update_status',
            resource_type: 'trip',
            resource_id: tripId,
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
        body: JSON.stringify({ data: currentTrip }),
      });
    },
  );

  await page.goto(`/admin/trips/${tripId}`);

  await expect(page.getByRole('heading', { name: '부산 가족 여행' })).toBeVisible();
  await expect(page.getByTestId('admin-trip-companions')).toContainText('f***@example.com');
  await expect(page.getByTestId('admin-trip-share-links')).toContainText('view_only');

  await page.getByTestId('admin-trip-status-select').selectOption('archived');
  await page.getByTestId('admin-trip-status-save').click();
  await page.getByTestId('admin-trip-action-reason').fill('운영 정책 위반 처리');
  await page.getByTestId('admin-trip-action-confirm').click();

  await expect(page.getByTestId('admin-trip-audit-list')).toContainText(
    'trip.update_status',
  );
  expect(patchReason).toBe('운영 정책 위반 처리');
  expect(requests.some((url) => url.includes('/features/'))).toBe(false);
  expect(requests.some((url) => url.includes('9011'))).toBe(false);
});
