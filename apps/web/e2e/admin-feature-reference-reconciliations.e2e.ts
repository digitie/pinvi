import { expect, test } from '@playwright/test';

const adminUser = {
  user_id: '77777777-7777-4777-8777-777777777777',
  email: 'admin@example.com',
  nickname: '관리자',
  avatar_url: null,
  status: 'active',
  roles: ['user', 'admin'],
  email_verified_at: '2026-08-21T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

const appliedEventId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const blockedEventId = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const appliedAttempt = {
  event_id: appliedEventId,
  attempt_sequence: 1,
  event_sequence: 10,
  event_sha256: 'a'.repeat(64),
  status: 'applied',
  block_fingerprint_sha256: null,
  observation_root_sha256: 'b'.repeat(64),
  observed_at: '2026-08-21T10:00:00+09:00',
};
const blockedAttempt = {
  event_id: blockedEventId,
  attempt_sequence: 2,
  event_sequence: 11,
  event_sha256: 'c'.repeat(64),
  status: 'blocked',
  block_fingerprint_sha256: 'd'.repeat(64),
  observation_root_sha256: 'e'.repeat(64),
  observed_at: '2026-08-21T10:01:00+09:00',
};
const receipt = {
  event_id: appliedEventId,
  event_sequence: 10,
  event_sha256: 'a'.repeat(64),
  action: 'rebind',
  old_feature_id: 'feature-old',
  old_feature_uuid: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
  replacement_feature_id: 'feature-new',
  replacement_feature_uuid: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
  impact_root_sha256: 'f'.repeat(64),
  impact_count: 1,
  receipt_sha256: '0'.repeat(64),
  applied_at: '2026-08-21T10:00:00+09:00',
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
    (url) => url.port === '12801' && url.pathname === '/admin/feature-reference-reconciliations',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [
              {
                event_id: appliedEventId,
                status: 'applied',
                event_sequence: 10,
                event_sha256: 'a'.repeat(64),
                observed_at: '2026-08-21T10:00:00+09:00',
                receipt,
                latest_attempt: appliedAttempt,
              },
              {
                event_id: blockedEventId,
                status: 'blocked',
                event_sequence: 11,
                event_sha256: 'c'.repeat(64),
                observed_at: '2026-08-21T10:01:00+09:00',
                receipt: null,
                latest_attempt: blockedAttempt,
              },
            ],
            total: 2,
            page: 1,
            limit: 50,
          },
        }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/feature-reference-reconciliations/${appliedEventId}`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            event_id: appliedEventId,
            status: 'applied',
            receipt,
            attempts: [appliedAttempt],
            impacts: [
              {
                event_id: appliedEventId,
                impact_index: 0,
                target_relation: 'trip_day_pois',
                target_id: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
                old_feature_id: 'feature-old',
                old_feature_uuid: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
                replacement_feature_id: 'feature-new',
                replacement_feature_uuid: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
                outcome: 'rebind',
                recorded_at: '2026-08-21T10:00:00+09:00',
              },
            ],
          },
        }),
      });
    },
  );
});

test('Admin이 M05 receipt와 blocked evidence를 읽기 전용으로 확인한다', async ({ page }) => {
  await page.goto('/admin/feature-reference-reconciliations');

  await expect(page.getByRole('heading', { name: 'Feature 참조 조정 증거' })).toBeVisible();
  await expect(page.getByText('blocked')).toBeVisible();
  await page.getByTestId(`admin-frr-detail-${appliedEventId}`).click();

  const detail = page.getByTestId('admin-frr-detail');
  await expect(detail).toContainText('feature-old');
  await expect(detail).toContainText('feature-new');
  await expect(detail).toContainText('trip_day_pois · rebind');
  await expect(detail).not.toContainText('승인');
  await expect(detail).not.toContainText('거절');
});
