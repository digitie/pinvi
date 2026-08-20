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
  kor_travel_map_ref: null,
  reviewed_by_admin_id: null,
  created_at: '2026-06-11T10:00:00+09:00',
  resolved_at: null,
};

const correctionRequestId = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd';
const correctionSummary = {
  ...summary,
  request_id: correctionRequestId,
  type: 'correction',
  target_feature_id: '01900000-0000-7000-8000-000000000001',
  name: '수정 전 장소',
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
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/feature-requests',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: { items: [summary, correctionSummary], total: 2, page: 1, limit: 50 },
        }),
      });
    },
  );
});

test('Admin이 신규 장소를 승인하면 저장된 payload를 Map 요청 큐에 제출한다', async ({ page }) => {
  let approveBody: Record<string, unknown> | null = null;
  await page.route(
    (url) =>
      url.port === '12801' && url.pathname === `/admin/feature-requests/${requestId}/approve`,
    async (route) => {
      approveBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            request_id: requestId,
            status: 'approved',
            kor_travel_map_ref: {
              request_id: requestId,
              state: 'pending',
              review_mode: 'feature_request_queue',
              action: 'submit',
            },
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

  await expect(page.getByTestId('admin-fr-queue-payload-notice')).toBeVisible();
  await expect(page.getByTestId('admin-fr-category')).toHaveCount(0);
  await expect(page.getByTestId('admin-fr-marker-color')).toHaveCount(0);
  await expect(page.getByTestId('admin-fr-marker-icon')).toHaveCount(0);
  await page.getByTestId('admin-fr-reason').fill('실재 확인 완료');
  await page.getByTestId('admin-fr-approve').click();

  await expect(page.getByTestId('admin-fr-notice')).toBeVisible();
  expect(approveBody).toEqual({ access_reason: '실재 확인 완료' });
});

test('신규 장소는 카테고리/마커 없이도 저장된 요청을 제출할 수 있다', async ({ page }) => {
  await page.route(
    (url) =>
      url.port === '12801' && url.pathname === `/admin/feature-requests/${requestId}/approve`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            request_id: requestId,
            status: 'approved',
            kor_travel_map_ref: { request_id: requestId, state: 'pending' },
            reviewed_by_admin_id: adminUser.user_id,
            resolved_at: '2026-06-11T10:05:00+09:00',
          },
        }),
      });
    },
  );
  await page.goto('/admin/feature-requests');
  await page.getByTestId(`admin-fr-review-${requestId}`).click();
  await page.getByTestId('admin-fr-reason').fill('사유만 입력');
  await page.getByTestId('admin-fr-approve').click();
  await expect(page.getByTestId('admin-fr-notice')).toBeVisible();
});

test('Admin이 정보 수정 승인에 명시한 변경 필드를 전달한다', async ({ page }) => {
  let approveBody: Record<string, unknown> | null = null;
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/feature-requests/${correctionRequestId}/approve`,
    async (route) => {
      approveBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            request_id: correctionRequestId,
            status: 'added',
            kor_travel_map_ref: { feature_id: '01900000-0000-7000-8000-000000000001' },
            reviewed_by_admin_id: adminUser.user_id,
            resolved_at: '2026-06-11T10:05:00+09:00',
          },
        }),
      });
    },
  );

  await page.goto('/admin/feature-requests');
  await page.getByTestId(`admin-fr-review-${correctionRequestId}`).click();
  await page.getByTestId('admin-fr-name').fill('수정 후 장소');
  await page.getByTestId('admin-fr-category').fill('01070100');
  await page.getByTestId('admin-fr-reason').fill('현장 재확인');
  await page.getByTestId('admin-fr-approve').click();

  await expect(page.getByTestId('admin-fr-notice')).toBeVisible();
  expect(approveBody).toMatchObject({
    access_reason: '현장 재확인',
    name: '수정 후 장소',
    category: '01070100',
  });
});
