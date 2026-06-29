import { expect, test } from '@playwright/test';

const userId = '22222222-2222-4222-8222-222222222222';

test('프로필에서 아바타를 업로드하고 삭제한다', async ({ page }) => {
  let currentUser: Record<string, unknown> = {
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
    (url) => url.port === '12801' && url.pathname === '/auth/oauth/providers',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: { providers: [{ provider: 'google', enabled: true }] } }),
      });
    },
  );

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/users/me/avatar/upload-url',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            method: 'PUT',
            bucket: 'pinvi-media',
            storage_key: `user-uploads/avatar/${userId}/2026/06/avatar.jpg`,
            upload_url: 'http://127.0.0.1:9557/pinvi-media/avatar.jpg?X-Amz-Signature=z',
            headers: { 'Content-Type': 'image/jpeg' },
            expires_at: '2026-06-01T09:15:00+09:00',
            max_upload_bytes: 2097152,
            public_url: null,
          },
        }),
      });
    },
  );

  await page.route(/.*127\.0\.0\.1:9557.*/, async (route) => {
    await route.fulfill({ status: 200, body: '' });
  });

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/users/me/avatar',
    async (route) => {
      if (route.request().method() === 'PUT') {
        currentUser = {
          ...currentUser,
          avatar_kind: 'upload',
          avatar_content_type: 'image/jpeg',
          avatar_byte_size: 5,
          avatar_updated_at: '2026-06-01T09:10:00+09:00',
          has_avatar: true,
        };
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            data: {
              avatar_kind: 'upload',
              avatar_url: null,
              avatar_content_type: 'image/jpeg',
              avatar_byte_size: 5,
              avatar_updated_at: '2026-06-01T09:10:00+09:00',
              has_avatar: true,
            },
          }),
        });
        return;
      }
      currentUser = {
        ...currentUser,
        avatar_kind: 'default',
        avatar_content_type: null,
        avatar_byte_size: null,
        avatar_updated_at: '2026-06-01T09:20:00+09:00',
        has_avatar: false,
      };
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            avatar_kind: 'default',
            avatar_url: null,
            avatar_content_type: null,
            avatar_byte_size: null,
            avatar_updated_at: '2026-06-01T09:20:00+09:00',
            has_avatar: false,
          },
        }),
      });
    },
  );

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/users/me/avatar/download-url',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            method: 'GET',
            bucket: 'pinvi-media',
            storage_key: `user-uploads/avatar/${userId}/2026/06/avatar.jpg`,
            download_url: 'http://127.0.0.1:9557/pinvi-media/avatar.jpg?X-Amz-Signature=get',
            expires_at: '2026-06-01T09:15:00+09:00',
            public_url: null,
          },
        }),
      });
    },
  );

  page.on('dialog', (dialog) => dialog.accept());

  await page.goto('/profile');
  await expect(page.getByRole('heading', { name: '프로필' })).toBeVisible();
  await expect(page.getByTestId('profile-avatar-meta')).toContainText('등록된 이미지 없음');

  await page.getByTestId('profile-avatar-input').setInputFiles({
    name: 'avatar.jpg',
    mimeType: 'image/jpeg',
    buffer: Buffer.from('hello'),
  });

  await expect(page.getByTestId('profile-avatar-meta')).toContainText('image/jpeg');
  await expect(page.getByTestId('profile-avatar-image')).toBeVisible();

  await page.getByTestId('profile-avatar-delete').click();

  await expect(page.getByTestId('profile-avatar-meta')).toContainText('등록된 이미지 없음');
});
