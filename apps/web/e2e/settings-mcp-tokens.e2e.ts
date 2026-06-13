import { expect, test } from '@playwright/test';

test('사용자 MCP 토큰 발급 폼이 시각적 라벨을 갖는다(label↔input 연결)', async ({ page }) => {
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/users/me/mcp-tokens',
    async (route, request) => {
      if (request.method() !== 'GET') return route.continue();
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
    },
  );

  await page.goto('/settings/mcp-tokens');
  await expect(page.getByRole('heading', { name: 'MCP 토큰' })).toBeVisible();

  // FormField/FormSelect가 시각적 라벨을 노출.
  await expect(page.getByLabel('토큰 이름')).toBeVisible();
  await expect(page.getByLabel('만료')).toBeVisible();
});
