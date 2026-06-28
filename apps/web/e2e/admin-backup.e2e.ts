import { expect, test, type Page } from '@playwright/test';

const adminUserId = '55555555-5555-4555-8555-555555555555';

async function mockAdminAuth(page: Page) {
  await page.route(/.*\/auth\/me$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          user_id: adminUserId,
          email: 'admin@example.com',
          nickname: '관리자',
          avatar_url: null,
          status: 'active',
          roles: ['user', 'admin'],
          email_verified_at: '2026-06-01T09:00:00+09:00',
          has_password: true,
          oauth_identities: [],
        },
      }),
    });
  });
}

test('Admin backup page가 snapshot 목록, 필터, 수동 trigger, restore 잠금을 렌더링한다', async ({
  page,
}) => {
  const requests: string[] = [];
  page.on('request', (request) => requests.push(request.url()));

  await mockAdminAuth(page);

  await page.route(/.*\/admin\/backup\/snapshots(\?.*)?$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: [
          {
            snapshot_id: 'pinvi-app-20260606-003000',
            filename: 'pinvi-app-20260606-003000.dump',
            path: 'backup://pinvi-app-20260606-003000.dump',
            size_bytes: 2097152,
            checksum_sha256: 'b'.repeat(64),
            status: 'available',
            created_at: '2026-06-06T00:30:00+09:00',
          },
          {
            snapshot_id: 'pinvi-app-20260606-001500',
            filename: 'pinvi-app-20260606-001500.dump',
            path: 'backup://pinvi-app-20260606-001500.dump',
            size_bytes: 1048576,
            checksum_sha256: 'a'.repeat(64),
            status: 'verified',
            created_at: '2026-06-06T00:15:00+09:00',
          },
        ],
      }),
    });
  });

  await page.route(/.*\/admin\/backup\/snapshot$/, async (route) => {
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          snapshot_id: 'pinvi-app-20260606-004500',
          filename: 'pinvi-app-20260606-004500.dump',
          path: 'backup://pinvi-app-20260606-004500.dump',
          size_bytes: 3145728,
          checksum_sha256: 'c'.repeat(64),
          status: 'verified',
          created_at: '2026-06-06T00:45:00+09:00',
        },
      }),
    });
  });

  await page.goto('/admin/backup');

  await expect(page.getByRole('heading', { name: 'Backup' })).toBeVisible();
  await expect(page.getByTestId('admin-backup-filename')).toHaveCount(2);
  await expect(page.getByTestId('admin-backup-visible-count')).toContainText('2 / 2');

  await page.getByTestId('admin-backup-search').fill('001500');
  await expect(page.getByTestId('admin-backup-filename')).toHaveCount(1);
  await expect(page.getByTestId('admin-backup-visible-count')).toContainText('1 / 2');
  await expect(page.getByTestId('admin-backup-filename')).toContainText(
    'pinvi-app-20260606-001500.dump',
  );

  await page.getByTestId('admin-backup-search').fill('');
  await page.getByTestId('admin-backup-status-filter').selectOption('available');
  await expect(page.getByTestId('admin-backup-filename')).toContainText(
    'pinvi-app-20260606-003000.dump',
  );
  await expect(page.getByTestId('admin-backup-visible-count')).toContainText('1 / 2');

  await page.getByTestId('admin-backup-status-filter').selectOption('all');
  await page.getByTestId('admin-table-sort-filename').click();
  await expect(page.getByTestId('admin-backup-filename').first()).toContainText(
    'pinvi-app-20260606-001500.dump',
  );
  await page.getByTestId('admin-table-sort-filename').click();
  await expect(page.getByTestId('admin-backup-filename').first()).toContainText(
    'pinvi-app-20260606-003000.dump',
  );

  await page.getByTestId('admin-backup-create').click();
  await expect(page.getByText('수동 백업 snapshot을 생성했습니다.')).toBeVisible();
  await expect(page.getByTestId('admin-backup-filename').first()).toContainText(
    'pinvi-app-20260606-004500.dump',
  );

  await expect(page.getByTestId('admin-backup-restore').first()).toBeDisabled();
  expect(requests.some((url) => url.includes('/admin/backup/restore-hotswap'))).toBe(false);
  expect(requests.some((url) => url.includes('/features/'))).toBe(false);
  expect(requests.some((url) => url.includes('12701'))).toBe(false);
});

test('Admin backup page가 empty와 error 상태를 렌더링한다', async ({ page }) => {
  await mockAdminAuth(page);
  let shouldError = false;
  await page.route(/.*\/admin\/backup\/snapshots(\?.*)?$/, async (route) => {
    if (shouldError) {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: { code: 'BACKUP_FAILED', message: 'backup://snapshot unavailable' },
        }),
      });
      return;
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: [] }),
    });
  });

  await page.goto('/admin/backup');
  await expect(page.getByText('생성된 snapshot이 없습니다.')).toBeVisible();

  shouldError = true;
  await page.reload();
  await expect(page.getByTestId('admin-backup-error')).toContainText('HTTP 503');
});
