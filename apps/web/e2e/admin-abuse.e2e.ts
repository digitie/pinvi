import { expect, test, type Page, type Route } from '@playwright/test';

const adminUser = {
  user_id: '99999999-9999-4999-8999-999999999999',
  email: 'admin@example.com',
  nickname: 'Admin',
  avatar_url: null,
  status: 'active',
  roles: ['user', 'admin'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

const overrideId = '33333333-3333-4333-8333-333333333333';
const createdOverrideId = '44444444-4444-4444-8444-444444444444';

function bucketRecord(overrides: Record<string, unknown> = {}) {
  return {
    bucket_hash_prefix: 'abcdef1234567890',
    limit_name: 'auth_low',
    identity_kind: 'ip_email',
    count: 9,
    limit: 5,
    remaining: 0,
    rate_limited: true,
    window_start: '2026-06-29T09:00:00+09:00',
    expires_at: '2026-06-29T09:02:00+09:00',
    updated_at: '2026-06-29T09:01:00+09:00',
    status: 'observed',
    active_override_id: null,
    active_override_action: null,
    ...overrides,
  };
}

function overrideRecord(overrides: Record<string, unknown> = {}) {
  return {
    override_id: overrideId,
    limit_name: 'auth_low',
    bucket_hash_prefix: 'abcdef1234567890',
    identity_kind: 'ip_email',
    identity_label: 'ip_email_hash:123456abcdef',
    action: 'blocked',
    status: 'blocked',
    reason: 'login abuse burst',
    created_by_user_id: adminUser.user_id,
    expires_at: '2026-06-29T10:00:00+09:00',
    revoked_at: null,
    revoked_by_user_id: null,
    revoked_reason: null,
    created_at: '2026-06-29T09:00:00+09:00',
    updated_at: '2026-06-29T09:00:00+09:00',
    ...overrides,
  };
}

function summary(overrides: Record<string, unknown> = {}) {
  const bucket = bucketRecord();
  const override = overrideRecord();
  return {
    generated_at: '2026-06-29T09:01:00+09:00',
    backend: {
      enabled: true,
      configured_backend: 'postgres',
      effective_backend: 'postgres',
      window_seconds: 60,
      fail_open: false,
      fail_closed: true,
      store_status: 'ok',
      store_error_class: null,
      store_error_message: null,
    },
    policies: [
      { name: 'auth_low', limit_per_minute: 5, identity_kind: 'ip_email' },
      { name: 'shared_trip', limit_per_minute: 60, identity_kind: 'shared_token' },
      { name: 'storage_upload_urls', limit_per_minute: 30, identity_kind: 'user' },
    ],
    buckets: [bucket],
    suspicious: [{ signal: 'auth_low_repeated_attempt', bucket }],
    overrides: [override],
    rate_limited_bucket_count: 1,
    active_override_count: 1,
    suspicious_count: 1,
    ...overrides,
  };
}

async function mockAdminAuth(page: Page) {
  await page.route(/.*\/auth\/me$/, async (route) => {
    await fulfillJson(route, { data: adminUser });
  });
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function continueIfWebRequest(route: Route) {
  const url = new URL(route.request().url());
  if (url.port !== '12801') {
    await route.continue();
    return true;
  }
  return false;
}

test('Admin abuse page가 bucket 조회, override 생성, rollback을 처리한다', async ({ page }) => {
  await mockAdminAuth(page);
  const requests: string[] = [];
  let createBody: Record<string, unknown> | null = null;
  let rollbackBody: Record<string, unknown> | null = null;
  let currentOverrides = [overrideRecord()];
  page.on('request', (request) => requests.push(request.url()));

  await page.route(/.*\/admin\/abuse\/overrides\/[^/]+\/rollback$/, async (route) => {
    rollbackBody = route.request().postDataJSON() as Record<string, unknown>;
    currentOverrides = [
      overrideRecord({
        status: 'revoked',
        revoked_at: '2026-06-29T09:10:00+09:00',
        revoked_reason: String(rollbackBody.rollback_reason),
      }),
    ];
    await fulfillJson(route, { data: currentOverrides[0] });
  });

  await page.route(/.*\/admin\/abuse\/overrides$/, async (route) => {
    createBody = route.request().postDataJSON() as Record<string, unknown>;
    const created = overrideRecord({
      override_id: createdOverrideId,
      identity_label: 'ip_email_hash:created123',
      action: createBody.action,
      status: createBody.action,
      reason: createBody.access_reason,
    });
    currentOverrides = [created, ...currentOverrides];
    await fulfillJson(route, { data: created }, 201);
  });

  await page.route(/.*\/admin\/abuse(\?.*)?$/, async (route) => {
    if (await continueIfWebRequest(route)) return;
    await fulfillJson(route, { data: summary({ overrides: currentOverrides }) });
  });

  await page.goto('/admin/abuse');

  await expect(page.getByRole('heading', { name: 'Rate-limit abuse' })).toBeVisible();
  await expect(page.getByTestId('admin-nav--admin-abuse')).toBeVisible();
  await expect(page.getByTestId('admin-abuse-store-status')).toContainText('ok');
  await expect(page.getByTestId('admin-abuse-bucket-auth_low-abcdef1234567890')).toContainText(
    'auth_low',
  );
  await expect(page.getByTestId('admin-abuse-suspicious-auth_low_repeated_attempt')).toContainText(
    '9/5',
  );

  await page.getByTestId('admin-abuse-filter').selectOption('auth_low');
  await expect
    .poll(() => requests.some((url) => url.includes('/admin/abuse') && url.includes('limit_name=auth_low')))
    .toBe(true);

  await page.getByTestId('admin-abuse-email').fill('blocked@example.com');
  await page.getByTestId('admin-abuse-reason').fill('login abuse burst');
  await page.getByTestId('admin-abuse-create').click();
  await expect(page.getByTestId('admin-abuse-notice')).toContainText('ip_email_hash:created123');
  expect(createBody).toMatchObject({
    limit_name: 'auth_low',
    identity_kind: 'ip_email',
    ip: '127.0.0.1',
    email: 'blocked@example.com',
    action: 'blocked',
    ttl_minutes: 60,
    access_reason: 'login abuse burst',
  });

  await page.getByTestId('admin-abuse-rollback-reason').fill('false positive');
  await page.getByTestId(`admin-abuse-rollback-${createdOverrideId}`).click();
  await expect(page.getByTestId('admin-abuse-notice')).toContainText('rollback했습니다');
  expect(rollbackBody).toMatchObject({
    access_reason: 'false positive',
    rollback_reason: 'false positive',
  });
});
