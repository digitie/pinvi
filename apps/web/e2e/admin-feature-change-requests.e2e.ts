import { expect, test } from '@playwright/test';

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

const requestId = 'krq-1';

const baseRecord = {
  request_id: requestId,
  feature_id: 'f_place_1',
  action: 'add',
  status: 'pending',
  review_mode: 'require_review',
  payload: { name: '새 카페', category: '01070100' },
  reason: '사용자 제안 승인',
  requested_by: 'pinvi-admin',
  reviewed_by: null,
  reviewed_at: null,
  applied_at: null,
  created_at: '2026-06-12T00:00:00+09:00',
};

test.beforeEach(async ({ page }) => {
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/auth/me',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: adminUser }),
      });
    },
  );
});

test('Admin이 upstream feature 변경 요청을 승인하고 목록 상태를 갱신한다', async ({ page }) => {
  let approveBody: Record<string, unknown> | null = null;
  let status = 'pending';

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/features/change-requests',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [{ ...baseRecord, status }],
            review_mode: 'require_review',
            page_size: 100,
          },
        }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/features/change-requests/${requestId}/approve`,
    async (route) => {
      approveBody = route.request().postDataJSON() as Record<string, unknown>;
      status = 'applied';
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            ...baseRecord,
            status: 'applied',
            reason: '원천 확인',
            reviewed_by: 'pinvi-admin',
            reviewed_at: '2026-06-12T01:00:00+09:00',
            applied_at: '2026-06-12T01:00:01+09:00',
          },
        }),
      });
    },
  );

  await page.goto('/admin/features/change-requests');
  await expect(page.getByRole('heading', { name: 'Feature 변경 요청' })).toBeVisible();
  await expect(page.getByTestId(`admin-fcr-row-${requestId}`)).toBeVisible();

  await page.getByTestId(`admin-fcr-select-${requestId}`).click();
  await page.getByTestId('admin-fcr-reason').fill('Pinvi 운영 검수 완료');
  await page.getByTestId('admin-fcr-map-reason').fill('원천 확인');
  await page.getByTestId('admin-fcr-approve').click();

  await expect(page.getByTestId(`admin-fcr-status-${requestId}`)).toHaveText('반영');
  await expect(page.getByTestId('admin-fcr-notice')).toBeVisible();
  expect(approveBody).toMatchObject({
    access_reason: 'Pinvi 운영 검수 완료',
    kor_travel_map_reason: '원천 확인',
  });
});

test('upstream 거절 실패 시 optimistic 상태를 rollback하고 오류를 표시한다', async ({ page }) => {
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/features/change-requests',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [baseRecord],
            review_mode: 'require_review',
            page_size: 100,
          },
        }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/features/change-requests/${requestId}/reject`,
    async (route) => {
      await route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({
          error: {
            code: 'INVALID_STATE',
            message: '이미 처리된 변경 요청입니다.',
          },
        }),
      });
    },
  );

  await page.goto('/admin/features/change-requests');
  await page.getByTestId(`admin-fcr-select-${requestId}`).click();
  await page.getByTestId('admin-fcr-reason').fill('중복 변경 요청');
  await page.getByTestId('admin-fcr-reject').click();

  await expect(page.getByTestId('admin-fcr-mutation-error')).toContainText(
    '이미 처리된 변경 요청입니다.',
  );
  await expect(page.getByTestId(`admin-fcr-status-${requestId}`)).toHaveText('대기');
});

test('필터 값은 Pinvi proxy query로 전달된다', async ({ page }) => {
  const seenUrls: string[] = [];
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/features/change-requests',
    async (route) => {
      seenUrls.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [baseRecord],
            review_mode: 'require_review',
            page_size: 100,
          },
        }),
      });
    },
  );

  await page.goto('/admin/features/change-requests');
  await page.getByTestId('admin-fcr-search').fill('f_place_1');
  await page.getByTestId('admin-fcr-action-filter').selectOption('add');
  await page.getByTestId('admin-fcr-status-filter').selectOption('applied');
  await page.getByTestId('admin-fcr-search-submit').click();

  await expect(page.getByTestId(`admin-fcr-row-${requestId}`)).toBeVisible();
  const lastUrl = new URL(seenUrls[seenUrls.length - 1]!);
  expect(lastUrl.searchParams.get('q')).toBe('f_place_1');
  expect(lastUrl.searchParams.get('action')).toBe('add');
  expect(lastUrl.searchParams.get('status')).toBe('applied');
});
