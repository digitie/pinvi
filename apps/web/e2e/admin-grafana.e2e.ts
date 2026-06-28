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
  await page.route(/.*\/admin\/grafana\/health$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        origin: 'http://localhost:12205',
        status_code: 200,
        message: 'Grafana health 확인',
      }),
    });
  });
  await page.route('http://localhost:12205/**', async (route) => {
    await route.fulfill({
      contentType: 'text/html',
      body: '<!doctype html><title>Grafana</title>',
    });
  });

  await page.goto('/admin/grafana');

  await expect(page.getByRole('heading', { name: 'Grafana' })).toBeVisible();
  await expect(page.getByTestId('admin-grafana-health-status')).toContainText('정상');
  await expect(page.getByTestId('admin-grafana-frame')).toBeVisible();
  await expect(page.getByTestId('admin-grafana-origin')).toContainText('http://localhost:12205');
  await expect(page.getByTestId('admin-grafana-dashboard-list')).toContainText('DB pool');
  await expect(page.getByTestId('admin-nav--admin-grafana')).toBeVisible();

  const frameSrc = await page.getByTestId('admin-grafana-frame').getAttribute('src');
  expect(frameSrc).toContain('/d/pinvi/overview');
  expect(frameSrc).not.toMatch(/secret|token|password|api[_-]?key/i);

  await page.getByTestId('admin-grafana-dashboard-websocket').click();
  await expect(page.getByTestId('admin-grafana-dashboard-path')).toContainText(
    '/d/pinvi-websocket/websocket',
  );
  expect(requests.some((url) => url.includes('/features/'))).toBe(false);
  expect(requests.some((url) => url.includes('12701'))).toBe(false);
});

test('Admin Grafana embed health가 실패하면 degraded 상태를 표시한다', async ({ page }) => {
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
  await page.route(/.*\/admin\/grafana\/health$/, async (route) => {
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'degraded',
        origin: 'http://localhost:12205',
        status_code: null,
        message: 'Grafana health 확인 필요',
      }),
    });
  });

  await page.goto('/admin/grafana');

  await expect(page.getByTestId('admin-grafana-frame')).toBeVisible();
  await expect(page.getByTestId('admin-grafana-health-status')).toContainText('강등');
  await expect(page.getByTestId('admin-grafana-health-message')).toContainText(
    'Grafana health 확인 필요',
  );
});
