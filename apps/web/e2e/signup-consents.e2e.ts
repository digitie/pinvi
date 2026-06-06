import { expect, test } from '@playwright/test';

test('회원가입 화면이 필수 약관 동의를 register payload에 포함한다', async ({ page }) => {
  let registerPayload: unknown = null;

  await page.route(/.*\/auth\/register$/, async (route) => {
    registerPayload = route.request().postDataJSON();
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          user: {
            user_id: '77777777-7777-4777-8777-777777777777',
            email: 'signup@example.com',
            status: 'pending_verification',
            email_verified_at: null,
          },
          verification_email_dispatched: true,
        },
      }),
    });
  });

  await page.goto('/signup');

  await page.getByTestId('signup-email').fill('signup@example.com');
  await page.getByTestId('signup-password').fill('secret-pw-12345');
  await page.getByTestId('signup-nickname').fill('약관사용자');

  await expect(page.getByTestId('signup-submit')).toBeDisabled();

  await page.getByTestId('signup-consent-required-all').check();
  await page.getByTestId('signup-consent-marketing').check();
  await expect(page.getByTestId('signup-submit')).toBeEnabled();
  await page.getByTestId('signup-submit').click();

  await expect(page).toHaveURL(/\/signup\/verify-pending\?/);
  expect(registerPayload).toMatchObject({
    email: 'signup@example.com',
    nickname: '약관사용자',
    consents: [
      { consent_type: 'tos', version: 'v1.0' },
      { consent_type: 'privacy', version: 'v1.0' },
      { consent_type: 'lbs_tos', version: 'v1.0' },
      { consent_type: 'location_collection', version: 'v1.0' },
      { consent_type: 'marketing', version: 'v1.0' },
    ],
  });
});
