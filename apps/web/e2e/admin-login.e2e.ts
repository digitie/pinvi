import { expect, test } from '@playwright/test';

test('admin 로그인: 잘못된 이메일 제출 시 필드 오류 + aria-invalid + 포커스', async ({ page }) => {
  await page.goto('/admin/login');
  await expect(page.getByText('Pinvi Admin', { exact: true })).toBeVisible();

  await page.locator('[data-slot=login-username]').fill('not-an-email');
  await page.locator('[data-slot=login-password]').fill('whatever');
  await page.locator('[data-slot=login-submit]').click();

  const emailError = page.locator('[data-slot=login-error]');
  await expect(emailError).toBeVisible();
  await expect(emailError).toHaveText(/이메일/);
  await expect(page.locator('[data-slot=login-username]')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.locator('[data-slot=login-username]')).toBeFocused();
});

test('admin 로그인: 권한 안내 reason은 role=alert로 노출된다', async ({ page }) => {
  await page.goto('/admin/login?reason=forbidden');
  const err = page.locator('[data-slot=login-error]');
  await expect(err).toBeVisible();
  await expect(err).toHaveAttribute('role', 'alert');
  await expect(err).toHaveText(/관리자 권한/);
});
