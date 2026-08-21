import { expect, test, type Page } from '@playwright/test';

const enabled = process.env.PINVI_M04_LIVE_E2E === '1';
const adminEmail = process.env.PINVI_M04_LIVE_EMAIL;
const adminPassword = process.env.PINVI_M04_LIVE_PASSWORD;
const adminStorageState = process.env.PINVI_M04_LIVE_STORAGE_STATE;
const featureRequestId = process.env.PINVI_M04_LIVE_FEATURE_REQUEST_ID;
const reason = process.env.PINVI_M04_LIVE_REASON ?? '[tvn-m04 isolated live e2e] queue receipt';

async function ensureAdminAuth(page: Page) {
  if (adminStorageState) {
    await page.goto('/admin');
    await expect(page.getByTestId('admin-me')).toBeVisible();
    return;
  }
  if (!adminEmail || !adminPassword) {
    throw new Error('PINVI_M04_LIVE_EMAIL/PINVI_M04_LIVE_PASSWORD가 필요합니다.');
  }
  await page.goto('/admin/login');
  await page.getByTestId('admin-login-email').fill(adminEmail);
  await page.getByTestId('admin-login-password').fill(adminPassword);
  await page.getByTestId('admin-login-submit').click();
  await expect(page).toHaveURL(/\/admin(?:[?#].*)?$/);
}

test.describe('M04 isolated Map feature-request queue live e2e', () => {
  test.skip(!enabled, 'PINVI_M04_LIVE_E2E=1인 격리 paired stack에서만 실행합니다.');
  test.skip(!featureRequestId, 'PINVI_M04_LIVE_FEATURE_REQUEST_ID가 필요합니다.');
  test.skip(
    !adminStorageState && (!adminEmail || !adminPassword),
    'PINVI_M04_LIVE_EMAIL/PINVI_M04_LIVE_PASSWORD 또는 storage state가 필요합니다.',
  );
  if (adminStorageState) test.use({ storageState: adminStorageState });
  test.describe.configure({ mode: 'serial' });

  test('관리자 UI 승인 후 Map pending receipt를 PinVi approved 상태로 보존한다', async ({ page }) => {
    await ensureAdminAuth(page);
    await page.goto('/admin/feature-requests');
    await page.getByTestId(`admin-fr-review-${featureRequestId}`).click();
    await expect(page.getByTestId('admin-fr-queue-payload-notice')).toBeVisible();
    await page.getByTestId('admin-fr-reason').fill(reason);

    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        response.url().includes(`/admin/feature-requests/${featureRequestId}/approve`),
    );
    await page.getByTestId('admin-fr-approve').click();
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    const payload = (await response.json()) as {
      data?: { status?: string; kor_travel_map_ref?: Record<string, unknown> };
    };
    expect(payload.data?.status).toBe('approved');
    expect(payload.data?.kor_travel_map_ref).toMatchObject({
      request_id: featureRequestId,
      state: 'pending',
      review_mode: 'feature_request_queue',
      action: 'submit',
    });
    await expect(page.getByTestId('admin-fr-notice')).toContainText('Map Feature 요청 큐');
  });
});
