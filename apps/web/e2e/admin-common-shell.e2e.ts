import { test, expect } from './fixtures';
import AxeBuilder from '@axe-core/playwright';
import { join } from 'node:path';

const user = {
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

test('공통 Admin 메뉴·PinVi 색상·접힘·반응형', async ({ page }) => {
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/auth/me',
    (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: user }) }),
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/trips',
    (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: { items: [], total: 0, page: 1, limit: 50 } }),
      }),
  );
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/admin/trips');
  const nav = page.getByRole('navigation', { name: '관리자 주요 메뉴' });
  await expect(nav.getByRole('link')).toHaveCount(30);
  await expect(nav.locator('[aria-current="page"]')).toHaveAttribute('href', '/admin/trips');
  await expect(page.getByTestId('admin-sidebar')).toHaveCSS('width', '256px');
  expect(
    await nav.evaluate((el) => {
      const style = getComputedStyle(el);
      return (
        style.getPropertyValue('--kt-brand-tint').trim() ===
        style.getPropertyValue('--color-admin-brand-tint').trim()
      );
    }),
  ).toBe(true);
  await nav.getByRole('link', { name: '사용자', exact: true }).focus();
  await expect(nav.getByRole('link', { name: '사용자', exact: true })).toBeFocused();
  const scan = await new AxeBuilder({ page })
    .include('[data-testid="admin-sidebar"]')
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(scan.violations).toEqual([]);
  const links = nav.getByRole('link');
  await links.nth(28).focus();
  await page.keyboard.press('Tab');
  await expect(links.last()).toBeFocused();
  await expect(links.last()).toBeInViewport();
  await page.getByRole('link', { name: '본문으로 건너뛰기' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('main')).toBeFocused();
  const output = process.env.PINVI_PLAYWRIGHT_RUNNER_OUTPUT_DIR;
  if (output)
    await page.screenshot({ path: join(output, 'pinvi-admin-desktop.png'), fullPage: true });
  await page.getByRole('button', { name: 'Admin 메뉴 접기' }).click();
  await expect(page.getByTestId('admin-sidebar')).toHaveCSS('width', '64px');
  await page.reload();
  await expect(page.getByTestId('admin-sidebar')).toHaveAttribute('data-collapsed', 'true');
  if (output)
    await page.screenshot({ path: join(output, 'pinvi-admin-collapsed.png'), fullPage: true });
  for (const width of [320, 375, 414, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    if (width < 1024) {
      await expect(page.getByRole('button', { name: '로그아웃', exact: true })).toHaveCSS(
        'min-height',
        '44px',
      );
      await expect(
        nav.getByRole('link', { name: '여행', exact: true }).locator('span').last(),
      ).toHaveCSS('position', 'static');
      await expect(nav.getByRole('link', { name: '여행', exact: true })).toHaveCSS(
        'min-height',
        '44px',
      );
    }
    if (output && width === 375)
      await page.screenshot({ path: join(output, 'pinvi-admin-mobile.png'), fullPage: true });
  }
  let logoutAttempts = 0;
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/auth/logout',
    async (route) => {
      logoutAttempts += 1;
      await route.fulfill(
        logoutAttempts === 1
          ? {
              status: 500,
              contentType: 'application/json',
              body: JSON.stringify({
                error: { code: 'INTERNAL_ERROR', message: '검증용 내부 오류' },
              }),
            }
          : { status: 204 },
      );
    },
  );
  await page.getByRole('button', { name: '로그아웃', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('로그아웃하지 못했습니다.');
  await expect(page).toHaveURL(/\/admin\/trips/);
  await page.getByRole('button', { name: '로그아웃', exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/login/);
  await expect(page.getByTestId('admin-login-form')).toBeVisible();
  if (output)
    await page.screenshot({ path: join(output, 'pinvi-admin-login.png'), fullPage: true });
});
