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

const requestId = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

const summary = {
  request_id: requestId,
  requester_user_id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
  requester_email_masked: 'r***@example.com',
  type: 'new_place',
  kind: 'place',
  name: '새 카페',
  coord: { lon: 129.0, lat: 35.0 },
  categories: ['카페'],
  note: '좋은 곳',
  target_feature_id: null,
  status: 'pending',
  krtour_ref: null,
  reviewed_by_admin_id: null,
  created_at: '2026-06-11T10:00:00+09:00',
  resolved_at: null,
};

test.beforeEach(async ({ page }) => {
  await page.route(
    (url) => url.port === '12501' && url.pathname === '/auth/me',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: adminUser }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12501' && url.pathname === '/admin/feature-requests',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: { items: [summary], total: 1, page: 1, limit: 50 } }),
      });
    },
  );
});

test('Admin이 feature 제안을 승인하면 krtour 전달 API를 호출한다', async ({ page }) => {
  let approveBody: Record<string, unknown> | null = null;
  await page.route(
    (url) => url.port === '12501' && url.pathname === `/admin/feature-requests/${requestId}/approve`,
    async (route) => {
      approveBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            request_id: requestId,
            status: 'added',
            krtour_ref: { feature_id: 'f_new_1' },
            reviewed_by_admin_id: adminUser.user_id,
            resolved_at: '2026-06-11T10:05:00+09:00',
          },
        }),
      });
    },
  );

  await page.goto('/admin/feature-requests');
  await expect(page.getByRole('heading', { name: 'Feature 제안 검토' })).toBeVisible();
  await expect(page.getByText('새 카페')).toBeVisible();

  await page.getByTestId(`admin-fr-review-${requestId}`).click();
  await expect(page.getByTestId('admin-fr-review-panel')).toBeVisible();

  await page.getByTestId('admin-fr-category').fill('01070100');
  await page.getByTestId('admin-fr-marker-color').fill('P-07');
  await page.getByTestId('admin-fr-marker-icon').fill('cafe');
  await page.getByTestId('admin-fr-reason').fill('실재 확인 완료');
  await page.getByTestId('admin-fr-approve').click();

  await expect(page.getByTestId('admin-fr-notice')).toBeVisible();
  expect(approveBody).toMatchObject({
    access_reason: '실재 확인 완료',
    category: '01070100',
    marker_color: 'P-07',
    marker_icon: 'cafe',
  });
});

test('신규 장소는 카테고리/마커 누락 시 승인 전 막힌다', async ({ page }) => {
  await page.goto('/admin/feature-requests');
  await page.getByTestId(`admin-fr-review-${requestId}`).click();
  await page.getByTestId('admin-fr-reason').fill('사유만 입력');
  await page.getByTestId('admin-fr-approve').click();
  await expect(page.getByTestId('admin-fr-panel-error')).toBeVisible();
});
