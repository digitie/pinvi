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

  expect(requests.some((url) => url.includes('/features/'))).toBe(false);
  expect(requests.some((url) => url.includes('9011'))).toBe(false);
});
