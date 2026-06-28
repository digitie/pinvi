import { expect, test, type Page } from '@playwright/test';

interface BackupSnapshotResponse {
  data?: {
    snapshot_id: string;
    filename: string;
    path: string;
    size_bytes: number;
    checksum_sha256: string | null;
    status: 'available' | 'verified';
    created_at: string;
  };
}

const liveEnabled = process.env.PINVI_BACKUP_LIVE_MUTATING_E2E === '1';
const stagingEnabled = process.env.PINVI_BACKUP_LIVE_STAGING === '1';
const adminEmail = process.env.PINVI_BACKUP_LIVE_EMAIL ?? process.env.PINVI_ADMIN_LIVE_EMAIL;
const adminPassword =
  process.env.PINVI_BACKUP_LIVE_PASSWORD ?? process.env.PINVI_ADMIN_LIVE_PASSWORD;
const adminStorageState =
  process.env.PINVI_BACKUP_LIVE_STORAGE_STATE ?? process.env.PINVI_ADMIN_LIVE_STORAGE_STATE;
const throttleMs = Number(
  process.env.PINVI_BACKUP_LIVE_THROTTLE_MS ?? process.env.PINVI_ADMIN_LIVE_THROTTLE_MS ?? '2100',
);
const reasonPrefix = process.env.PINVI_BACKUP_LIVE_REASON_PREFIX ?? '[codex-backup-live]';

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
    throw new Error('PINVI_BACKUP_LIVE_EMAIL/PINVI_BACKUP_LIVE_PASSWORD가 필요합니다.');
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

function pathnameOf(value: string) {
  try {
    return new URL(value).pathname;
  } catch {
    return '';
  }
}

function expectNoRawBackupLeaksInText(text: string) {
  for (const pattern of rawBackupLeakPatterns) {
    expect(text).not.toMatch(pattern);
  }
}

async function expectNoRawBackupLeaks(page: Page) {
  expectNoRawBackupLeaksInText(await page.locator('main').innerText());
}

test.describe('admin backup staging live mutating e2e', () => {
  test.skip(
    !liveEnabled,
    'PINVI_BACKUP_LIVE_MUTATING_E2E=1 일 때만 backup live mutating e2e를 실행합니다.',
  );
  test.skip(
    !stagingEnabled,
    'PINVI_BACKUP_LIVE_STAGING=1 명시가 있어야 staging backup mutation을 실행합니다.',
  );
  test.skip(
    !adminStorageState && (!adminEmail || !adminPassword),
    'PINVI_BACKUP_LIVE_EMAIL/PINVI_BACKUP_LIVE_PASSWORD 또는 PINVI_BACKUP_LIVE_STORAGE_STATE가 필요합니다.',
  );
  if (adminStorageState) {
    test.use({ storageState: adminStorageState });
  }
  test.describe.configure({ mode: 'serial' });

  test('manual snapshot 생성, audit evidence, retention cap, masking을 staging에서 검증한다', async ({
    page,
  }) => {
    const forbiddenRestoreRequests: string[] = [];
    page.on('request', (request) => {
      if (
        request.method() !== 'GET' &&
        pathnameOf(request.url()) === '/admin/backup/restore-hotswap'
      ) {
        forbiddenRestoreRequests.push(request.url());
      }
    });

    await ensureAdminAuth(page);
    await throttle();
    await page.goto('/admin/backup');
    await expect(page.getByRole('heading', { name: 'Backup' })).toBeVisible();
    await expect(page.getByText('불러오는 중...')).toHaveCount(0, { timeout: 15_000 });
    await expect(page.getByTestId('admin-backup-error')).toHaveCount(0);

    const reason = `${reasonPrefix} ${new Date().toISOString()}`;
    await page.getByTestId('admin-backup-reason').fill(reason);
    await throttle();
    const createResponsePromise = page.waitForResponse(
      (response) =>
        pathnameOf(response.url()) === '/admin/backup/snapshot' &&
        response.request().method() === 'POST',
      { timeout: 120_000 },
    );
    await page.getByTestId('admin-backup-create').click();
    const createResponse = await createResponsePromise;
    expect(createResponse.status()).toBe(201);

    const payload = (await createResponse.json()) as BackupSnapshotResponse;
    const created = payload.data;
    expect(created).toBeTruthy();
    expect(created!.path).toMatch(/^backup:\/\/[^/]+\.dump$/);
    expectNoRawBackupLeaksInText(JSON.stringify(created));

    await expect(page.getByText('수동 백업 snapshot을 생성했습니다.')).toBeVisible();
    await expect(page.getByTestId('admin-backup-filename').first()).toContainText(
      created!.filename,
    );
    await expectNoRawBackupLeaks(page);

    const rows = page.locator('[data-testid^="admin-backup-row-"]');
    expect(await rows.count()).toBeLessThanOrEqual(50);

    await throttle();
    await page.goto('/admin/audit');
    await expect(page.getByRole('heading', { name: '감사 로그' })).toBeVisible();
    await expect(page.getByText('불러오는 중...')).toHaveCount(0, { timeout: 15_000 });
    await expect(page.getByText('backup.snapshot').first()).toBeVisible();
    await expect(page.getByText(reason).first()).toBeVisible();
    await expectNoRawBackupLeaks(page);
    expect(forbiddenRestoreRequests).toEqual([]);
  });
});
