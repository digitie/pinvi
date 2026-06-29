import { expect, test, type Page } from '@playwright/test';

const adminUserId = '55555555-5555-4555-8555-555555555555';
const restoreUiEnabled = process.env.NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED === '1';

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

test('Admin backup page가 snapshot 목록, 필터, 수동 trigger, restore 상태를 렌더링한다', async ({
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

  if (restoreUiEnabled) {
    await expect(page.getByTestId('admin-backup-restore').first()).toBeEnabled();
  } else {
    await expect(page.getByTestId('admin-backup-restore').first()).toBeDisabled();
  }
  expect(requests.some((url) => url.includes('/admin/backup/restore-hotswap'))).toBe(false);
  expect(requests.some((url) => url.includes('/features/'))).toBe(false);
  expect(requests.some((url) => url.includes('12701'))).toBe(false);
});

test('Admin backup restore dialog가 확인 문구, focus, 단계 표시, POST body를 검증한다', async ({
  page,
}) => {
  test.skip(
    !restoreUiEnabled,
    'NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=1 빌드에서만 restore dialog를 검증합니다.',
  );

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
            status: 'verified',
            created_at: '2026-06-06T00:30:00+09:00',
          },
        ],
      }),
    });
  });

  let restoreBody: Record<string, unknown> | null = null;
  await page.route(/.*\/admin\/backup\/restore-hotswap$/, async (route) => {
    restoreBody = route.request().postDataJSON() as Record<string, unknown>;
    await new Promise((resolve) => setTimeout(resolve, 500));
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          restore_id: 'restore-20260606-003000',
          snapshot_id: 'pinvi-app-20260606-003000',
          snapshot_path: 'backup://pinvi-app-20260606-003000.dump',
          restore_schema: 'app_restore_20260606003000',
          previous_schema: 'app_previous_20260606003000',
          status: 'succeeded',
          phases: [
            { name: 'preparing', status: 'success', message: 'snapshot verified' },
            { name: 'restoring', status: 'success', message: 'restored' },
            { name: 'validating', status: 'success', message: 'validated' },
            { name: 'draining', status: 'success', message: 'drained' },
            { name: 'switching', status: 'success', message: 'schema-swap completed' },
          ],
          started_at: '2026-06-06T00:31:00+09:00',
          completed_at: '2026-06-06T00:32:00+09:00',
        },
      }),
    });
  });

  await page.goto('/admin/backup');
  await expect(page.getByRole('heading', { name: 'Backup' })).toBeVisible();
  await page.getByTestId('admin-backup-restore').first().click();

  await expect(page.getByTestId('restore-hotswap-dialog')).toBeVisible();
  await expect(page.getByTestId('restore-snapshot-name')).toContainText(
    'pinvi-app-20260606-003000.dump',
  );
  await expect(page.getByTestId('restore-reason')).toBeFocused();
  await expect(page.getByTestId('restore-submit')).toBeDisabled();

  await page.keyboard.press('Shift+Tab');
  await expect(page.getByTestId('restore-close')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('restore-hotswap-dialog')).toHaveCount(0);

  await page.getByTestId('admin-backup-restore').first().click();
  await expect(page.getByTestId('restore-hotswap-dialog')).toBeVisible();
  await page.getByTestId('restore-hotswap-overlay').click({ position: { x: 2, y: 2 } });
  await expect(page.getByTestId('restore-hotswap-dialog')).toHaveCount(0);

  await page.getByTestId('admin-backup-restore').first().click();
  await page.getByTestId('restore-reason').fill('스테이징 schema-swap 훈련');
  await page.getByTestId('restore-confirm').check();
  await page.getByTestId('restore-confirmation').fill('wrong-snapshot.dump');
  await expect(page.getByTestId('restore-confirmation')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByTestId('restore-submit')).toBeDisabled();

  await page.getByTestId('restore-confirmation').fill('pinvi-app-20260606-003000.dump');
  await expect(page.getByTestId('restore-submit')).toBeEnabled();
  const restoreResponse = page.waitForResponse(
    (response) =>
      response.url().includes('/admin/backup/restore-hotswap') &&
      response.request().method() === 'POST',
  );
  await page.getByTestId('restore-submit').click();
  await expect(page.getByTestId('restore-progress')).toBeVisible();
  await expect(page.getByTestId('restore-phase-preparing')).toContainText('running');
  await expect(page.getByTestId('restore-close')).toBeDisabled();

  expect((await restoreResponse).status()).toBe(200);
  await expect(page.getByTestId('restore-run-id')).toContainText('restore-20260606-003000');
  await expect(page.getByTestId('restore-phase-switching')).toContainText('schema-swap');
  await expect(page.getByTestId('restore-phase-switching')).toContainText('success');
  await expect(
    page.getByText('핫스왑 restore 요청이 완료됐습니다. restore id: restore-20260606-003000'),
  ).toBeVisible();
  expect(restoreBody).toEqual({
    snapshot_id: 'pinvi-app-20260606-003000',
    access_reason: '스테이징 schema-swap 훈련',
    confirm_schema_swap: true,
  });
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
