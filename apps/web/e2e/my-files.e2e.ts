import { expect, test } from '@playwright/test';
import type { AttachmentLibraryItem } from '@pinvi/schemas';

const userId = '22222222-2222-4222-8222-222222222222';
const attachmentId = '33333333-3333-4333-8333-333333333333';

const currentUser = {
  user_id: userId,
  email: 'user@example.com',
  nickname: '사용자',
  avatar_url: null,
  avatar_kind: 'default',
  avatar_content_type: null,
  avatar_byte_size: null,
  avatar_updated_at: null,
  has_avatar: false,
  status: 'active',
  roles: ['user'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

const fileItem: AttachmentLibraryItem = {
  attachment_id: attachmentId,
  trip_id: '44444444-4444-4444-8444-444444444444',
  trip_day_index: 2,
  trip_poi_id: null,
  curated_plan_id: null,
  curated_poi_id: null,
  notice_plan_id: null,
  notice_poi_id: null,
  source_attachment_id: null,
  bucket: 'pinvi-media',
  storage_key: `user-uploads/trip_day_attachment/${userId}/2026/06/day.jpg`,
  original_filename: 'day.jpg',
  content_type: 'image/jpeg',
  byte_size: 4096,
  public_url: null,
  role: 'image',
  description: '둘째 날 영수증',
  sort_order: 0,
  created_at: '2026-06-01T09:00:00+09:00',
  updated_at: '2026-06-01T09:00:00+09:00',
  target_scope: 'day',
  uploaded_by_user_id: userId,
  uploaded_by_email_masked: 'u***@example.com',
  trip_title: '부산 여행',
  poi_label: null,
};

test('파일 목록 로드 실패는 원인 + 다시 시도를 준다', async ({ page }) => {
  // T-316: 회복 행동 없는 오류 배너를 role=alert + 재시도로 바꿨다.
  let attempts = 0;
  await page.route(/.*\/users\/me\/files(\?.*)?$/, async (route, request) => {
    if (!['fetch', 'xhr'].includes(request.resourceType())) return route.continue();
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          error: { code: 'INTERNAL', message: '파일을 불러오지 못했습니다.' },
        }),
      });
      return;
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ items: [], total: 0 }),
    });
  });

  await page.goto('/files');
  const alert = page.getByTestId('my-file-error');
  await expect(alert).toBeVisible();
  await expect(alert).toHaveAttribute('role', 'alert');

  await alert.getByRole('button', { name: '다시 시도' }).click();
  await expect.poll(() => attempts).toBeGreaterThan(1);

  // 빈 상태는 다음 행동을 준다.
  await expect(page.getByText('업로드한 파일이 없습니다.')).toBeVisible();
  await expect(page.getByRole('link', { name: '여행으로 가기' })).toBeVisible();
});

test('내 파일함에서 파일을 다운로드하고 삭제한다', async ({ page }) => {
  let items = [fileItem];

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
        body: JSON.stringify({ data: currentUser }),
      });
    },
  );

  await page.route(
    (url) => url.port === '12801' && url.pathname.startsWith('/users/me/files'),
    async (route) => {
      const { pathname } = new URL(route.request().url());
      if (pathname === `/users/me/files/${attachmentId}/download-url`) {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            data: {
              method: 'GET',
              bucket: fileItem.bucket,
              storage_key: fileItem.storage_key,
              download_url: 'http://127.0.0.1:9558/pinvi-media/day.jpg?X-Amz-Signature=get',
              expires_at: '2026-06-01T09:15:00+09:00',
              public_url: null,
            },
          }),
        });
        return;
      }
      if (pathname === `/users/me/files/${attachmentId}` && route.request().method() === 'DELETE') {
        items = [];
        await route.fulfill({ status: 204, body: '' });
        return;
      }
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

  await page.goto('/files');
  await expect(page.getByRole('heading', { name: '파일' })).toBeVisible();
  await expect(page.getByTestId('my-file-list')).toContainText('day.jpg');
  await expect(page.getByTestId('my-file-list')).toContainText('부산 여행');

  await page.getByRole('button', { name: '다운로드' }).click();
  await expect
    .poll(() =>
      page.evaluate(() => (window as Window & { __pinviOpenedUrl?: string }).__pinviOpenedUrl),
    )
    .toContain('X-Amz-Signature=get');

  // 파괴적 액션은 공용 확인 다이얼로그를 거친다(native confirm 제거, T-316).
  await page.getByRole('button', { name: '삭제' }).click();
  await expect(page.getByTestId('file-delete-confirm')).toBeVisible();

  // 취소하면 요청이 나가지 않는다.
  await page.getByTestId('file-delete-confirm-cancel').click();
  await expect(page.getByTestId('file-delete-confirm')).toHaveCount(0);
  await expect(page.getByTestId('my-file-list')).toContainText('day.jpg');

  await page.getByRole('button', { name: '삭제' }).click();
  await page.getByTestId('file-delete-confirm-confirm').click();
  await expect(page.getByText('업로드한 파일이 없습니다.')).toBeVisible();
});
