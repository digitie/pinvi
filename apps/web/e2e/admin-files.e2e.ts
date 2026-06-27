import { expect, test } from '@playwright/test';
import type { AdminFileStorageSettings, AttachmentLibraryItem } from '@pinvi/schemas';

const adminUser = {
  user_id: '77777777-7777-4777-8777-777777777777',
  email: 'admin@example.com',
  nickname: '관리자',
  avatar_url: null,
  avatar_kind: 'default',
  avatar_content_type: null,
  avatar_byte_size: null,
  avatar_updated_at: null,
  has_avatar: false,
  status: 'active',
  roles: ['user', 'admin'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

const attachmentId = '33333333-3333-4333-8333-333333333333';
const tripId = '44444444-4444-4444-8444-444444444444';
const userId = '22222222-2222-4222-8222-222222222222';

const fileItem: AttachmentLibraryItem = {
  attachment_id: attachmentId,
  trip_id: tripId,
  trip_day_index: null,
  trip_poi_id: null,
  curated_plan_id: null,
  curated_poi_id: null,
  notice_plan_id: null,
  notice_poi_id: null,
  source_attachment_id: null,
  bucket: 'pinvi-media',
  storage_key: `user-uploads/trip_attachment/${userId}/2026/06/receipt.jpg`,
  original_filename: 'receipt.jpg',
  content_type: 'image/jpeg',
  byte_size: 8192,
  public_url: null,
  role: 'image',
  description: '영수증',
  sort_order: 0,
  created_at: '2026-06-01T09:00:00+09:00',
  updated_at: '2026-06-01T09:00:00+09:00',
  target_scope: 'trip',
  uploaded_by_user_id: userId,
  uploaded_by_email_masked: 'u***@example.com',
  trip_title: '부산 여행',
  poi_label: null,
};

test('Admin 파일 화면에서 정책 저장, 검색, 다운로드, 삭제를 수행한다', async ({ page }) => {
  let items = [fileItem];
  let settings: AdminFileStorageSettings = {
    attachment_max_upload_bytes: 10485760,
    trip_attachment_quota_bytes: 104857600,
    user_attachment_quota_bytes: 1073741824,
  };
  let settingsBody: Record<string, unknown> | null = null;
  let lastFilesUrl = '';
  let deleteBody: Record<string, unknown> | null = null;

  await page.addInitScript(() => {
    Object.defineProperty(window, 'open', {
      value: (url: string | URL | undefined) => {
        (window as Window & { __pinviOpenedUrl?: string }).__pinviOpenedUrl = String(url);
        return null;
      },
    });
  });

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/auth/me',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: adminUser }),
      });
    },
  );

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/settings/files',
    async (route) => {
      if (route.request().method() === 'PUT') {
        settingsBody = route.request().postDataJSON() as Record<string, unknown>;
        settings = {
          attachment_max_upload_bytes: Number(settingsBody.attachment_max_upload_bytes),
          trip_attachment_quota_bytes: Number(settingsBody.trip_attachment_quota_bytes),
          user_attachment_quota_bytes: Number(settingsBody.user_attachment_quota_bytes),
        };
      }
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: settings }),
      });
    },
  );

  await page.route(
    (url) => url.port === '12801' && url.pathname.startsWith('/admin/files'),
    async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.pathname === `/admin/files/${attachmentId}/download-url`) {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            data: {
              method: 'GET',
              bucket: fileItem.bucket,
              storage_key: fileItem.storage_key,
              download_url: 'http://127.0.0.1:9559/pinvi-media/receipt.jpg?X-Amz-Signature=get',
              expires_at: '2026-06-01T09:15:00+09:00',
              public_url: null,
            },
          }),
        });
        return;
      }
      if (url.pathname === `/admin/files/${attachmentId}` && request.method() === 'DELETE') {
        deleteBody = request.postDataJSON() as Record<string, unknown>;
        items = [];
        await route.fulfill({ status: 204, body: '' });
        return;
      }
      lastFilesUrl = request.url();
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items,
            total: items.length,
            page: 1,
            limit: 100,
          },
        }),
      });
    },
  );

  page.on('dialog', (dialog) => dialog.accept('운영 정리'));

  await page.goto('/admin/files');
  await expect(page.getByRole('heading', { name: '파일' })).toBeVisible();
  await expect(page.getByText('receipt.jpg')).toBeVisible();
  await expect(page.getByText('u***@example.com')).toBeVisible();

  await page.getByTestId('admin-file-setting-attachment_max_upload_bytes').fill('4096');
  await page.getByTestId('admin-file-setting-trip_attachment_quota_bytes').fill('8192');
  await page.getByTestId('admin-file-setting-user_attachment_quota_bytes').fill('16384');
  await page.getByLabel('사유').fill('전역 파일 정책 조정');
  await page.getByTestId('admin-file-settings-save').click();
  await expect.poll(() => settingsBody).toMatchObject({
    attachment_max_upload_bytes: 4096,
    trip_attachment_quota_bytes: 8192,
    user_attachment_quota_bytes: 16384,
    access_reason: '전역 파일 정책 조정',
  });

  await page.getByTestId('admin-files-search').fill('receipt');
  await page.getByTestId('admin-files-scope').selectOption('trip');
  await page.getByTestId('admin-files-search-submit').click();
  await expect
    .poll(() => lastFilesUrl)
    .toContain('q=receipt');
  expect(lastFilesUrl).toContain('scope=trip');

  await page.getByRole('button', { name: '다운로드' }).click();
  await expect
    .poll(() =>
      page.evaluate(() => (window as Window & { __pinviOpenedUrl?: string }).__pinviOpenedUrl),
    )
    .toContain('X-Amz-Signature=get');

  await page.getByRole('button', { name: '삭제' }).click();
  await expect.poll(() => deleteBody).toMatchObject({ access_reason: '운영 정리' });
  await expect(page.getByText('파일이 없습니다.')).toBeVisible();
});
