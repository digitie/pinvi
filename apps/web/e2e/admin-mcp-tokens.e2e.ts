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

test.beforeEach(async ({ page }) => {
  await page.route(
    (url) => url.port === '12501' && url.pathname === '/auth/me',
    async (route) => {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: adminUser }) });
    },
  );
  // 포트 12501(API)로 한정 — 12505 페이지 내비게이션을 가로채지 않도록.
  await page.route(
    (url) => url.port === '12501' && url.pathname === '/admin/mcp-tokens',
    async (route, request) => {
      if (request.method() !== 'GET') return route.continue();
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
    },
  );
});

test('MCP 토큰 발급 폼이 시각적 라벨을 갖는다(label↔input 연결)', async ({ page }) => {
  await page.goto('/admin/mcp-tokens');
  await expect(page.getByRole('heading', { name: 'MCP 토큰' })).toBeVisible();

  // FormField/FormSelect가 시각적 라벨을 노출 → getByLabel로 접근 가능.
  await expect(page.getByLabel('대상 user_id')).toBeVisible();
  await expect(page.getByLabel('토큰 이름')).toBeVisible();
  await expect(page.getByLabel('만료')).toBeVisible();
  await expect(page.getByLabel('발급 사유')).toBeVisible();
  await expect(page.getByLabel('회수 사유')).toBeVisible();
});

test('user_id 없이 발급하면 필드 오류 + aria-invalid + 포커스', async ({ page }) => {
  await page.goto('/admin/mcp-tokens');
  await expect(page.getByRole('heading', { name: 'MCP 토큰' })).toBeVisible();

  // 발급 사유만 채우고 user_id는 비운 채 발급.
  await page.getByTestId('admin-mcp-reason').fill('대리 발급 테스트');
  await page.getByRole('button', { name: '발급' }).click();

  const userError = page.locator('#admin-mcp-user-error');
  await expect(userError).toBeVisible();
  await expect(userError).toHaveText(/user_id/);
  await expect(page.getByTestId('admin-mcp-user')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByTestId('admin-mcp-user')).toBeFocused();
});
