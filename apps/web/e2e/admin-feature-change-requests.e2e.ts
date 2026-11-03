import { test, expect } from '@playwright/test';

test('퇴역한 변경 요청 화면은 사용자 제안 큐로 이동한다', async ({ page }) => {
  const obsolete: string[] = [];
  await page.route('**/admin/features/change-requests**', async (route) => {
    if (route.request().resourceType() === 'fetch') {
      obsolete.push(route.request().url());
      await route.abort();
    } else await route.continue();
  });
  await page.route('**/auth/me', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          user_id: '00000000-0000-4000-8000-000000000001',
          email: 'admin@example.com',
          display_name: '관리자',
          roles: ['admin'],
          status: 'active',
        },
      }),
    }),
  );
  await page.route('**/admin/feature-requests**', (route) =>
    route.request().resourceType() === 'fetch'
      ? route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: { items: [], total: 0, page: 1, limit: 50 } }),
        })
      : route.continue(),
  );
  await page.goto('/admin/features/change-requests');
  await expect(page).toHaveURL(/\/admin\/feature-requests$/);
  await expect(
    page.getByRole('heading', { name: 'Feature 제안 검토', exact: false }),
  ).toBeVisible();
  expect(obsolete).toEqual([]);
});
