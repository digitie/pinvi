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

const targetUserId = '99999999-9999-4999-8999-999999999999';

const maskedUser = {
  user_id: targetUserId,
  email_masked: 's***@example.com',
  email: 's***@example.com',
  email_revealed: false,
  nickname: '비밀사용자',
  status: 'active',
  roles: ['user'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  created_at: '2026-06-01T09:00:00+09:00',
  email_status: 'active',
  is_active: true,
  recent_audit: [],
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

test('Admin 사용자 목록이 검색어와 상태 필터를 API에 전달한다', async ({ page }) => {
  const listRequests: string[] = [];

  await page.route(
    (url) => url.port === '9021' && url.pathname === '/admin/users',
    async (route) => {
      listRequests.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [
              {
                user_id: targetUserId,
                email_masked: 'k***@example.com',
                nickname: '김여행',
                status: 'active',
                roles: ['user'],
                email_verified_at: '2026-06-01T09:00:00+09:00',
                created_at: '2026-06-01T09:00:00+09:00',
              },
            ],
            total: 1,
            page: 1,
            limit: 50,
          },
        }),
      });
    },
  );

  await page.goto('/admin/users');
  await expect(page.getByRole('heading', { name: '사용자' })).toBeVisible();
  await expect(page.getByText('김여행')).toBeVisible();

  await page.getByTestId('admin-users-search').fill('kim');
  await page.getByTestId('admin-users-search-submit').click();
  await expect
    .poll(() => listRequests.some((url) => url.includes('q=kim')))
    .toBe(true);

  await page.getByTestId('admin-users-status-filter').selectOption('active');
  await expect
    .poll(() =>
      listRequests.some(
        (url) => url.includes('q=kim') && url.includes('status_filter=active'),
      ),
    )
    .toBe(true);

  expect(listRequests.some((url) => url.includes('/features/'))).toBe(false);
  expect(listRequests.some((url) => url.includes('9011'))).toBe(false);
});

test('Admin 사용자 상세가 사유와 함께 이메일 원본 조회 audit을 표시한다', async ({ page }) => {
  let revealReason: string | null = null;
  let revealUrl: string | null = null;

  await page.route(
    (url) => url.port === '9021' && url.pathname === `/admin/users/${targetUserId}`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: maskedUser,
        }),
      });
    },
  );

  await page.route(
    (url) => url.port === '9021' && url.pathname === `/admin/users/${targetUserId}/reveal-pii`,
    async (route) => {
      const body = route.request().postDataJSON() as { access_reason?: string } | null;
      revealUrl = route.request().url();
      revealReason = body?.access_reason ?? null;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            ...maskedUser,
            email: 'secret@example.com',
            email_revealed: true,
            recent_audit: [
              {
                log_id: 12,
                actor_user_id: adminUser.user_id,
                action: 'user.reveal_pii',
                resource_type: 'user',
                resource_id: targetUserId,
                access_reason: '고객 문의 확인',
                target_pii_fields: ['email'],
                prev_hash: '0'.repeat(64),
                content_hash: '1'.repeat(64),
                occurred_at: '2026-06-06T12:00:00+09:00',
              },
            ],
          },
        }),
      });
    },
  );

  await page.goto(`/admin/users/${targetUserId}`);

  await expect(page.getByTestId('admin-user-email')).toContainText('s***@example.com');
  await page.getByTestId('admin-user-reveal-email').click();
  await page.getByTestId('admin-user-action-reason').fill('고객 문의 확인');
  await page.getByTestId('admin-user-action-confirm').click();

  await expect(page.getByTestId('admin-user-email')).toContainText('secret@example.com');
  await expect(page.getByTestId('admin-user-audit-list')).toContainText('user.reveal_pii');
  expect(revealReason).toBe('고객 문의 확인');
  expect(revealUrl).not.toContain('access_reason');
});
