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

const seedScenarios = {
  environment: 'development',
  enabled: false,
  mode: 'dry_run_only',
  scenarios: [
    {
      key: 'new_user_first_trip',
      title: '새 사용자와 첫 여행',
      description: '가입 직후 첫 여행',
      destructive: false,
      confirm_phrase: 'RUN new_user_first_trip',
      steps: ['사용자 샘플 확인', '여행/day/POI 생성 계획'],
    },
  ],
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
});

test('Seed 페이지가 scenario dry-run을 실행한다', async ({ page }) => {
  let dryRunBody: Record<string, unknown> | null = null;
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/seed/scenarios',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: seedScenarios }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === '/admin/seed/scenarios/new_user_first_trip',
    async (route) => {
      dryRunBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            action: 'dev_seed.dry_run',
            target: 'new_user_first_trip',
            status: 'dry_run',
            dry_run: true,
            audit_log_id: 101,
            would_execute: ['사용자 샘플 확인'],
            message: 'seed scenario dry-run을 기록했습니다.',
          },
        }),
      });
    },
  );

  await page.goto('/admin/seed');
  await expect(page.getByRole('heading', { name: '시드 시나리오' })).toBeVisible();
  await page.getByTestId('admin-seed-row-new_user_first_trip').click();
  await page.getByTestId('admin-seed-confirm').fill('RUN new_user_first_trip');
  await page.getByTestId('admin-seed-reason').fill('dev smoke dry-run');
  await page.getByTestId('admin-seed-run').click();
  await expect(page.getByTestId('admin-seed-notice')).toContainText('#101');
  expect(dryRunBody).toEqual({
    confirm: 'RUN new_user_first_trip',
    access_reason: 'dev smoke dry-run',
    dry_run: true,
  });
});

test('Reset 페이지가 reset dry-run을 실행한다', async ({ page }) => {
  let resetBody: Record<string, unknown> | null = null;
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/reset/status',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            environment: 'development',
            enabled: false,
            mode: 'dry_run_only',
            confirm_phrase: 'RESET',
            target_schemas: ['app'],
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/reset',
    async (route) => {
      resetBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            action: 'dev_reset.dry_run',
            target: 'app',
            status: 'dry_run',
            dry_run: true,
            audit_log_id: 202,
            would_execute: ['현재 app schema 상태 확인'],
            message: 'reset dry-run을 기록했습니다.',
          },
        }),
      });
    },
  );

  await page.goto('/admin/reset');
  await expect(page.getByRole('heading', { name: 'DB 리셋' })).toBeVisible();
  await expect(page.getByTestId('admin-reset-environment')).toContainText('development');
  await page.getByTestId('admin-reset-confirm').fill('RESET');
  await page.getByTestId('admin-reset-reason').fill('reset rehearsal');
  await page.getByTestId('admin-reset-include-seed').uncheck();
  await page.getByTestId('admin-reset-run').click();
  await expect(page.getByTestId('admin-reset-notice')).toContainText('#202');
  expect(resetBody).toEqual({
    confirm: 'RESET',
    access_reason: 'reset rehearsal',
    dry_run: true,
    include_seed: false,
  });
});

test('Seed production-hidden 응답에서는 action을 렌더링하지 않는다', async ({ page }) => {
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/seed/scenarios',
    async (route) => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ error: { code: 'RESOURCE_NOT_FOUND', message: 'Not found.' } }),
      });
    },
  );

  await page.goto('/admin/seed');
  await expect(page.getByText('seed route가 비활성화되어 있습니다.')).toBeVisible();
  await expect(page.getByTestId('admin-seed-run')).toHaveCount(0);
});
