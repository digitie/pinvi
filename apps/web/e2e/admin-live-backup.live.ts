import { expect, test, type Page } from '@playwright/test';

const liveEnabled = process.env.PINVI_ADMIN_LIVE_E2E === '1';
const adminEmail = process.env.PINVI_ADMIN_LIVE_EMAIL;
const adminPassword = process.env.PINVI_ADMIN_LIVE_PASSWORD;
const adminStorageState = process.env.PINVI_ADMIN_LIVE_STORAGE_STATE;
const throttleMs = Number(process.env.PINVI_ADMIN_LIVE_THROTTLE_MS ?? '2100');

const rawBackupLeakPatterns = [
  /\/(?:var|opt|srv|mnt|home|tmp|repo|app|data)[^\s]*\.dump/i,
  /[A-Za-z]:\\[^\s]+\.dump/i,
  /postgresql(?:\+asyncpg)?:\/\/\S+/i,
  /(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*(?!\[masked\]|%5Bmasked%5D|redacted|<redacted>|\*\*\*)[A-Za-z0-9_./+=-]{8,}/i,
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

function backupMutationPath(value: string, method: string) {
  if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') return null;
  try {
    const url = new URL(value);
    return url.pathname.startsWith('/admin/backup') ? url.pathname : null;
  } catch {
    return null;
  }
}

async function expectNoRawBackupLeaks(page: Page) {
  const bodyText = await page.locator('main').innerText();
  for (const pattern of rawBackupLeakPatterns) {
    expect(bodyText).not.toMatch(pattern);
  }
}

test.describe('admin backup live read-only e2e', () => {
  test.skip(!liveEnabled, 'PINVI_ADMIN_LIVE_E2E=1 일 때만 N150/live 대상에 실행합니다.');
  test.skip(
    !adminStorageState && (!adminEmail || !adminPassword),
    'PINVI_ADMIN_LIVE_EMAIL/PINVI_ADMIN_LIVE_PASSWORD 또는 PINVI_ADMIN_LIVE_STORAGE_STATE가 필요합니다.',
  );
  if (adminStorageState) {
    test.use({ storageState: adminStorageState });
  }
  test.describe.configure({ mode: 'serial' });

  test('/admin/backup 목록, 정렬, 필터, empty, masking을 live read-only로 검증한다', async ({
    page,
  }) => {
    const backupMutations: string[] = [];
    page.on('request', (request) => {
      const path = backupMutationPath(request.url(), request.method());
      if (path) backupMutations.push(path);
    });

    await ensureAdminAuth(page);
    await throttle();
    await page.goto('/admin/backup');
    await expect(page.getByRole('heading', { name: 'Backup' })).toBeVisible();
    await expect(page.getByTestId('admin-table-scroll')).toBeVisible();
    await expect(page.getByText('불러오는 중...')).toHaveCount(0, { timeout: 15_000 });
    await expect(page.getByTestId('admin-backup-error')).toHaveCount(0);

    await page.getByTestId('admin-table-sort-filename').click();
    await throttle();
    await page.getByTestId('admin-table-sort-status').click();
    await expect(page.getByTestId('admin-backup-status-filter')).toHaveValue('all');

    await page.getByTestId('admin-backup-status-filter').selectOption('verified');
    await expect(page.getByTestId('admin-backup-status-filter')).toHaveValue('verified');
    await throttle();
    await page.getByTestId('admin-backup-status-filter').selectOption('all');

    await page.getByTestId('admin-backup-search').fill(`pinvi-live-no-match-${Date.now()}`);
    await expect(page.getByTestId('admin-backup-visible-count')).toContainText('0 /');
    await expect(
      page.getByText(/조건에 맞는 snapshot이 없습니다|생성된 snapshot이 없습니다/),
    ).toBeVisible();
    await page.getByTestId('admin-backup-search').fill('');

    const restoreButtons = page.getByTestId('admin-backup-restore');
    const restoreCount = await restoreButtons.count();
    for (let index = 0; index < restoreCount; index += 1) {
      await expect(restoreButtons.nth(index)).toBeDisabled();
    }

    await expectNoRawBackupLeaks(page);
    expect(backupMutations).toEqual([]);
  });
});
