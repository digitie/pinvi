import { expect, test } from '@playwright/test';

const adminUser = {
  user_id: '77777777-7777-4777-8777-777777777777',
  email: 'admin@example.com',
  nickname: '관리자',
  avatar_url: null,
  status: 'active',
  roles: ['user', 'admin'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

const targetUserId = '99999999-9999-4999-8999-999999999999';

const maskedUser = {
  user_id: targetUserId,
  email_masked: 's***@example.com',
  email: 's***@example.com',
  email_revealed: false,
  nickname: '비밀사용자',
  status: 'active',
  roles: ['user'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  created_at: '2026-06-01T09:00:00+09:00',
  email_status: 'active',
  is_active: true,
  recent_audit: [],
};

test.beforeEach(async ({ page }) => {
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
    (url) => url.port === '12801' && url.pathname === '/admin/settings/avatar',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: { avatar_max_upload_bytes: 2097152 } }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/users/${targetUserId}/sessions`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: { user_id: targetUserId, items: [] } }),
      });
    },
  );
});

test('Admin 사용자 목록이 검색어와 상태 필터를 API에 전달한다', async ({ page }) => {
  const listRequests: string[] = [];

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/users',
    async (route) => {
      listRequests.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [
              {
                user_id: targetUserId,
                email_masked: 'k***@example.com',
                nickname: '김여행',
                status: 'active',
                roles: ['user'],
                email_verified_at: '2026-06-01T09:00:00+09:00',
                created_at: '2026-06-01T09:00:00+09:00',
              },
            ],
            total: 1,
            page: 1,
            limit: 50,
          },
        }),
      });
    },
  );

  await page.goto('/admin/users');
  await expect(page.getByRole('heading', { name: '사용자' })).toBeVisible();
  await expect(page.getByText('김여행')).toBeVisible();

  await page.getByTestId('admin-users-search').fill('kim');
  await page.getByTestId('admin-users-search-submit').click();
  await expect.poll(() => listRequests.some((url) => url.includes('q=kim'))).toBe(true);

  await page.getByTestId('admin-users-status-filter').selectOption('active');
  await expect
    .poll(() =>
      listRequests.some((url) => url.includes('q=kim') && url.includes('status_filter=active')),
    )
    .toBe(true);

  expect(listRequests.some((url) => url.includes('/features/'))).toBe(false);
  expect(listRequests.some((url) => url.includes('12701'))).toBe(false);
});

test('Admin 사용자 상세가 사유와 함께 이메일 원본 조회 audit을 표시한다', async ({ page }) => {
  let revealReason: string | null = null;
  let revealUrl: string | null = null;

  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/users/${targetUserId}`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: maskedUser,
        }),
      });
    },
  );

  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/users/${targetUserId}/reveal-pii`,
    async (route) => {
      const body = route.request().postDataJSON() as { access_reason?: string } | null;
      revealUrl = route.request().url();
      revealReason = body?.access_reason ?? null;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            ...maskedUser,
            email: 'secret@example.com',
            email_revealed: true,
            recent_audit: [
              {
                log_id: 12,
                actor_user_id: adminUser.user_id,
                action: 'user.reveal_pii',
                resource_type: 'user',
                resource_id: targetUserId,
                access_reason: '고객 문의 확인',
                target_pii_fields: ['email'],
                prev_hash: '0'.repeat(64),
                content_hash: '1'.repeat(64),
                occurred_at: '2026-06-06T12:00:00+09:00',
              },
            ],
          },
        }),
      });
    },
  );

  await page.goto(`/admin/users/${targetUserId}`);

  await expect(page.getByTestId('admin-user-email')).toContainText('s***@example.com');
  await page.getByTestId('admin-user-reveal-email').click();
  await page.getByTestId('admin-user-action-reason').fill('고객 문의 확인');
  await page.getByTestId('admin-user-action-confirm').click();

  await expect(page.getByTestId('admin-user-email')).toContainText('secret@example.com');
  await expect(page.getByTestId('admin-user-audit-list')).toContainText('user.reveal_pii');
  expect(revealReason).toBe('고객 문의 확인');
  expect(revealUrl).not.toContain('access_reason');
});

test('Admin 사용자 상세에서 역할을 부여하고 회수한다', async ({ page }) => {
  let currentUser: Record<string, unknown> = { ...maskedUser, roles: ['user'] };
  let grantReason: string | null = null;
  let revokeReason: string | null = null;

  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/users/${targetUserId}`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: currentUser }),
      });
    },
  );

  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/users/${targetUserId}/roles/grant`,
    async (route) => {
      const body = route.request().postDataJSON() as { role?: string; access_reason?: string };
      grantReason = body.access_reason ?? null;
      currentUser = {
        ...currentUser,
        roles: ['user', body.role ?? 'operator'],
        recent_audit: [
          {
            log_id: 50,
            actor_user_id: adminUser.user_id,
            action: 'user.role_grant',
            resource_type: 'user',
            resource_id: targetUserId,
            access_reason: body.access_reason ?? null,
            target_pii_fields: null,
            prev_hash: '0'.repeat(64),
            content_hash: '1'.repeat(64),
            occurred_at: '2026-06-06T12:00:00+09:00',
          },
        ],
      };
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: currentUser }),
      });
    },
  );

  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/users/${targetUserId}/roles/revoke`,
    async (route) => {
      const body = route.request().postDataJSON() as { role?: string; access_reason?: string };
      revokeReason = body.access_reason ?? null;
      currentUser = {
        ...currentUser,
        roles: ['user'],
        recent_audit: [
          {
            log_id: 51,
            actor_user_id: adminUser.user_id,
            action: 'user.role_revoke',
            resource_type: 'user',
            resource_id: targetUserId,
            access_reason: body.access_reason ?? null,
            target_pii_fields: null,
            prev_hash: '1'.repeat(64),
            content_hash: '2'.repeat(64),
            occurred_at: '2026-06-06T12:10:00+09:00',
          },
        ],
      };
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: currentUser }),
      });
    },
  );

  await page.goto(`/admin/users/${targetUserId}`);

  await page.getByTestId('admin-user-role-select').selectOption('operator');
  await page.getByTestId('admin-user-role-reason').fill('운영 담당자 지정');
  await page.getByTestId('admin-user-role-grant').click();

  await expect(page.getByTestId('admin-user-role-manager')).toContainText('operator');
  await expect(page.getByTestId('admin-user-audit-list')).toContainText('user.role_grant');
  expect(grantReason).toBe('운영 담당자 지정');

  await page.getByTestId('admin-user-role-reason').fill('운영 담당 해제');
  await page.getByTestId('admin-user-role-revoke').click();

  await expect(page.getByTestId('admin-user-role-manager')).not.toContainText('operator');
  await expect(page.getByTestId('admin-user-audit-list')).toContainText('user.role_revoke');
  expect(revokeReason).toBe('운영 담당 해제');
});

test('Admin 사용자 상세에서 lifecycle 액션과 세션 강제 로그아웃을 처리한다', async ({ page }) => {
  const sessionId = '88888888-8888-4888-8888-888888888888';
  let currentUser: Record<string, unknown> = { ...maskedUser };
  let currentSessions: Array<{
    session_id: string;
    created_at: string;
    updated_at: string;
    expires_at: string;
    revoked_at: string | null;
    user_agent: string;
    ip_hash: string;
    is_active: boolean;
  }> = [
    {
      session_id: sessionId,
      created_at: '2026-06-01T09:00:00+09:00',
      updated_at: '2026-06-01T09:00:00+09:00',
      expires_at: '2026-06-08T09:00:00+09:00',
      revoked_at: null,
      user_agent: 'Firefox',
      ip_hash: 'a'.repeat(64),
      is_active: true,
    },
  ];
  let revokedReason: string | null = null;
  let resetReason: string | null = null;
  let deleteReason: string | null = null;

  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/users/${targetUserId}`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: currentUser }),
      });
    },
  );

  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/users/${targetUserId}/sessions`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: { user_id: targetUserId, items: currentSessions } }),
      });
    },
  );

  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/users/${targetUserId}/sessions/${sessionId}/revoke`,
    async (route) => {
      const body = route.request().postDataJSON() as { access_reason?: string };
      revokedReason = body.access_reason ?? null;
      currentSessions = currentSessions.map((session) => ({
        ...session,
        revoked_at: '2026-06-01T10:00:00+09:00',
        is_active: false,
      }));
      currentUser = {
        ...currentUser,
        recent_audit: [
          {
            log_id: 60,
            actor_user_id: adminUser.user_id,
            action: 'user.session_revoke',
            resource_type: 'user',
            resource_id: targetUserId,
            access_reason: body.access_reason ?? null,
            target_pii_fields: ['session'],
            prev_hash: '0'.repeat(64),
            content_hash: '1'.repeat(64),
            occurred_at: '2026-06-06T12:00:00+09:00',
          },
        ],
      };
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: currentUser }),
      });
    },
  );

  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/users/${targetUserId}/lifecycle/force-password-reset`,
    async (route) => {
      const body = route.request().postDataJSON() as { access_reason?: string };
      resetReason = body.access_reason ?? null;
      currentUser = {
        ...currentUser,
        recent_audit: [
          {
            log_id: 61,
            actor_user_id: adminUser.user_id,
            action: 'user.password_reset_force',
            resource_type: 'user',
            resource_id: targetUserId,
            access_reason: body.access_reason ?? null,
            target_pii_fields: ['email', 'password_hash'],
            prev_hash: '1'.repeat(64),
            content_hash: '2'.repeat(64),
            occurred_at: '2026-06-06T12:05:00+09:00',
          },
        ],
      };
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: currentUser }),
      });
    },
  );

  await page.route(
    (url) =>
      url.port === '12801' && url.pathname === `/admin/users/${targetUserId}/lifecycle/delete`,
    async (route) => {
      const body = route.request().postDataJSON() as { access_reason?: string; confirm?: string };
      deleteReason = `${body.access_reason ?? ''}:${body.confirm ?? ''}`;
      currentUser = {
        ...currentUser,
        status: 'pending_delete',
        is_active: false,
        recent_audit: [
          {
            log_id: 62,
            actor_user_id: adminUser.user_id,
            action: 'user.delete_schedule',
            resource_type: 'user',
            resource_id: targetUserId,
            access_reason: body.access_reason ?? null,
            target_pii_fields: ['email'],
            prev_hash: '2'.repeat(64),
            content_hash: '3'.repeat(64),
            occurred_at: '2026-06-06T12:10:00+09:00',
          },
        ],
      };
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: currentUser }),
      });
    },
  );

  page.on('dialog', (dialog) => dialog.accept());

  await page.goto(`/admin/users/${targetUserId}`);
  await expect(page.getByTestId('admin-user-lifecycle-section')).toBeVisible();
  await expect(page.getByTestId('admin-user-sessions')).toContainText('Firefox');

  await page.getByTestId('admin-user-lifecycle-reason').fill('분실 기기 세션 종료');
  await page.getByTestId(`admin-user-session-revoke-${sessionId}`).click();
  await expect(page.getByTestId('admin-user-sessions')).toContainText('revoked');
  await expect(page.getByTestId('admin-user-audit-list')).toContainText('user.session_revoke');
  expect(revokedReason).toBe('분실 기기 세션 종료');

  await page.getByTestId('admin-user-lifecycle-reason').fill('계정 탈취 의심');
  await page.getByTestId('admin-user-force-password-reset').click();
  await expect(page.getByTestId('admin-user-audit-list')).toContainText(
    'user.password_reset_force',
  );
  expect(resetReason).toBe('계정 탈취 의심');

  await page.getByTestId('admin-user-lifecycle-reason').fill('탈퇴 요청 접수');
  await page.getByTestId('admin-user-schedule-delete').click();
  await expect(page.getByTestId('admin-user-info')).toContainText('pending_delete');
  expect(deleteReason).toBe('탈퇴 요청 접수:DELETE');
});

test('Admin RBAC 권한 매트릭스를 표시한다', async ({ page }) => {
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/rbac/permission-matrix',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            roles: {
              user: '일반 사용자',
              admin: '전체 운영 mutation',
              operator: '운영 조회',
              cpo: '개인정보 처리',
            },
            entries: [
              {
                resource: 'admin.users',
                action: 'role_grant_revoke',
                route: '/admin/users/{user_id}/roles/{grant|revoke}',
                roles: ['admin'],
                access_reason_required: true,
                audit_required: true,
                notes: '자기 admin 회수 차단',
              },
            ],
          },
        }),
      });
    },
  );

  await page.goto('/admin/rbac');

  await expect(page.getByRole('heading', { name: 'RBAC' })).toBeVisible();
  await expect(page.getByTestId('admin-rbac-roles')).toContainText('admin');
  await expect(page.getByTestId('admin-table-scroll')).toContainText('role_grant_revoke');
});

test('Admin 사용자 상세에서 아바타 교체, 삭제, 전역 제한을 관리한다', async ({ page }) => {
  let currentUser: Record<string, unknown> = { ...maskedUser };
  let avatarReason: string | null = null;
  let settingsReason: string | null = null;
  let settingsBytes: number | null = null;

  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/users/${targetUserId}`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: currentUser }),
      });
    },
  );

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/settings/avatar',
    async (route) => {
      if (route.request().method() === 'PUT') {
        const body = route.request().postDataJSON() as {
          avatar_max_upload_bytes: number;
          access_reason: string;
        };
        settingsBytes = body.avatar_max_upload_bytes;
        settingsReason = body.access_reason;
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: { avatar_max_upload_bytes: body.avatar_max_upload_bytes } }),
        });
        return;
      }
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: { avatar_max_upload_bytes: 2097152 } }),
      });
    },
  );

  await page.route(
    (url) =>
      url.port === '12801' && url.pathname === `/admin/users/${targetUserId}/avatar/upload-url`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            method: 'PUT',
            bucket: 'pinvi-media',
            storage_key: `user-uploads/avatar/${targetUserId}/2026/06/avatar.png`,
            upload_url: 'http://127.0.0.1:9556/pinvi-media/avatar.png?X-Amz-Signature=z',
            headers: { 'Content-Type': 'image/png' },
            expires_at: '2026-06-01T09:15:00+09:00',
            max_upload_bytes: 2097152,
            public_url: null,
          },
        }),
      });
    },
  );

  await page.route(/.*127\.0\.0\.1:9556.*/, async (route) => {
    await route.fulfill({ status: 200, body: '' });
  });

  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/users/${targetUserId}/avatar`,
    async (route) => {
      const body = route.request().postDataJSON() as { access_reason?: string } | null;
      avatarReason = body?.access_reason ?? null;
      if (route.request().method() === 'PUT') {
        currentUser = {
          ...currentUser,
          has_avatar: true,
          avatar_kind: 'upload',
          avatar_content_type: 'image/png',
          avatar_byte_size: 5,
          avatar_updated_at: '2026-06-01T09:10:00+09:00',
          recent_audit: [
            {
              log_id: 40,
              actor_user_id: adminUser.user_id,
              action: 'user.avatar_replace',
              resource_type: 'user',
              resource_id: targetUserId,
              access_reason: body?.access_reason ?? null,
              target_pii_fields: ['avatar'],
              prev_hash: '0'.repeat(64),
              content_hash: '1'.repeat(64),
              occurred_at: '2026-06-06T12:00:00+09:00',
            },
          ],
        };
      } else {
        currentUser = {
          ...currentUser,
          has_avatar: false,
          avatar_kind: 'default',
          avatar_content_type: null,
          avatar_byte_size: null,
          avatar_updated_at: '2026-06-01T09:20:00+09:00',
          recent_audit: [
            {
              log_id: 41,
              actor_user_id: adminUser.user_id,
              action: 'user.avatar_delete',
              resource_type: 'user',
              resource_id: targetUserId,
              access_reason: body?.access_reason ?? null,
              target_pii_fields: ['avatar'],
              prev_hash: '1'.repeat(64),
              content_hash: '2'.repeat(64),
              occurred_at: '2026-06-06T12:10:00+09:00',
            },
          ],
        };
      }
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: currentUser }),
      });
    },
  );

  await page.route(
    (url) =>
      url.port === '12801' && url.pathname === `/admin/users/${targetUserId}/avatar/download-url`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            method: 'GET',
            bucket: 'pinvi-media',
            storage_key: `user-uploads/avatar/${targetUserId}/2026/06/avatar.png`,
            download_url: 'http://127.0.0.1:9556/pinvi-media/avatar.png?X-Amz-Signature=get',
            expires_at: '2026-06-01T09:15:00+09:00',
            public_url: null,
          },
        }),
      });
    },
  );

  page.on('dialog', (dialog) => dialog.accept());

  await page.goto(`/admin/users/${targetUserId}`);
  await expect(page.getByTestId('admin-user-avatar-section')).toContainText('등록된 이미지 없음');

  await page.getByTestId('admin-user-avatar-reason').fill('사용자 요청 대행');
  await page.getByTestId('admin-user-avatar-input').setInputFiles({
    name: 'avatar.png',
    mimeType: 'image/png',
    buffer: Buffer.from('hello'),
  });

  await expect(page.getByTestId('admin-user-avatar-meta')).toContainText('image/png');
  await expect(page.getByTestId('admin-user-avatar-image')).toBeVisible();
  await expect(page.getByTestId('admin-user-audit-list')).toContainText('user.avatar_replace');
  expect(avatarReason).toBe('사용자 요청 대행');

  await page.getByTestId('admin-avatar-settings-max-bytes').fill('4096');
  await page.getByTestId('admin-avatar-settings-reason').fill('부하 제한 조정');
  await page.getByTestId('admin-avatar-settings-save').click();

  expect(settingsBytes).toBe(4096);
  expect(settingsReason).toBe('부하 제한 조정');

  await page.getByTestId('admin-user-avatar-reason').fill('사용자 요청 삭제');
  await page.getByTestId('admin-user-avatar-delete').click();

  await expect(page.getByTestId('admin-user-avatar-section')).toContainText('등록된 이미지 없음');
  await expect(page.getByTestId('admin-user-audit-list')).toContainText('user.avatar_delete');
  expect(avatarReason).toBe('사용자 요청 삭제');
});
