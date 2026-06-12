import { expect, test } from '@playwright/test';

test('Admin Grafana embed shell이 admin guard 뒤에서 iframe을 렌더링한다', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', (request) => requests.push(request.url()));

  await page.route(/.*\/auth\/me$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          user_id: '44444444-4444-4444-8444-444444444444',
          email: 'admin@example.com',
          nickname: '관리자',
          avatar_url: null,
          status: 'active',
          roles: ['user', 'admin'],
          email_verified_at: '2026-06-01T09:00:00+09:00',
          has_password: true,
          oauth_identities: [],
        },
      }),
    });
  });

  await page.goto('/admin/grafana');

  await expect(page.getByRole('heading', { name: 'Grafana' })).toBeVisible();
  await expect(page.getByTestId('admin-grafana-frame')).toBeVisible();
  await expect(page.getByTestId('admin-grafana-origin')).toContainText('http://localhost:3002');
  await expect(page.getByTestId('admin-nav--admin-grafana')).toBeVisible();

  const frameSrc = await page.getByTestId('admin-grafana-frame').getAttribute('src');
  expect(frameSrc).toContain('/d/tripmate/overview');
  expect(requests.some((url) => url.includes('/features/'))).toBe(false);
  expect(requests.some((url) => url.includes('12301'))).toBe(false);
});
