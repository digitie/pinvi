import { expect, test } from '@playwright/test';

// 로그인 페이지는 마운트 시 oauth providers를 조회하므로 mock해 둔다.
async function mockProviders(page: import('@playwright/test').Page) {
  await page.route(/.*\/auth\/oauth\/providers$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: { providers: [{ provider: 'google', enabled: true }] } }),
    });
  });
}

test('잘못된 이메일 제출 시 필드별 오류 + aria-invalid가 표시된다', async ({ page }) => {
  await mockProviders(page);
  await page.goto('/login');

  await page.getByTestId('login-email').fill('not-an-email');
  await page.getByTestId('login-password').fill('whatever');
  await page.getByTestId('login-submit').click();

  // 필드 오류 메시지(role=alert)가 이메일 입력에 연결되어 보인다.
  const emailError = page.locator('#login-email-error');
  await expect(emailError).toBeVisible();
  await expect(emailError).toHaveText(/이메일/);

  // aria-invalid + aria-describedby 연결 확인.
  const emailInput = page.getByTestId('login-email');
  await expect(emailInput).toHaveAttribute('aria-invalid', 'true');
  await expect(emailInput).toHaveAttribute('aria-describedby', /login-email-error/);
});

test('label 클릭으로 입력에 포커스가 간다(label↔input 연결)', async ({ page }) => {
  await mockProviders(page);
  await page.goto('/login');

  await page.getByText('이메일', { exact: true }).click();
  await expect(page.getByTestId('login-email')).toBeFocused();
});

test('비밀번호 8자 미만 회원가입은 비밀번호 오류를 알린다', async ({ page }) => {
  await page.goto('/signup');

  await page.getByTestId('signup-email').fill('user@example.com');
  await page.getByTestId('signup-password').fill('short');
  await page.getByTestId('signup-nickname').fill('테스터');
  // 필수 약관 전체 동의 후 제출 → 비밀번호 길이 검증으로 막힌다.
  await page.getByTestId('signup-consent-required-all').check();
  await page.getByTestId('signup-submit').click();

  const pwError = page.locator('#signup-password-error');
  await expect(pwError).toBeVisible();
  await expect(pwError).toHaveText(/8자/);
  await expect(page.getByTestId('signup-password')).toHaveAttribute('aria-invalid', 'true');
});
