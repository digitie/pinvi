import { expect, test } from '@playwright/test';

const authUser = {
  user_id: '88888888-8888-4888-8888-888888888888',
  email: 'owner@example.com',
  nickname: '사용자',
  avatar_url: null,
  status: 'active',
  roles: ['user'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

test('로그인 화면이 Google 계정 매칭 필요 redirect를 안내한다', async ({ page }) => {
  await page.route(/.*\/auth\/oauth\/providers$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          providers: [{ provider: 'google', enabled: true }],
        },
      }),
    });
  });

  await page.goto('/login?error=OAUTH_ACCOUNT_LINK_REQUIRED');

  await expect(page.getByTestId('oauth-error')).toContainText(
    '이메일로 로그인한 뒤 프로필에서 Google을 연결',
  );
  await expect(page.getByTestId('google-oauth-start')).toBeEnabled();
  await expect(page.getByText('Naver')).toHaveCount(0);
  await expect(page.getByText('Kakao')).toHaveCount(0);
});

test('프로필 화면이 Google 연결 충돌 redirect를 안내한다', async ({ page }) => {
  await page.route(/.*\/auth\/me$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: authUser }),
    });
  });
  await page.route(/.*\/auth\/oauth\/providers$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          providers: [{ provider: 'google', enabled: true }],
        },
      }),
    });
  });

  await page.goto('/profile?error=OAUTH_ACCOUNT_LINK_REQUIRED');

  await expect(page.getByTestId('profile-error')).toContainText(
    'Google 계정은 다른 Pinvi 계정과 충돌',
  );
  await expect(page).toHaveURL(/\/profile$/);
});
