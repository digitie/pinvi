import { expect, test, type Page } from '@playwright/test';

const liveEnabled = process.env.PINVI_ADMIN_LIVE_E2E === '1';
const adminEmail = process.env.PINVI_ADMIN_LIVE_EMAIL;
const adminPassword = process.env.PINVI_ADMIN_LIVE_PASSWORD;
const adminStorageState = process.env.PINVI_ADMIN_LIVE_STORAGE_STATE;
const throttleMs = Number(process.env.PINVI_ADMIN_LIVE_THROTTLE_MS ?? '2100');

const secretPatterns = [
  /(?:api[_-]?key|secret|password|passwd|token)=((?!%2A%2A%2A|\*\*\*)[^&\s]{8,})/i,
  /AKIA[0-9A-Z]{16}/,
  /BEGIN [A-Z ]*PRIVATE KEY/,
];

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

function expectNoSecret(value: string) {
  for (const pattern of secretPatterns) {
    expect(value).not.toMatch(pattern);
  }
}

test.describe('admin grafana live e2e', () => {
  test.skip(!liveEnabled, 'PINVI_ADMIN_LIVE_E2E=1 일 때만 N150/live 대상에 실행합니다.');
  test.skip(
    !adminStorageState && (!adminEmail || !adminPassword),
    'PINVI_ADMIN_LIVE_EMAIL/PINVI_ADMIN_LIVE_PASSWORD 또는 PINVI_ADMIN_LIVE_STORAGE_STATE가 필요합니다.',
  );
  if (adminStorageState) {
    test.use({ storageState: adminStorageState });
  }

  test('/admin/grafana iframe과 ok/degraded health 상태를 검증한다', async ({ page }) => {
    await ensureAdminAuth(page);
    await throttle();
    await page.goto('/admin/grafana');

    await expect(page.getByRole('heading', { name: 'Grafana' })).toBeVisible();
    await expect(page.getByTestId('admin-grafana-frame')).toBeVisible();
    await expect(page.getByTestId('admin-grafana-dashboard-list')).toContainText('API');
    await expect(page.getByTestId('admin-grafana-health-status')).toHaveText(/정상|강등/, {
      timeout: 10_000,
    });

    const healthText = await page.getByTestId('admin-grafana-health-message').innerText();
    const originText = await page.getByTestId('admin-grafana-origin').innerText();
    expectNoSecret(healthText);
    expectNoSecret(originText);

    const dashboards = {
      api: '/d/pinvi-api-http',
      db: '/d/pinvi-db-pool',
      websocket: '/d/pinvi-websocket',
      'etl-backup': '/d/pinvi-etl-backup',
    };
    for (const [dashboard, expectedPath] of Object.entries(dashboards)) {
      await page.getByTestId(`admin-grafana-dashboard-${dashboard}`).click();
      await throttle();
      const frameSrc = await page.getByTestId('admin-grafana-frame').getAttribute('src');
      expect(frameSrc ?? '').toContain(expectedPath);
      expectNoSecret(frameSrc ?? '');
    }
  });
});
