import { expect, test, type Page } from '@playwright/test';

const liveEnabled = process.env.PINVI_ADMIN_LIVE_E2E === '1';
const adminEmail = process.env.PINVI_ADMIN_LIVE_EMAIL;
const adminPassword = process.env.PINVI_ADMIN_LIVE_PASSWORD;
const adminStorageState = process.env.PINVI_ADMIN_LIVE_STORAGE_STATE;
const throttleMs = Number(process.env.PINVI_ADMIN_LIVE_THROTTLE_MS ?? '2100');

let lastActionAt = 0;

async function throttle() {
  if (!Number.isFinite(throttleMs) || throttleMs <= 0) return;
  const elapsed = Date.now() - lastActionAt;
  if (elapsed < throttleMs) {
    await new Promise((resolve) => setTimeout(resolve, throttleMs - elapsed));
  }
  lastActionAt = Date.now();
}

async function loginViaUi(page: Page) {
  if (!adminEmail || !adminPassword) {
    throw new Error('PINVI_ADMIN_LIVE_EMAIL/PINVI_ADMIN_LIVE_PASSWORD가 필요합니다.');
  }
  await page.goto('/admin/login');
  await page.getByTestId('admin-login-email').fill(adminEmail);
  await page.getByTestId('admin-login-password').fill(adminPassword);
  await throttle();
  await page.getByTestId('admin-login-submit').click();
  await expect(page).toHaveURL(/\/admin(?:[?#].*)?$/);
  await expect(page.getByTestId('admin-me')).toBeVisible();
}

async function ensureAdminAuth(page: Page) {
  if (!adminStorageState) {
    await loginViaUi(page);
    return;
  }
  await page.goto('/admin');
  await expect(page.getByTestId('admin-me')).toBeVisible();
}

test.describe('map marker parity live e2e', () => {
  test.skip(!liveEnabled, 'PINVI_ADMIN_LIVE_E2E=1 일 때만 N150/live 대상에 실행합니다.');
  test.skip(
    !adminStorageState && (!adminEmail || !adminPassword),
    'PINVI_ADMIN_LIVE_EMAIL/PINVI_ADMIN_LIVE_PASSWORD 또는 PINVI_ADMIN_LIVE_STORAGE_STATE가 필요합니다.',
  );
  if (adminStorageState) {
    test.use({ storageState: adminStorageState });
  }

  test('/map marker style metadata를 live read-only로 검증한다', async ({ page }) => {
    await ensureAdminAuth(page);
    await throttle();
    await page.goto('/map');

    await expect(page.getByRole('heading', { name: '탐색 지도' })).toBeVisible();
    await expect(page.getByTestId('feature-map')).toBeVisible();
    await expect(page.getByTestId('feature-map-status')).toBeVisible();

    const markers = page.getByTestId('feature-map-marker-style');
    const count = await markers.count();
    if (count === 0) {
      await expect(page.getByTestId('feature-map-marker-legend')).toBeAttached();
      return;
    }

    const first = markers.first();
    await expect(first).toHaveAttribute(
      'data-marker-source',
      /^(upstream|category|kind|fallback|cluster)$/,
    );
    await expect(first).toHaveAttribute('data-marker-icon', /.+/);
    await expect(first).toHaveAttribute('data-marker-hex', /^(#[0-9A-Fa-f]{6}|#[0-9A-Fa-f]{3})$/);

    const cluster = page
      .locator('[data-testid="feature-map-marker-style"][data-marker-source="cluster"]')
      .first();
    if ((await cluster.count()) > 0) {
      await expect(cluster).toHaveAttribute('data-marker-color', 'cluster');
      await expect(cluster).toHaveAttribute('data-marker-count', /[1-9][0-9]*/);
    }
  });
});
