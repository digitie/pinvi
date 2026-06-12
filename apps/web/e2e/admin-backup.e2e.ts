import { expect, test } from '@playwright/test';

const adminUserId = '55555555-5555-4555-8555-555555555555';

test('Admin backup page가 snapshot 목록과 수동 trigger를 렌더링한다', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', (request) => requests.push(request.url()));

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

  await page.route(/.*\/admin\/backup\/snapshots(\?.*)?$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: [
          {
            snapshot_id: 'tripmate-app-20260606-001500',
            filename: 'tripmate-app-20260606-001500.dump',
            path: '/var/lib/tripmate/backups/tripmate-app-20260606-001500.dump',
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
          snapshot_id: 'tripmate-app-20260606-003000',
          filename: 'tripmate-app-20260606-003000.dump',
          path: '/var/lib/tripmate/backups/tripmate-app-20260606-003000.dump',
          size_bytes: 2097152,
          checksum_sha256: 'b'.repeat(64),
          status: 'verified',
          created_at: '2026-06-06T00:30:00+09:00',
        },
      }),
    });
  });

  await page.route(/.*\/admin\/backup\/restore-hotswap$/, async (route) => {
    const body = route.request().postDataJSON();
    expect(body.snapshot_id).toBe('tripmate-app-20260606-001500');
    expect(body.confirm_schema_swap).toBe(true);
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          restore_id: '20260608093000',
          snapshot_id: 'tripmate-app-20260606-001500',
          snapshot_path: '/var/lib/tripmate/backups/tripmate-app-20260606-001500.dump',
          restore_schema: 'app_restore_20260608093000',
          previous_schema: 'app_previous_20260608093000',
          status: 'succeeded',
          phases: [
            { name: 'preparing', status: 'success', message: 'checked' },
            { name: 'restoring', status: 'success', message: 'restored' },
            { name: 'validating', status: 'success', message: 'validated' },
            { name: 'draining', status: 'success', message: 'drained' },
            { name: 'switching', status: 'success', message: 'switched' },
          ],
          started_at: '2026-06-08T09:30:00+09:00',
          completed_at: '2026-06-08T09:31:00+09:00',
        },
      }),
    });
  });

  await page.goto('/admin/backup');

  await expect(page.getByRole('heading', { name: 'Backup' })).toBeVisible();
  await expect(page.getByTestId('admin-backup-filename')).toContainText(
    'tripmate-app-20260606-001500.dump',
  );

  await page.getByTestId('admin-backup-create').click();
  await expect(page.getByText('수동 백업 snapshot을 생성했습니다.')).toBeVisible();
  await expect(page.getByTestId('admin-backup-filename').first()).toContainText(
    'tripmate-app-20260606-003000.dump',
  );

  await page.getByTestId('admin-backup-restore').last().click();
  await expect(page.getByTestId('restore-snapshot-name')).toContainText(
    'tripmate-app-20260606-001500.dump',
  );
  await page.getByTestId('restore-reason').fill('복구 훈련');
  await page.getByTestId('restore-confirm').check();
  await page.getByTestId('restore-submit').click();
  await expect(page.getByTestId('restore-run-id')).toContainText('20260608093000');
  await expect(page.getByTestId('restore-phase-switching')).toContainText('success');
  await expect(page.getByText(/핫스왑 restore 요청이 완료됐습니다/)).toBeVisible();

  expect(requests.some((url) => url.includes('/features/'))).toBe(false);
  expect(requests.some((url) => url.includes('12301'))).toBe(false);
});
