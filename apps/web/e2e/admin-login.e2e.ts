import { expect, test } from '@playwright/test';

test('admin 로그인: 잘못된 이메일 제출 시 필드 오류 + aria-invalid + 포커스', async ({ page }) => {
  await page.goto('/admin/login');
  await expect(page.getByRole('heading', { name: 'TripMate Admin' })).toBeVisible();

  await page.getByTestId('admin-login-email').fill('not-an-email');
  await page.getByTestId('admin-login-password').fill('whatever');
  await page.getByTestId('admin-login-submit').click();

  const emailError = page.locator('#admin-login-email-error');
  await expect(emailError).toBeVisible();
  await expect(emailError).toHaveText(/이메일/);
  await expect(page.getByTestId('admin-login-email')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByTestId('admin-login-email')).toBeFocused();
});

test('admin 로그인: 권한 안내 reason은 role=alert로 노출된다', async ({ page }) => {
  await page.goto('/admin/login?reason=forbidden');
  const err = page.getByTestId('admin-login-error');
  await expect(err).toBeVisible();
  await expect(err).toHaveAttribute('role', 'alert');
  await expect(err).toHaveText(/관리자 권한/);
});
