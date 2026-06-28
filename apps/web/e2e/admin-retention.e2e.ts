import { expect, test, type Page, type Route } from '@playwright/test';

const cpoUser = {
  user_id: '99999999-9999-4999-8999-999999999999',
  email: 'cpo@example.com',
  nickname: 'CPO',
  avatar_url: null,
  status: 'active',
  roles: ['user', 'admin', 'cpo'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

const runId = '11111111-1111-4111-8111-111111111111';
const dryRunId = '22222222-2222-4222-8222-222222222222';

function retentionRun(overrides: Record<string, unknown> = {}) {
  return {
    run_id: runId,
    mode: 'execute',
    scope: 'all',
    status: 'completed',
    candidate_snapshot: {},
    result: {
      pii: { anonymized_users: 1 },
      location: { archived_rows: 1, deleted_active_rows: 1 },
      skipped_admin_audit_pii_over_retention: 1,
    },
    kill_switch_enabled: true,
    access_reason: '보존기간 정리',
    actor_user_id: cpoUser.user_id,
    error_message: null,
    started_at: '2026-06-28T09:00:00+09:00',
    completed_at: '2026-06-28T09:01:00+09:00',
    created_at: '2026-06-28T09:00:00+09:00',
    updated_at: '2026-06-28T09:01:00+09:00',
    ...overrides,
  };
}

function retentionSummary(rows: ReturnType<typeof retentionRun>[]) {
  return {
    generated_at: '2026-06-28T09:05:00+09:00',
    execute_enabled: false,
    confirm_phrase: 'EXECUTE RETENTION',
    pii_retention: {
      dry_run: true,
      generated_at: '2026-06-28T09:05:00+09:00',
      user_pii_cutoff: '2026-05-29T09:05:00+09:00',
      session_cutoff: '2026-05-29T09:05:00+09:00',
      location_cutoff: '2025-12-28T09:05:00+09:00',
      user_pii_grace_days: 30,
      session_grace_days: 30,
      location_retention_months: 6,
      total_candidates: 10,
      deleted_user_pii_candidates: 1,
      deleted_user_oauth_identity_candidates: 1,
      excluded_privileged_deleted_users: 1,
      expired_signup_verifications: 1,
      expired_password_reset_tokens: 1,
      old_revoked_sessions: 1,
      old_expired_sessions: 1,
      expired_oauth_login_states: 1,
      expired_mobile_oauth_exchanges: 1,
      location_access_logs_over_retention: 1,
      admin_audit_pii_over_retention: 1,
    },
    location_log_archive: {
      dry_run: true,
      generated_at: '2026-06-28T09:05:00+09:00',
      archive_cutoff: '2025-12-28T09:05:00+09:00',
      location_retention_months: 6,
      total_candidates: 1,
      oldest_candidate_at: '2025-12-10T09:05:00+09:00',
      newest_candidate_at: '2025-12-10T09:05:00+09:00',
      archive_tail_log_id: 1,
      active_head_log_id: 2,
      active_rows_after_cutoff: 1,
      chain_bridge_required: true,
      bridge_anchor_matches: true,
      pending_outbox_total: 1,
      pending_outbox_before_cutoff: 0,
      archive_blocked_by_pending_outbox: false,
      oldest_pending_outbox_at: '2026-06-28T09:00:00+09:00',
      purpose_stats: [{ purpose: 'nearby_attractions', total: 1 }],
    },
    latest_runs: rows,
  };
}

async function mockCpoAuth(page: Page) {
  await page.route(/.*\/auth\/me$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: cpoUser }),
    });
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

test('Admin retention page가 summary, dry-run, kill-switch guard를 렌더링한다', async ({
  page,
}) => {
  await mockCpoAuth(page);
  let rows = [retentionRun()];
  let dryRunBody: Record<string, unknown> | null = null;

  await page.route(/.*\/admin\/retention\/summary$/, async (route) => {
    if (await continueIfWebRequest(route)) return;
    await fulfillJson(route, { data: retentionSummary(rows) });
  });

  await page.route(/.*\/admin\/retention\/runs(\?.*)?$/, async (route) => {
    if (await continueIfWebRequest(route)) return;
    await fulfillJson(route, { data: { items: rows, page_size: 20 } });
  });

  await page.route(/.*\/admin\/retention\/dry-run$/, async (route) => {
    if (await continueIfWebRequest(route)) return;
    dryRunBody = route.request().postDataJSON() as Record<string, unknown>;
    const created = retentionRun({
      run_id: dryRunId,
      mode: 'dry_run',
      scope: dryRunBody.scope,
      status: 'dry_run',
      result: { dry_run: true },
      kill_switch_enabled: false,
      access_reason: dryRunBody.access_reason,
    });
    rows = [created, ...rows];
    await fulfillJson(route, { data: created });
  });

  await page.goto('/admin/retention');

  await expect(page.getByRole('heading', { name: 'Retention' })).toBeVisible();
  await expect(page.getByTestId('admin-nav--admin-retention')).toBeVisible();
  await expect(page.getByTestId('admin-retention-pii-total')).toContainText('10');
  await expect(page.getByTestId('admin-retention-location-total')).toContainText('1');
  await expect(page.getByTestId('admin-retention-execute-enabled')).toContainText('disabled');

  await page.getByLabel('Dry-run 사유').fill('보존기간 후보 점검');
  await page.getByTestId('admin-retention-dry-run').click();

  await expect(page.getByText(`${dryRunId} dry-run을 기록했습니다.`)).toBeVisible();
  expect(dryRunBody).toMatchObject({ scope: 'all', access_reason: '보존기간 후보 점검' });

  await page.getByLabel('Execute 사유').fill('보존기간 정리');
  await page.getByLabel('Confirm phrase').fill('EXECUTE RETENTION');
  await expect(page.getByTestId('admin-retention-execute')).toBeDisabled();
});
